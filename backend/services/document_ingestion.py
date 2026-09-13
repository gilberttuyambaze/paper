"""Multi-stage document ingestion orchestrator.

Executes the cascading extraction pipeline:
Native PDF text -> Quality Check -> Selective OCR -> Targeted Vision Fallback -> Layout & Question Parsing.
"""

from __future__ import annotations

import io
import json
import logging
from dataclasses import dataclass, field
from typing import Any

from services.document_classifier import DocumentClassifier, DocumentClassification, DocumentType, PageType
from services.document_structure import DocumentStructureParser, DocumentStructure, StructuredUnit
from services.ocr.factory import get_ocr_provider
from services.ocr.image_preprocessor import extract_page_image_bytes, render_pdf_page_to_bytes
from services.ocr.vision_provider import VisionAIOCRProvider

logger = logging.getLogger(__name__)


@dataclass
class ExtractedPageData:
    page_number: int
    text: str
    extraction_method: str  # "native" | "ocr" | "vision" | "failed"
    confidence: float
    is_scanned: bool = False
    image_bytes: bytes | None = None
    structured_units: list[StructuredUnit] = field(default_factory=list)


@dataclass
class DocumentIngestionResult:
    document_id: int | None
    document_type: DocumentType
    extraction_status: str  # "completed" | "partial" | "failed"
    extraction_method: str  # "native" | "ocr" | "hybrid" | "vision"
    extraction_quality: float  # 0.0 to 1.0
    ocr_used: bool
    page_count: int
    failed_pages: list[int]
    pages: list[ExtractedPageData]
    structure: DocumentStructure
    combined_text: str


