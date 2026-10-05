from pathlib import Path
from typing import NamedTuple

from pypdf import PdfReader, PdfWriter


MAX_PDF_PAGES_PER_CHUNK = 10
MAX_FILE_BYTES = 200 * 1024 * 1024


class PDFChunk(NamedTuple):
    path: Path
    start_page: int
    end_page: int


def validate_size(path: Path) -> None:
    if path.stat().st_size > MAX_FILE_BYTES:
        raise ValueError("Document exceeds the 200 MB processing limit.")


def split_pdf(path: Path, output_dir: Path) -> list[PDFChunk]:
    validate_size(path)
    reader = PdfReader(str(path))
    page_count = len(reader.pages)

    if page_count <= MAX_PDF_PAGES_PER_CHUNK:
        return [PDFChunk(path=path, start_page=1, end_page=page_count)]

    output_dir.mkdir(parents=True, exist_ok=True)
    chunks: list[PDFChunk] = []

    for start in range(0, page_count, MAX_PDF_PAGES_PER_CHUNK):
        end = min(start + MAX_PDF_PAGES_PER_CHUNK, page_count)
        writer = PdfWriter()
        for page_index in range(start, end):
            writer.add_page(reader.pages[page_index])

        chunk_path = output_dir / f"{path.stem}_p{start + 1}-{end}.pdf"
        with chunk_path.open("wb") as handle:
            writer.write(handle)

        chunks.append(PDFChunk(path=chunk_path, start_page=start + 1, end_page=end))

    return chunks
