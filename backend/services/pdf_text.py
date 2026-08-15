"""Safe, bounded PDF text extraction used for upload assistance and study context."""

from __future__ import annotations

import io
import re
from dataclasses import dataclass


def extract_pdf_text(file_bytes: bytes, *, max_pages: int = 12, max_chars: int = 48_000) -> str:
    """Extract readable text without retaining the uploaded document in memory longer than needed."""
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(file_bytes))
        pages = []
        for page in reader.pages[:max_pages]:
            pages.append(page.extract_text() or "")
            if sum(len(part) for part in pages) >= max_chars:
                break
        text = "\n".join(pages)
    except Exception:
        # Scanned/encrypted PDFs need OCR. Returning an empty result is safer than
        # treating compressed PDF bytes as text and making incorrect suggestions.
        text = ""

    return re.sub(r"\s+", " ", text).strip()[:max_chars]


@dataclass(frozen=True)
class PdfPageText:
    page_number: int
    text: str


def extract_pdf_pages(file_bytes: bytes, *, max_pages: int = 200, max_chars_per_page: int = 20_000) -> list[PdfPageText]:
    """Extract page-aware text. Empty/scanned pages are omitted without failing indexing."""
    try:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(file_bytes))
        result = []
        for index, page in enumerate(reader.pages[:max_pages], start=1):
            text = re.sub(r"\s+", " ", page.extract_text() or "").strip()[:max_chars_per_page]
            if text:
                result.append(PdfPageText(page_number=index, text=text))
        return result
    except Exception:
        return []


def chunk_page_text(text: str, *, chunk_size: int = 900, overlap: int = 160) -> list[str]:
    """Create readable overlapping passages while preserving the page boundary."""
    normalized = re.sub(r"\s+", " ", text).strip()
    if len(normalized) < 40:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(normalized):
        end = min(len(normalized), start + chunk_size)
        if end < len(normalized):
            boundary = max(normalized.rfind(". ", start, end), normalized.rfind("? ", start, end), normalized.rfind("! ", start, end), normalized.rfind(" ", start, end))
            if boundary > start + chunk_size // 2:
                end = boundary + 1
        chunk = normalized[start:end].strip()
        if len(chunk) >= 40:
            chunks.append(chunk)
        if end >= len(normalized):
            break
        start = max(end - overlap, start + 1)
    return chunks