class DocumentIngestionService:
    """Orchestrates multi-stage extraction and structure parsing for past paper PDFs."""

    @classmethod
    async def process_pdf(
        cls,
        pdf_bytes: bytes,
        *,
        document_id: int | None = None,
        context_hint: str | None = None,
        max_pages: int = 150,
    ) -> DocumentIngestionResult:
        """Processes a PDF through the full multi-stage ingestion pipeline."""
        from pypdf import PdfReader

        if not pdf_bytes:
            empty_structure = DocumentStructure(title=None, sections=[], units=[], detected_questions=[], overall_confidence=0.0)
            return DocumentIngestionResult(
                document_id=document_id,
                document_type=DocumentType.FAILED_PDF,
                extraction_status="failed",
                extraction_method="failed",
                extraction_quality=0.0,
                ocr_used=False,
                page_count=0,
                failed_pages=[],
                pages=[],
                structure=empty_structure,
                combined_text="",
            )

        # Step 1: Document Classification
        classification = DocumentClassifier.classify_pdf_bytes(pdf_bytes, max_pages=max_pages)

        try:
            reader = PdfReader(io.BytesIO(pdf_bytes))
            page_objs = reader.pages[:max_pages]
        except Exception as exc:
            logger.warning("Failed opening PDF reader in ingestion: %s", exc)
            page_objs = []

        extracted_pages: list[ExtractedPageData] = []
        ocr_used_flag = False
        failed_pages_list: list[int] = []
        methods_used: set[str] = set()

        ocr_provider = None

        for index, page_obj in enumerate(page_objs, start=1):
            # Locate corresponding page classification
            page_class = (
                classification.pages[index - 1]
                if index - 1 < len(classification.pages)
                else DocumentClassifier.classify_page(page_obj, index)
            )

            # High-confidence native text
            if page_class.page_type == PageType.TEXT and page_class.quality_score >= 0.70:
                raw_text = page_class.raw_text or page_obj.extract_text() or ""
                extracted_pages.append(
                    ExtractedPageData(
                        page_number=index,
                        text=raw_text.strip(),
                        extraction_method="native",
                        confidence=page_class.quality_score,
                        is_scanned=False,
                    )
                )
                methods_used.add("native")
                continue

            # Scanned, mixed, or poor-quality native page: trigger OCR
            image_bytes = render_pdf_page_to_bytes(pdf_bytes, index, scale=2.0)
            if not image_bytes:
                image_bytes = extract_page_image_bytes(page_obj)

            if not image_bytes and page_class.raw_text and len(page_class.raw_text) > 40:
                # Retain native text if no image could be rendered/extracted
                extracted_pages.append(
                    ExtractedPageData(
                        page_number=index,
                        text=page_class.raw_text,
                        extraction_method="native",
                        confidence=page_class.quality_score,
                        is_scanned=False,
                    )
                )
                methods_used.add("native")
                continue

            if image_bytes:
                if ocr_provider is None:
                    ocr_provider = await get_ocr_provider()

                ocr_result = await ocr_provider.extract_page(
                    image_bytes,
                    index,
                    context_hint=context_hint,
                )
                ocr_used_flag = True

                # Step 3: If OCR confidence is low (< 0.50) and vision is available, use targeted Vision AI
                if ocr_result.confidence < 0.50:
                    vision_prov = VisionAIOCRProvider()
                    if await vision_prov.is_available() and ocr_provider.name != "vision_ai":
                        logger.info("OCR confidence low (%s) on page %s; applying targeted Vision fallback", ocr_result.confidence, index)
                        vision_result = await vision_prov.extract_page(image_bytes, index, context_hint=context_hint)
                        if vision_result.confidence > ocr_result.confidence:
                            ocr_result = vision_result

                if ocr_result.text.strip():
                    method_tag = "vision" if "vision" in ocr_result.provider else "ocr"
                    extracted_pages.append(
                        ExtractedPageData(
                            page_number=index,
                            text=ocr_result.text.strip(),
                            extraction_method=method_tag,
                            confidence=ocr_result.confidence,
                            is_scanned=True,
                            image_bytes=image_bytes,
                        )
                    )
                    methods_used.add(method_tag)
                else:
                    # OCR produced no text on this page
                    failed_pages_list.append(index)
                    extracted_pages.append(
                        ExtractedPageData(
                            page_number=index,
                            text="",
                            extraction_method="failed",
                            confidence=0.0,
                            is_scanned=True,
                            image_bytes=image_bytes,
                        )
                    )
            else:
                # Empty unreadable page
                failed_pages_list.append(index)
                extracted_pages.append(
                    ExtractedPageData(
                        page_number=index,
                        text="",
                        extraction_method="failed",
                        confidence=0.0,
                        is_scanned=False,
                    )
                )

        # Step 4: Parse layout and question structure
        page_tuples = [
            (p.page_number, p.text, p.extraction_method, p.confidence)
            for p in extracted_pages
            if p.text.strip()
        ]
        structure = DocumentStructureParser.parse_document(page_tuples)

        total_pages = len(page_objs)
        successful_pages = [p for p in extracted_pages if p.text.strip()]
        avg_quality = (
            sum(p.confidence for p in extracted_pages) / max(1, total_pages)
            if total_pages
            else 0.0
        )

        if not successful_pages:
            status = "failed"
        elif len(failed_pages_list) > 0 or avg_quality < 0.65:
            status = "partial"
        else:
            status = "completed"

        if len(methods_used) > 1:
            overall_method = "hybrid"
        elif "ocr" in methods_used:
            overall_method = "ocr"
        elif "vision" in methods_used:
            overall_method = "vision"
        else:
            overall_method = "native"

        combined_text = "\n\n".join(
            f"[Page {p.page_number}]\n{p.text}"
            for p in extracted_pages
            if p.text.strip()
        )

        return DocumentIngestionResult(
            document_id=document_id,
            document_type=classification.document_type,
            extraction_status=status,
            extraction_method=overall_method,
            extraction_quality=round(avg_quality, 2),
            ocr_used=ocr_used_flag,
            page_count=total_pages,
            failed_pages=failed_pages_list,
            pages=extracted_pages,
            structure=structure,
            combined_text=combined_text,
        )
