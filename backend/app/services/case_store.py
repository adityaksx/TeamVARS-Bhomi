import json
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.services.storage import delete_document, put_document


ROOT = Path(__file__).resolve().parents[2] / "data"
UPLOADS = ROOT / "uploads"
DB_FILE = ROOT / "cases.json"
_LOCK = threading.RLock()
_PG_READY = False

_JSON_FIELDS = {
    "analysis",
    "extracted",
    "normalized",
    "annotations",
    "source_pages",
    "source_anchors",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _settings():
    from app.core.config import get_settings
    return get_settings()


def _use_postgres() -> bool:
    return _settings().case_store_backend.casefold() == "postgres"


def _ensure_local() -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    UPLOADS.mkdir(parents=True, exist_ok=True)
    if not DB_FILE.exists():
        DB_FILE.write_text(json.dumps({"cases": {}}, indent=2), encoding="utf-8")


def _read() -> dict[str, Any]:
    _ensure_local()
    try:
        return json.loads(DB_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"cases": {}}


def _write(data: dict[str, Any]) -> None:
    tmp = DB_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, DB_FILE)


def _ensure_postgres() -> None:
    global _PG_READY
    if _PG_READY:
        return
    import psycopg

    database_url = _settings().database_url
    if not database_url:
        raise RuntimeError("DATABASE_URL is required when CASE_STORE_BACKEND=postgres")

    with psycopg.connect(database_url) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS cases (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                created_at TEXT NOT NULL,
                status TEXT NOT NULL,
                analysis JSONB
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS documents (
                id TEXT PRIMARY KEY,
                case_id TEXT NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
                filename TEXT NOT NULL,
                content_type TEXT NOT NULL,
                size BIGINT NOT NULL,
                storage_path TEXT NOT NULL,
                uploaded_at TEXT NOT NULL,
                status TEXT NOT NULL,
                job_id TEXT,
                extracted JSONB NOT NULL DEFAULT '{}'::jsonb,
                normalized JSONB NOT NULL DEFAULT '{}'::jsonb,
                annotations JSONB NOT NULL DEFAULT '{}'::jsonb,
                source_pages JSONB NOT NULL DEFAULT '{}'::jsonb,
                source_anchors JSONB NOT NULL DEFAULT '{}'::jsonb,
                page_count INTEGER
            )
            """
        )
    _PG_READY = True


def _json_value(value: Any) -> Any:
    if value is None:
        return None
    from psycopg.types.json import Jsonb
    return Jsonb(value) if isinstance(value, (dict, list)) else value


def _pg_case(case_id: str) -> dict[str, Any] | None:
    import psycopg

    _ensure_postgres()
    with psycopg.connect(_settings().database_url) as connection:
        case_row = connection.execute(
            "SELECT id, name, created_at, status, analysis FROM cases WHERE id = %s",
            (case_id,),
        ).fetchone()
        if not case_row:
            return None
        document_rows = connection.execute(
            """
            SELECT id, filename, content_type, size, storage_path, uploaded_at,
                   status, job_id, extracted, normalized, annotations,
                   source_pages, source_anchors, page_count
            FROM documents WHERE case_id = %s ORDER BY uploaded_at
            """,
            (case_id,),
        ).fetchall()

    return {
        "id": case_row[0],
        "name": case_row[1],
        "created_at": case_row[2],
        "status": case_row[3],
        "analysis": case_row[4],
        "documents": {
            row[0]: {
                "id": row[0],
                "filename": row[1],
                "content_type": row[2],
                "size": row[3],
                "storage_path": row[4],
                "uploaded_at": row[5],
                "status": row[6],
                "job_id": row[7],
                "extracted": row[8] or {},
                "normalized": row[9] or {},
                "annotations": row[10] or {},
                "source_pages": row[11] or {},
                "source_anchors": row[12] or {},
                "page_count": row[13],
            }
            for row in document_rows
        },
    }


def create_case(name: str = "Untitled property review") -> dict[str, Any]:
    case_id = f"case_{uuid.uuid4().hex[:10]}"
    case = {
        "id": case_id,
        "name": name,
        "created_at": _now(),
        "status": "draft",
        "analysis": None,
        "documents": {},
    }
    with _LOCK:
        if _use_postgres():
            import psycopg
            _ensure_postgres()
            with psycopg.connect(_settings().database_url) as connection:
                connection.execute(
                    "INSERT INTO cases (id, name, created_at, status, analysis) VALUES (%s, %s, %s, %s, %s)",
                    (case_id, name, case["created_at"], "draft", None),
                )
        else:
            data = _read()
            data["cases"][case_id] = case
            _write(data)
    return case


def get_case(case_id: str) -> dict[str, Any] | None:
    with _LOCK:
        if _use_postgres():
            return _pg_case(case_id)
        return _read().get("cases", {}).get(case_id)


def list_cases() -> list[dict[str, Any]]:
    with _LOCK:
        if _use_postgres():
            import psycopg
            _ensure_postgres()
            with psycopg.connect(_settings().database_url) as connection:
                rows = connection.execute(
                    "SELECT id FROM cases ORDER BY created_at DESC"
                ).fetchall()
            return [case for row in rows if (case := _pg_case(row[0]))]
        cases = list(_read().get("cases", {}).values())
        cases.sort(key=lambda item: item.get("created_at", ""), reverse=True)
        return cases


def update_case(case_id: str, **changes: Any) -> dict[str, Any]:
    with _LOCK:
        if _use_postgres():
            import psycopg
            allowed = {"name", "created_at", "status", "analysis"}
            invalid = set(changes) - allowed
            if invalid:
                raise ValueError(f"Unsupported case fields: {sorted(invalid)}")
            _ensure_postgres()
            assignments = ", ".join(f"{key} = %s" for key in changes)
            if assignments:
                values = [_json_value(value) if key in _JSON_FIELDS else value for key, value in changes.items()]
                values.append(case_id)
                with psycopg.connect(_settings().database_url) as connection:
                    connection.execute(f"UPDATE cases SET {assignments} WHERE id = %s", values)
            result = _pg_case(case_id)
            if not result:
                raise KeyError(case_id)
            return result

        data = _read()
        case = data["cases"][case_id]
        case.update(changes)
        _write(data)
        return case


def add_document(case_id: str, filename: str, content_type: str, content: bytes) -> dict[str, Any]:
    with _LOCK:
        if not get_case(case_id):
            raise KeyError(case_id)
        safe_name = Path(filename).name or "document"
        document_id = f"doc_{uuid.uuid4().hex[:10]}"
        storage_path = put_document(
            case_id,
            document_id,
            safe_name,
            content,
            content_type,
        )
        document = {
            "id": document_id,
            "filename": safe_name,
            "content_type": content_type,
            "size": len(content),
            "storage_path": str(storage_path),
            "uploaded_at": _now(),
            "status": "uploaded",
            "job_id": None,
            "extracted": {},
            "normalized": {},
            "annotations": {},
            "source_pages": {},
            "source_anchors": {},
            "page_count": None,
        }
        try:
            if _use_postgres():
                import psycopg
                _ensure_postgres()
                with psycopg.connect(_settings().database_url) as connection:
                    connection.execute(
                        """
                        INSERT INTO documents (
                            id, case_id, filename, content_type, size, storage_path,
                            uploaded_at, status, job_id, extracted, normalized,
                            annotations, source_pages, source_anchors, page_count
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            document["id"], case_id, document["filename"], content_type,
                            document["size"], document["storage_path"], document["uploaded_at"],
                            document["status"], None, {}, {}, {}, {}, {}, None,
                        ),
                    )
            else:
                data = _read()
                data["cases"][case_id]["documents"][document_id] = document
                _write(data)
        except Exception:
            delete_document(storage_path)
            raise
        return document


def update_document(case_id: str, document_id: str, **changes: Any) -> dict[str, Any]:
    with _LOCK:
        case = get_case(case_id)
        if not case or document_id not in case.get("documents", {}):
            raise KeyError(document_id)
        if _use_postgres():
            import psycopg
            allowed = {
                "filename", "content_type", "size", "storage_path", "uploaded_at",
                "status", "job_id", "extracted", "normalized", "annotations",
                "source_pages", "source_anchors", "page_count",
            }
            invalid = set(changes) - allowed
            if invalid:
                raise ValueError(f"Unsupported document fields: {sorted(invalid)}")
            _ensure_postgres()
            assignments = ", ".join(f"{key} = %s" for key in changes)
            values = [_json_value(value) if key in _JSON_FIELDS else value for key, value in changes.items()]
            values.append(document_id)
            with psycopg.connect(_settings().database_url) as connection:
                connection.execute(f"UPDATE documents SET {assignments} WHERE id = %s", values)
            return _pg_case(case_id)["documents"][document_id]

        data = _read()
        document = data["cases"][case_id]["documents"][document_id]
        document.update(changes)
        _write(data)
        return document
