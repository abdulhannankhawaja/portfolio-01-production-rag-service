import hashlib
import io
import re
import zipfile
import zlib
from pathlib import Path
from typing import Any

import pymupdf
from docx import Document
from docx.opc.exceptions import PackageNotFoundError
from lxml.etree import XMLSyntaxError
from pptx import Presentation
from pptx.exc import PackageNotFoundError as PptxPackageNotFoundError


MAX_PAGES = 300
MAX_CHARS = 1_500_000
MAX_OFFICE_MEMBERS = 5_000
MAX_OFFICE_UNCOMPRESSED_BYTES = 20_000_000


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def extract_pdf(content: bytes) -> list[tuple[int, str]]:
    if b"%PDF-" not in content[:1024]:
        raise ValueError("Invalid PDF file")
    pages: list[tuple[int, str]] = []
    try:
        with pymupdf.open(stream=content, filetype="pdf") as document:
            if document.needs_pass:
                raise ValueError("Encrypted PDFs are not supported")
            if len(document) > MAX_PAGES:
                raise ValueError("PDF has too many pages")
            for number, page in enumerate(document, start=1):
                text = page.get_text("text").strip()
                if text:
                    pages.append((number, text))
    except (pymupdf.FileDataError, pymupdf.EmptyFileError) as exc:
        raise ValueError("Invalid PDF file") from exc
    return pages


def _validate_office_archive(
    content: bytes,
    required_members: set[str],
    file_type: str,
) -> None:
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            members = archive.infolist()
            if len(members) > MAX_OFFICE_MEMBERS:
                raise ValueError(f"{file_type} archive contains too many files")
            if sum(member.file_size for member in members) > MAX_OFFICE_UNCOMPRESSED_BYTES:
                raise ValueError(f"{file_type} archive expands beyond the supported size")
            if any(member.flag_bits & 0x1 for member in members):
                raise ValueError(f"Encrypted {file_type} files are not supported")
            names = [member.filename for member in members]
            if len(set(names)) != len(names) or not required_members.issubset(names):
                raise ValueError(f"Invalid {file_type} file")
            if archive.testzip() is not None:
                raise ValueError(f"Invalid {file_type} file")
    except (zipfile.BadZipFile, OSError, RuntimeError, EOFError, zlib.error) as exc:
        raise ValueError(f"Invalid {file_type} file") from exc


def extract_docx(content: bytes) -> list[tuple[None, str, str]]:
    _validate_office_archive(
        content,
        {"[Content_Types].xml", "word/document.xml"},
        "DOCX",
    )
    try:
        document = Document(io.BytesIO(content))
    except (
        zipfile.BadZipFile,
        KeyError,
        PackageNotFoundError,
        ValueError,
        UnicodeDecodeError,
        XMLSyntaxError,
    ) as exc:
        raise ValueError("Invalid DOCX file") from exc
    sections: list[tuple[None, str, str]] = []
    current_heading = ""
    for paragraph in document.paragraphs:
        text = paragraph.text.strip()
        if not text:
            continue
        if paragraph.style and paragraph.style.name.startswith("Heading"):
            current_heading = text
        sections.append((None, text, current_heading))
    for table in document.tables:
        for row in table.rows:
            row_text = " | ".join(cell.text.strip() for cell in row.cells)
            if row_text.strip(" |"):
                sections.append((None, row_text, current_heading))
    return sections


