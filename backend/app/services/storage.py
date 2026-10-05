from __future__ import annotations

import io
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import BinaryIO, Iterator

from app.core.config import Settings


def _settings() -> Settings:
    from app.core.config import get_settings
    return get_settings()


def _backend() -> str:
    return _settings().document_storage_backend.casefold()


def _s3_client():
    import boto3

    settings = _settings()
    missing = [
        name
        for name, value in (
            ("DOCUMENT_STORAGE_BUCKET", settings.document_storage_bucket),
            ("DOCUMENT_STORAGE_ACCESS_KEY", settings.document_storage_access_key),
            ("DOCUMENT_STORAGE_SECRET_KEY", settings.document_storage_secret_key),
        )
        if not value
    ]
    if missing:
        raise RuntimeError(
            "S3 document storage is missing required settings: " + ", ".join(missing)
        )

    return boto3.client(
        "s3",
        endpoint_url=settings.document_storage_endpoint_url or None,
        region_name=settings.document_storage_region,
        aws_access_key_id=settings.document_storage_access_key,
        aws_secret_access_key=settings.document_storage_secret_key,
    )


def _object_key(case_id: str, document_id: str, filename: str) -> str:
    safe_name = Path(filename).name or "document"
    return f"cases/{case_id}/documents/{document_id}/{safe_name}"


def _local_path(case_id: str, document_id: str, filename: str) -> Path:
    from app.services.case_store import UPLOADS

    safe_name = Path(filename).name or "document"
    folder = UPLOADS / case_id
    folder.mkdir(parents=True, exist_ok=True)
    return folder / f"{document_id}_{safe_name}"


def put_document(
    case_id: str,
    document_id: str,
    filename: str,
    content: bytes,
    content_type: str,
) -> str:
    backend = _backend()
    if backend == "local":
        path = _local_path(case_id, document_id, filename)
        path.write_bytes(content)
        return str(path)

    if backend != "s3":
        raise RuntimeError(f"Unsupported DOCUMENT_STORAGE_BACKEND: {backend}")

    settings = _settings()
    key = _object_key(case_id, document_id, filename)
    _s3_client().put_object(
        Bucket=settings.document_storage_bucket,
        Key=key,
        Body=content,
        ContentType=content_type,
    )
    return f"s3://{settings.document_storage_bucket}/{key}"


def delete_document(storage_ref: str) -> None:
    if storage_ref.startswith("s3://"):
        bucket_and_key = storage_ref[5:]
        bucket, _, key = bucket_and_key.partition("/")
        if bucket and key:
            _s3_client().delete_object(Bucket=bucket, Key=key)
        return

    Path(storage_ref).unlink(missing_ok=True)


def exists(storage_ref: str) -> bool:
    if storage_ref.startswith("s3://"):
        bucket_and_key = storage_ref[5:]
        bucket, _, key = bucket_and_key.partition("/")
        if not bucket or not key:
            return False
        try:
            _s3_client().head_object(Bucket=bucket, Key=key)
            return True
        except Exception as exc:
            error_code = getattr(exc, "response", {}).get("Error", {}).get("Code")
            if error_code in {"404", "NoSuchKey", "NotFound"}:
                return False
            raise

    return Path(storage_ref).is_file()


def read_bytes(storage_ref: str) -> bytes:
    if storage_ref.startswith("s3://"):
        bucket_and_key = storage_ref[5:]
        bucket, _, key = bucket_and_key.partition("/")
        if not bucket or not key:
            raise FileNotFoundError(storage_ref)
        response = _s3_client().get_object(Bucket=bucket, Key=key)
        return response["Body"].read()

    return Path(storage_ref).read_bytes()


def open_binary(storage_ref: str) -> BinaryIO:
    if storage_ref.startswith("s3://"):
        return io.BytesIO(read_bytes(storage_ref))
    return Path(storage_ref).open("rb")


@contextmanager
def materialize(storage_ref: str) -> Iterator[Path]:
    if not storage_ref.startswith("s3://"):
        path = Path(storage_ref)
        if not path.is_file():
            raise FileNotFoundError(storage_ref)
        yield path
        return

    suffix = Path(storage_ref.split("?", 1)[0]).suffix
    temporary = tempfile.NamedTemporaryFile(
        prefix="bhoomilens-",
        suffix=suffix,
        delete=False,
    )
    temporary_path = Path(temporary.name)
    try:
        with temporary:
            temporary.write(read_bytes(storage_ref))
        yield temporary_path
    finally:
        temporary_path.unlink(missing_ok=True)
