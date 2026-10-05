from __future__ import annotations

from pathlib import Path
from typing import Iterable

from fastapi import UploadFile


ALLOWED_TYPES = {
    "application/pdf": ".pdf",
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
}
EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg"}


class UploadValidationError(ValueError):
    pass


def safe_filename(filename: str | None, fallback: str = "document") -> str:
    name = Path(filename or fallback).name.strip()
    if not name:
        name = fallback
    if len(name) > 180:
        stem = Path(name).stem[:160]
        suffix = Path(name).suffix[:12]
        name = f"{stem}{suffix}"
    return name


def sniff_content_type(content: bytes) -> str:
    if content.startswith(b"%PDF-"):
        return "application/pdf"
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    return ""


def validate_file_signature(
    filename: str,
    declared_type: str | None,
    content: bytes,
) -> str:
    suffix = Path(filename).suffix.casefold()
    if suffix not in EXTENSIONS:
        raise UploadValidationError(
            f"Unsupported file extension for {filename}. Use PDF, PNG or JPEG."
        )

    detected_type = sniff_content_type(content)
    if not detected_type:
        raise UploadValidationError(
            f"The file signature for {filename} is not a supported PDF, PNG or JPEG."
        )

    expected_suffix = ALLOWED_TYPES[detected_type]
    suffix_ok = suffix == expected_suffix or (
        detected_type == "image/jpeg" and suffix == ".jpeg"
    )
    if not suffix_ok:
        raise UploadValidationError(
            f"File extension does not match its detected content for {filename}."
        )

    declared = (declared_type or "").casefold()
    if declared and declared not in {"application/octet-stream", detected_type, "image/jpg"}:
        raise UploadValidationError(
            f"Content type does not match the file signature for {filename}."
        )

    return detected_type


async def read_limited(
    file: UploadFile,
    max_bytes: int,
    chunk_size: int = 1024 * 1024,
) -> bytes:
    parts: list[bytes] = []
    total = 0

    while True:
        chunk = await file.read(chunk_size)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise UploadValidationError(
                f"{file.filename or 'Document'} exceeds the {max_bytes // (1024 * 1024)} MB file limit."
            )
        parts.append(chunk)

    content = b"".join(parts)
    if not content:
        raise UploadValidationError(f"{file.filename or 'Document'} is empty")
    return content


def validate_case_batch(
    existing_document_count: int,
    existing_bytes: int,
    incoming_sizes: Iterable[int],
    max_documents: int,
    max_case_bytes: int,
) -> None:
    sizes = list(incoming_sizes)
    if existing_document_count + len(sizes) > max_documents:
        raise UploadValidationError(
            f"A case can contain at most {max_documents} documents."
        )

    total = existing_bytes + sum(sizes)
    if total > max_case_bytes:
        raise UploadValidationError(
            f"Case storage limit exceeded: maximum is {max_case_bytes // (1024 * 1024)} MB."
        )
