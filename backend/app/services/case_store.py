import json
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2] / "data"
UPLOADS = ROOT / "uploads"
DB_FILE = ROOT / "cases.json"
_LOCK = threading.RLock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure() -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    UPLOADS.mkdir(parents=True, exist_ok=True)
    if not DB_FILE.exists():
        DB_FILE.write_text(json.dumps({"cases": {}}, indent=2), encoding="utf-8")


def _read() -> dict[str, Any]:
    _ensure()
    try:
        return json.loads(DB_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"cases": {}}


def _write(data: dict[str, Any]) -> None:
    tmp = DB_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, DB_FILE)


def create_case(name: str = "Untitled property review") -> dict[str, Any]:
    with _LOCK:
        data = _read()
        case_id = f"case_{uuid.uuid4().hex[:10]}"
        case = {
            "id": case_id,
            "name": name,
            "created_at": _now(),
            "status": "draft",
            "analysis": None,
            "documents": {},
        }
        data["cases"][case_id] = case
        _write(data)
        return case


def get_case(case_id: str) -> dict[str, Any] | None:
    with _LOCK:
        return _read().get("cases", {}).get(case_id)


def list_cases() -> list[dict[str, Any]]:
    with _LOCK:
        cases = list(_read().get("cases", {}).values())
        cases.sort(key=lambda item: item.get("created_at", ""), reverse=True)
        return cases


def update_case(case_id: str, **changes: Any) -> dict[str, Any]:
    with _LOCK:
        data = _read()
        case = data["cases"][case_id]
        case.update(changes)
        _write(data)
        return case


def add_document(case_id: str, filename: str, content_type: str, content: bytes) -> dict[str, Any]:
    with _LOCK:
        data = _read()
        safe_name = Path(filename).name or "document"
        document_id = f"doc_{uuid.uuid4().hex[:10]}"
        folder = UPLOADS / case_id
        folder.mkdir(parents=True, exist_ok=True)
        storage_path = folder / f"{document_id}_{safe_name}"
        storage_path.write_bytes(content)
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
        }
        data["cases"][case_id]["documents"][document_id] = document
        _write(data)
        return document


def update_document(case_id: str, document_id: str, **changes: Any) -> dict[str, Any]:
    with _LOCK:
        data = _read()
        document = data["cases"][case_id]["documents"][document_id]
        document.update(changes)
        _write(data)
        return document
