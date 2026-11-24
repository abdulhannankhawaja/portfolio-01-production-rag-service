import hashlib
import io
import re
import zipfile
from pathlib import Path

import pymupdf
from docx import Document
from docx.opc.exceptions import PackageNotFoundError


MAX_PAGES = 300
MAX_CHARS = 1_500_000


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def extract_pdf(content: bytes) -> list[tuple[int, str]]:
    pages: list[tuple[int, str]] = []
    try:
        with pymupdf.open(stream=content, filetype="pdf") as document:
            if len(document) > MAX_PAGES:
                raise ValueError("PDF has too many pages")
            for number, page in enumerate(document, start=1):
                text = page.get_text("text").strip()
                if text:
                    pages.append((number, text))
    except pymupdf.FileDataError as exc:
        raise ValueError("Invalid PDF file") from exc
    return pages


def extract_docx(content: bytes) -> list[tuple[int, str, str]]:
    try:
        document = Document(io.BytesIO(content))
    except (zipfile.BadZipFile, KeyError, PackageNotFoundError) as exc:
        raise ValueError("Invalid DOCX file") from exc
    sections: list[tuple[int, str, str]] = []
    current_heading = ""
    for paragraph in document.paragraphs:
        text = paragraph.text.strip()
        if not text:
            continue
        if paragraph.style and paragraph.style.name.startswith("Heading"):
            current_heading = text
        sections.append((1, text, current_heading))
    for table in document.tables:
        for row in table.rows:
            sections.append((1, " | ".join(cell.text.strip() for cell in row.cells), current_heading))
    return sections


def extract_text(content: bytes, filename: str) -> list[tuple]:
    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf":
        return extract_pdf(content)
    if suffix == ".docx":
        return extract_docx(content)
    raise ValueError("Unsupported file type")


def clean_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def split_text(pages: list[tuple], chunk_size: int, overlap: int) -> list[dict]:
    chunks: list[dict] = []
    chunk_index = 0
    for item in pages:
        page = item[0]
        text = item[1]
        section = item[2] if len(item) > 2 else None
        text = clean_text(text)
        if len(text) > MAX_CHARS:
            raise ValueError("Document text is too large")
        start = 0
        while start < len(text):
            end = min(start + chunk_size, len(text))
            chunk = clean_text(text[start:end])
            if chunk:
                chunks.append({
                    "text": chunk,
                    "page": page,
                    "section": section,
                    "chunk_index": chunk_index,
                })
                chunk_index += 1
            if end == len(text):
                break
            start = max(start + 1, end - overlap)
    return chunks
