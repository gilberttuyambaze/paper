"""Safe, bounded PDF text extraction used for upload assistance and study context."""

from __future__ import annotations

import io
import re
from dataclasses import dataclass


def extract_pdf_text(file_bytes: bytes, *, max_pages: int = 12, max_chars: int = 48_000) -> str:
    """Extract readable text while preserving line and paragraph structure."""
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(file_bytes))
        pages = []
        for page in reader.pages[:max_pages]:
            page_text = page.extract_text() or ""
            # Clean up excessive blank lines while preserving meaningful line breaks
            cleaned = re.sub(r"\r\n|\r", "\n", page_text)
            cleaned = re.sub(r"[ \t]+", " ", cleaned)
            cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
            if cleaned:
                pages.append(cleaned)
            if sum(len(part) for part in pages) >= max_chars:
                break
        text = "\n\n".join(pages)
    except Exception:
        # Scanned/encrypted PDFs need OCR. Returning an empty result is safer than
        # treating compressed PDF bytes as text.
        text = ""

    return text.strip()[:max_chars]


@dataclass(frozen=True)
class PdfPageText:
    page_number: int
    text: str


def extract_pdf_pages(file_bytes: bytes, *, max_pages: int = 200, max_chars_per_page: int = 20_000) -> list[PdfPageText]:
    """Extract page-aware text preserving line breaks. Empty/scanned pages are omitted without failing indexing."""
    try:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(file_bytes))
        result = []
        for index, page in enumerate(reader.pages[:max_pages], start=1):
            raw = page.extract_text() or ""
            cleaned = re.sub(r"\r\n|\r", "\n", raw)
            cleaned = re.sub(r"[ \t]+", " ", cleaned)
            cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()[:max_chars_per_page]
            if cleaned:
                result.append(PdfPageText(page_number=index, text=cleaned))
        return result
    except Exception:
        return []


def chunk_page_text(text: str, *, chunk_size: int = 1000, overlap: int = 160) -> list[str]:
    """Create readable passages while preserving sentence and paragraph boundaries."""
    normalized = text.strip()
    if len(normalized) < 40:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(normalized):
        end = min(len(normalized), start + chunk_size)
        if end < len(normalized):
            # Prefer paragraph breaks (\n\n), then sentence endings (. , ? , !), then space
            para_boundary = normalized.rfind("\n\n", start, end)
            if para_boundary > start + chunk_size // 2:
                end = para_boundary + 2
            else:
                boundary = max(
                    normalized.rfind(".\n", start, end),
                    normalized.rfind("?\n", start, end),
                    normalized.rfind(". ", start, end),
                    normalized.rfind("? ", start, end),
                    normalized.rfind("! ", start, end),
                    normalized.rfind("\n", start, end),
                    normalized.rfind(" ", start, end),
                )
                if boundary > start + chunk_size // 2:
                    end = boundary + 1
        chunk = normalized[start:end].strip()
        if len(chunk) >= 30:
            chunks.append(chunk)
        if end >= len(normalized):
            break
        start = max(end - overlap, start + 1)
    return chunks
