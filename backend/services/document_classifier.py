"""PDF document and page-level classification service.

Distinguishes native text pages, scanned image pages, mixed pages, and failed pages
using measurable signals (character density, word count, embedded images, and character validity).
"""

from __future__ import annotations

import io
import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class PageType(str, Enum):
    TEXT = "text"
    SCANNED = "scanned"
    MIXED = "mixed"
    FAILED = "failed"


class DocumentType(str, Enum):
    TEXT_PDF = "text_pdf"
    SCANNED_PDF = "scanned_pdf"
    MIXED_PDF = "mixed_pdf"
    FAILED_PDF = "failed_pdf"


@dataclass
class PageClassification:
    page_number: int
    page_type: PageType
    char_count: int
    word_count: int
    image_count: int
    image_area_ratio: float
    suspicious_char_ratio: float
    quality_score: float
    raw_text: str = ""
    has_equations: bool = False
    has_tables: bool = False


@dataclass
class DocumentClassification:
    document_type: DocumentType
    page_count: int
    overall_quality: float
    pages: list[PageClassification] = field(default_factory=list)
    scanned_pages: list[int] = field(default_factory=list)
    mixed_pages: list[int] = field(default_factory=list)
    failed_pages: list[int] = field(default_factory=list)
    suggested_method: str = "native"  # "native" | "ocr" | "hybrid"


class DocumentClassifier:
    """Classifies PDF documents and pages to determine optimal extraction strategy."""

    @staticmethod
    def classify_page(
        page_obj: Any,
        page_number: int,
        raw_text: str | None = None,
    ) -> PageClassification:
        """Classifies a single PDF page."""
        if raw_text is None:
            try:
                raw_text = page_obj.extract_text() or ""
            except Exception as exc:
                logger.debug("Failed to extract text on page %s: %s", page_number, exc)
                raw_text = ""

        clean_text = raw_text.strip()
        char_count = len(clean_text)
        words = clean_text.split()
        word_count = len(words)

        image_count = 0
        try:
            if hasattr(page_obj, "images"):
                image_count = len(page_obj.images)
        except Exception:
            image_count = 0

        # Calculate suspicious character ratio (replacement chars, unprintable control chars)
        suspicious_chars = len(re.findall(r"[\ufffd\x00-\x08\x0b\x0c\x0e-\x1f]", clean_text))
        suspicious_char_ratio = (suspicious_chars / max(1, char_count)) if char_count > 0 else 0.0

        # Estimate image area ratio based on page dimensions and image presence
        image_area_ratio = 0.0
        if image_count > 0:
            if char_count < 80:
                image_area_ratio = 0.95
            elif char_count < 300:
                image_area_ratio = 0.60
            else:
                image_area_ratio = min(0.40, image_count * 0.15)

        # Detect math / equation patterns
        has_equations = bool(re.search(r"(\b\d+\s*[\+\-\*\/\=]\s*\d+\b|\b[a-zA-Z]\s*\=\s*|\\[a-zA-Z]+|\b\d+\s*(?:kg|m\/s|m\^|km|cm|V|A|Hz|mol|Pa|N|J|W|Ω)\b)", clean_text))
        has_tables = bool(re.search(r"(\|[^\n]+\||\b(?:table|tab\.)\s*\d+\b|\t)", clean_text, re.IGNORECASE))

        # Scanner watermark / uninformative text check (e.g. "CamScanner", "Scanned by CamScanner")
        is_scanner_watermark = bool(re.search(r"^(?:camscanner|scanned\s+(?:by|with)\s+camscanner|vflat|tapscanner)$", clean_text.strip(), re.IGNORECASE))
        if is_scanner_watermark:
            char_count = 0
            word_count = 0

        # Classification logic:
        if is_scanner_watermark or (char_count < 60 and image_count >= 1):
            page_type = PageType.SCANNED
            quality_score = 0.05
        elif char_count < 15 and image_count == 0:
            page_type = PageType.FAILED
            quality_score = 0.0
        elif char_count < 25 and image_count == 0:
            page_type = PageType.SCANNED  # Likely scanned page where pypdf didn't find image object
            quality_score = 0.05
        elif image_count >= 1 and char_count < 350:
            page_type = PageType.SCANNED if char_count < 100 else PageType.MIXED
            quality_score = max(0.1, min(0.65, char_count / 500.0))
        elif image_count >= 1 and char_count >= 350:
            page_type = PageType.MIXED
            quality_score = max(0.6, 1.0 - suspicious_char_ratio - (image_area_ratio * 0.3))
        else:
            page_type = PageType.TEXT
            # High-confidence native text
            quality_score = max(0.2, min(1.0, 1.0 - (suspicious_char_ratio * 2.0)))

        return PageClassification(
            page_number=page_number,
            page_type=page_type,
            char_count=char_count,
            word_count=word_count,
            image_count=image_count,
            image_area_ratio=round(image_area_ratio, 2),
            suspicious_char_ratio=round(suspicious_char_ratio, 3),
            quality_score=round(quality_score, 2),
            raw_text=clean_text,
            has_equations=has_equations,
            has_tables=has_tables,
        )

    @classmethod
    def classify_pdf_bytes(cls, pdf_bytes: bytes, *, max_pages: int = 200) -> DocumentClassification:
        """Inspects all pages in a PDF and produces a structured document classification."""
        from pypdf import PdfReader

        try:
            reader = PdfReader(io.BytesIO(pdf_bytes))
            page_objs = reader.pages[:max_pages]
        except Exception as exc:
            logger.warning("PDF could not be parsed for classification: %s", exc)
            return DocumentClassification(
                document_type=DocumentType.FAILED_PDF,
                page_count=0,
                overall_quality=0.0,
                suggested_method="failed",
            )

        if not page_objs:
            return DocumentClassification(
                document_type=DocumentType.FAILED_PDF,
                page_count=0,
                overall_quality=0.0,
                suggested_method="failed",
            )

        pages = []
        scanned_pages = []
        mixed_pages = []
        failed_pages = []

        for index, page in enumerate(page_objs, start=1):
            classified = cls.classify_page(page, index)
            pages.append(classified)
            if classified.page_type == PageType.SCANNED:
                scanned_pages.append(index)
            elif classified.page_type == PageType.MIXED:
                mixed_pages.append(index)
            elif classified.page_type == PageType.FAILED:
                failed_pages.append(index)

        total_pages = len(pages)
        scanned_count = len(scanned_pages)
        mixed_count = len(mixed_pages)
        failed_count = len(failed_pages)
        text_count = total_pages - (scanned_count + mixed_count + failed_count)

        avg_quality = sum(p.quality_score for p in pages) / max(1, total_pages)

        if scanned_count == total_pages or (scanned_count + failed_count) >= total_pages * 0.8:
            doc_type = DocumentType.SCANNED_PDF
            suggested_method = "ocr"
        elif (scanned_count + mixed_count) > 0 and text_count > 0:
            doc_type = DocumentType.MIXED_PDF
            suggested_method = "hybrid"
        elif failed_count == total_pages:
            doc_type = DocumentType.FAILED_PDF
            suggested_method = "failed"
        else:
            doc_type = DocumentType.TEXT_PDF
            suggested_method = "native"

        return DocumentClassification(
            document_type=doc_type,
            page_count=total_pages,
            overall_quality=round(avg_quality, 2),
            pages=pages,
            scanned_pages=scanned_pages,
            mixed_pages=mixed_pages,
            failed_pages=failed_pages,
            suggested_method=suggested_method,
        )
