"""Multi-stage document ingestion orchestrator.

Executes the cascading extraction pipeline:
Native PDF text -> Quality Check -> Selective OCR -> Targeted Vision Fallback -> Layout & Question Parsing.
"""

from __future__ import annotations

import io
import json
import logging
from time import monotonic
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from services.document_classifier import DocumentClassifier, DocumentClassification, DocumentType, PageType
from services.document_structure import DocumentStructureParser, DocumentStructure, StructuredUnit
from services.ocr.factory import get_ocr_provider
from services.ocr.image_preprocessor import PdfPageRenderer, extract_page_image_bytes
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
    metrics: dict[str, Any] = field(default_factory=dict)


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
        progress_callback: Callable[[dict], Awaitable[None]] | None = None,
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

        async def report(**event) -> None:
            if progress_callback:
                await progress_callback(event)

        started = monotonic()
        # Step 1: Document Classification
        classification_started = monotonic()
        classification = DocumentClassifier.classify_pdf_bytes(pdf_bytes, max_pages=max_pages)
        classification_duration_ms = round((monotonic() - classification_started) * 1000)

        try:
            reader = PdfReader(io.BytesIO(pdf_bytes))
            page_objs = reader.pages[:max_pages]
        except Exception as exc:
            logger.warning("Failed opening PDF reader in ingestion: %s", exc)
            page_objs = []

        await report(
            stage="EXTRACTING",
            message="Extracting native text and identifying scanned pages.",
            pages_total=len(page_objs),
            pages_completed=0,
            percent_complete=12,
        )

        extracted_pages: list[ExtractedPageData] = []
        ocr_used_flag = False
        failed_pages_list: list[int] = []
        methods_used: set[str] = set()

        ocr_provider = None
        vision_provider = None
        page_renderer = PdfPageRenderer(pdf_bytes)
        metrics: dict[str, Any] = {
            "classification_duration_ms": classification_duration_ms,
            "page_reader_duration_ms": 0,
            "render_duration_ms": 0,
            "ocr_duration_ms": 0,
            "vision_duration_ms": 0,
            "structure_duration_ms": 0,
            "native_pages": 0,
            "scanned_pages": 0,
            "mixed_pages": 0,
            "failed_pages": 0,
            "ocr_calls": 0,
            "vision_calls": 0,
            "page_metrics": [],
        }

        for index, page_obj in enumerate(page_objs, start=1):
            page_started = monotonic()
            logger.info("PAGE_PROCESSING_START paper_id=%s page=%s total_pages=%s", document_id, index, len(page_objs))
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
                logger.info("PAGE_NATIVE_EXTRACTION paper_id=%s page=%s text_length=%s duration_ms=%s usable=true", document_id, index, len(raw_text.strip()), round((monotonic() - page_started) * 1000))
                metrics["native_pages"] += 1
                metrics["page_metrics"].append({"page": index, "classification": page_class.page_type.value, "method": "native", "duration_ms": round((monotonic() - page_started) * 1000), "quality": page_class.quality_score})
                await report(stage="EXTRACTING", message=f"Extracted native text — {index} / {len(page_objs)} pages.", pages_total=len(page_objs), pages_completed=index, percent_complete=12 + int(58 * index / max(1, len(page_objs))))
                continue

            # Scanned, mixed, or poor-quality native page: trigger OCR
            render_started = monotonic()
            image_bytes = page_renderer.render(index, scale=2.0)
            render_duration_ms = round((monotonic() - render_started) * 1000)
            metrics["render_duration_ms"] += render_duration_ms
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
                metrics["native_pages"] += 1
                metrics["page_metrics"].append({"page": index, "classification": page_class.page_type.value, "method": "native_render_unavailable", "render_duration_ms": render_duration_ms, "duration_ms": round((monotonic() - page_started) * 1000), "quality": page_class.quality_score})
                await report(stage="EXTRACTING", message=f"Retained available native text — {index} / {len(page_objs)} pages.", pages_total=len(page_objs), pages_completed=index, percent_complete=12 + int(58 * index / max(1, len(page_objs))))
                continue

            if image_bytes:
                if ocr_provider is None:
                    ocr_provider = await get_ocr_provider()

                logger.info("PAGE_OCR_START paper_id=%s page=%s", document_id, index)
                ocr_started = monotonic()
                ocr_result = await ocr_provider.extract_page(
                    image_bytes,
                    index,
                    context_hint=context_hint,
                )
                ocr_duration_ms = round((monotonic() - ocr_started) * 1000)
                metrics["ocr_duration_ms"] += ocr_duration_ms
                metrics["ocr_calls"] += 1
                ocr_used_flag = True

                # Step 3: If OCR confidence is low (< 0.50) and vision is available, use targeted Vision AI
                if ocr_result.confidence < 0.50:
                    if vision_provider is None:
                        vision_provider = VisionAIOCRProvider()
                    if await vision_provider.is_available() and ocr_provider.name != "vision_ai":
                        logger.info("OCR confidence low (%s) on page %s; applying targeted Vision fallback", ocr_result.confidence, index)
                        vision_started = monotonic()
                        vision_result = await vision_provider.extract_page(image_bytes, index, context_hint=context_hint)
                        metrics["vision_duration_ms"] += round((monotonic() - vision_started) * 1000)
                        metrics["vision_calls"] += 1
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
                    logger.info("PAGE_OCR_SUCCESS paper_id=%s page=%s text_length=%s confidence=%s duration_ms=%s", document_id, index, len(ocr_result.text.strip()), ocr_result.confidence, ocr_duration_ms)
                    if page_class.page_type == PageType.MIXED:
                        metrics["mixed_pages"] += 1
                    else:
                        metrics["scanned_pages"] += 1
                    metrics["page_metrics"].append({"page": index, "classification": page_class.page_type.value, "method": method_tag, "render_duration_ms": render_duration_ms, "ocr_duration_ms": ocr_duration_ms, "duration_ms": round((monotonic() - page_started) * 1000), "quality": ocr_result.confidence})
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
                    metrics["failed_pages"] += 1
                    logger.warning("PAGE_OCR_FAILED paper_id=%s page=%s error=empty_ocr_result duration_ms=%s", document_id, index, ocr_duration_ms)
                    metrics["page_metrics"].append({"page": index, "classification": page_class.page_type.value, "method": "ocr_failed", "render_duration_ms": render_duration_ms, "ocr_duration_ms": ocr_duration_ms, "duration_ms": round((monotonic() - page_started) * 1000), "quality": 0.0})
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
                metrics["failed_pages"] += 1
                metrics["page_metrics"].append({"page": index, "classification": page_class.page_type.value, "method": "render_failed", "render_duration_ms": render_duration_ms, "duration_ms": round((monotonic() - page_started) * 1000), "quality": 0.0})

            await report(stage="OCR_PROCESSING", message=f"Processing scanned content — {index} / {len(page_objs)} pages.", pages_total=len(page_objs), pages_completed=index, percent_complete=12 + int(58 * index / max(1, len(page_objs))))
            page_result = extracted_pages[-1]
            logger.info("PAGE_PROCESSING_COMPLETE paper_id=%s page=%s status=%s method=%s", document_id, index, "SUCCESS" if page_result.text.strip() else "FAILED", page_result.extraction_method.upper())

        page_renderer.close()

        # Step 4: Parse layout and question structure
        page_tuples = [
            (p.page_number, p.text, p.extraction_method, p.confidence)
            for p in extracted_pages
            if p.text.strip()
        ]
        await report(stage="STRUCTURING", message="Reconstructing reading order, sections, and questions.", pages_total=len(page_objs), pages_completed=len(page_objs), percent_complete=72)
        structure_started = monotonic()
        structure = DocumentStructureParser.parse_document(page_tuples)
        metrics["structure_duration_ms"] = round((monotonic() - structure_started) * 1000)

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
            metrics={**metrics, "total_duration_ms": round((monotonic() - started) * 1000)},
        )