def extract_pptx(content: bytes) -> list[tuple[int, str, None]]:
    _validate_office_archive(
        content,
        {"[Content_Types].xml", "ppt/presentation.xml"},
        "PPTX",
    )
    try:
        presentation = Presentation(io.BytesIO(content))
        slide_count = len(presentation.slides)
    except (
        zipfile.BadZipFile,
        KeyError,
        PptxPackageNotFoundError,
        ValueError,
        UnicodeDecodeError,
        XMLSyntaxError,
    ) as exc:
        raise ValueError("Invalid PPTX file") from exc
    if slide_count > MAX_PAGES:
        raise ValueError("PPTX has too many slides")

    try:
        slides: list[tuple[int, str, None]] = []
        for number, slide in enumerate(presentation.slides, start=1):
            slide_text = []
            for shape in slide.shapes:
                if shape.has_text_frame and shape.text.strip():
                    slide_text.append(shape.text.strip())
                if shape.has_table:
                    for row in shape.table.rows:
                        row_text = " | ".join(cell.text.strip() for cell in row.cells)
                        if row_text.strip(" |"):
                            slide_text.append(row_text)
            if slide_text:
                slides.append((number, "\n".join(slide_text), None))
    except (
        zipfile.BadZipFile,
        KeyError,
        ValueError,
        UnicodeDecodeError,
        XMLSyntaxError,
    ) as exc:
        raise ValueError("Invalid PPTX file") from exc
    return slides


def extract_plain_text(content: bytes) -> list[tuple[None, str, None]]:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("Text files must use UTF-8 encoding") from exc
    if any(
        (ord(character) < 32 and character not in "\t\n\r\f")
        or ord(character) == 127
        for character in text
    ):
        raise ValueError("Text file contains unsupported control characters")
    return [(None, text, None)] if text.strip() else []


def extract_text(content: bytes, filename: str) -> list[tuple]:
    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf":
        return extract_pdf(content)
    if suffix == ".docx":
        return extract_docx(content)
    if suffix == ".pptx":
        return extract_pptx(content)
    if suffix in {".txt", ".md"}:
        return extract_plain_text(content)
    raise ValueError("Unsupported file type")


def clean_text(text: str) -> str:
    text = re.sub(r"[^\S\n]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _token_offsets(text: str, tokenizer: Any | None) -> list[tuple[int, int]]:
    if tokenizer is None:
        return [(match.start(), match.end()) for match in re.finditer(r"\S+", text)]
    encoded = tokenizer(
        text,
        add_special_tokens=False,
        return_offsets_mapping=True,
        truncation=False,
        max_length=MAX_CHARS,
    )
    return [
        (int(start), int(end))
        for start, end in encoded["offset_mapping"]
        if end > start
    ]


def _recursive_boundary(
    text: str,
    start: int,
    end: int,
    separators: tuple[str, ...],
) -> int:
    if not separators:
        return end
    boundary = text.rfind(separators[0], start + 1, end)
    if boundary > start:
        return boundary + len(separators[0])
    return _recursive_boundary(text, start, end, separators[1:])


def split_text(
    pages: list[tuple],
    chunk_size: int,
    overlap: int,
    tokenizer: Any | None = None,
) -> list[dict]:
    if chunk_size < 1 or overlap < 0 or overlap >= chunk_size:
        raise ValueError("Chunk size must be positive and overlap smaller than chunk size")
    chunks: list[dict] = []
    chunk_index = 0
    total_chars = 0
    for item in pages:
        page = item[0]
        text = item[1]
        section = item[2] if len(item) > 2 else None
        text = clean_text(text)
        total_chars += len(text)
        if total_chars > MAX_CHARS:
            raise ValueError("Document text is too large")
        offsets = _token_offsets(text, tokenizer)
        start_token = 0
        while start_token < len(offsets):
            end_token = min(start_token + chunk_size, len(offsets))
            char_start = offsets[start_token][0]
            char_end = offsets[end_token - 1][1]
            if end_token < len(offsets):
                candidate_end = _recursive_boundary(
                    text,
                    char_start,
                    char_end,
                    ("\n\n", "\n", ". ", " "),
                )
                token_end = start_token + 1
                while (
                    token_end < end_token
                    and offsets[token_end][1] <= candidate_end
                ):
                    token_end += 1
                if token_end > start_token:
                    end_token = token_end
                    char_end = offsets[end_token - 1][1]
            chunk = clean_text(text[char_start:char_end])
            if chunk:
                chunks.append({
                    "text": chunk,
                    "page": page,
                    "section": section,
                    "chunk_index": chunk_index,
                })
                chunk_index += 1
            if end_token == len(offsets):
                break
            start_token = max(start_token + 1, end_token - overlap)
    return chunks
