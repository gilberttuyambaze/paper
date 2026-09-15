from __future__ import annotations

import hashlib
import json
import logging
import asyncio
import os
from time import monotonic
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
import io

from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from models.papers import Papers, PaperPassage, PaperPageExtraction
from services.document_ingestion import DocumentIngestionService
from services.embeddings import EmbeddingService
from services.pdf_text import chunk_page_text
from services.storage import StorageService
from services.question_classification import QuestionIndexService

logger = logging.getLogger(__name__)
DEFAULT_DOWNLOAD_TIMEOUT_SECONDS = 90


def _validate_downloaded_pdf(pdf_bytes: bytes) -> tuple[bool, str | None, int | None]:
    """Verify that a storage response is an openable, non-empty PDF.

    Storage providers may successfully return an HTML error document or an
    empty object.  Treating either as an acquired PDF used to let an ingestion
    run reach the extractor with no pages and, in some cases, READY.
    """
    if not pdf_bytes:
        return False, "Original document download was empty.", None
    if b"%PDF-" not in pdf_bytes[:1024]:
        return False, "Downloaded original is not a PDF document.", None
    try:
        from pypdf import PdfReader
        page_count = len(PdfReader(io.BytesIO(pdf_bytes)).pages)
    except Exception:
        return False, "Downloaded original PDF could not be opened.", None
    if page_count < 1:
        return False, "Downloaded original PDF has no pages.", None
    return True, None, page_count


class PassageIndexService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def index_paper(
        self,
        paper: Papers,
        *,
        progress_callback: Callable[[dict], Awaitable[None]] | None = None,
    ) -> dict:
        async def report(**event) -> None:
            if progress_callback:
                await progress_callback(event)

        if not paper.file_key:
            return {"passages": 0, "embedded": 0, "ingestion_succeeded": False, "error": "Paper has no original file."}

        total_started = monotonic()
        # An embedding-only retry must never download or OCR an already
        # persisted document again.  Passages are the durable resume boundary.
        existing_passages = []
        if hasattr(self.db, "execute"):
            existing_passages = (await self.db.execute(select(PaperPassage).where(PaperPassage.paper_id == paper.id).order_by(PaperPassage.passage_index))).scalars().all()
        if existing_passages:
            logger.info("EMBEDDING_RETRY_START paper_id=%s passages=%s", paper.id, len(existing_passages))
            outcome = await self._embed_passages(existing_passages)
            paper.embedding_status = "READY" if outcome.vectors else "FAILED"
            paper.embedding_error = None if outcome.vectors else outcome.error_type
            paper.retrieval_mode = "HYBRID" if outcome.vectors else "KEYWORD_ONLY"
            await self.db.commit()
            logger.info("EMBEDDING_RETRY_COMPLETE paper_id=%s passages=%s embedded=%s status=%s", paper.id, len(existing_passages), len(outcome.vectors or []), paper.embedding_status)
            return {"passages": len(existing_passages), "embedded": len(outcome.vectors or []), "ingestion_succeeded": True, "metrics": {"embedding_resumed": True, "embedding_duration_ms": round((monotonic() - total_started) * 1000), "embedding_status": "ready" if outcome.vectors else "failed", "embedding_error": outcome.error_type, "embedding_provider": outcome.provider, "embedding_model": outcome.model}, "embedding_error": outcome.error_type}
        try:
            await report(stage="DOWNLOADING", message="Downloading the preserved original document.", percent_complete=3)
            # A storage request must never hold a durable worker lease forever.
            # This deadline covers signing and downloading the original file;
            # a timeout becomes a visible, retryable job failure instead of an
            # endless 3% progress indicator.
            download_timeout = max(15, int(os.getenv(
                "PAPER_PROCESSING_DOWNLOAD_TIMEOUT_SECONDS",
                str(DEFAULT_DOWNLOAD_TIMEOUT_SECONDS),
            )))
            storage = StorageService()
            identifier_type = "provider_file_id" if getattr(paper, "file_drive_file_id", None) else "path"
            logger.info("PAPER_DOWNLOAD_START paper_id=%s provider=%s identifier_type=%s", paper.id, getattr(paper, "file_storage_provider", None), identifier_type)
            if identifier_type == "path":
                logger.info("STORAGE_LEGACY_PATH_FALLBACK paper_id=%s reason=provider_file_id_missing", paper.id)
            # The direct provider ID is created at upload time. Retaining it
            # avoids an expensive/path-sensitive storage lookup later and is
            # especially important for Google Drive's folder traversal.
            download = (
                storage.download_file_by_id("papers", paper.file_key, paper.file_drive_file_id)
                if getattr(paper, "file_drive_file_id", None) else
                storage.download_file("papers", paper.file_key)
            )
            pdf_bytes = await asyncio.wait_for(
                download,
                timeout=download_timeout,
            )
            logger.info("PAPER_DOWNLOAD_SUCCESS paper_id=%s bytes=%s duration_ms=%s", paper.id, len(pdf_bytes), round((monotonic() - total_started) * 1000))
        except asyncio.TimeoutError:
            logger.warning("Timed out downloading original file for indexing paper_id=%s", paper.id)
            logger.warning("PAPER_DOWNLOAD_FAILED paper_id=%s stage=DOWNLOAD error_type=TimeoutError retryable=true", paper.id)
            return {
                "passages": 0,
                "embedded": 0,
                "ingestion_succeeded": False,
                "error": "Original document download timed out.",
                "metrics": {"download_duration_ms": round((monotonic() - total_started) * 1000)},
            }
        except Exception as exc:
            logger.warning("Could not download file for indexing paper_id=%s: %s", paper.id, exc)
            logger.warning("PAPER_DOWNLOAD_FAILED paper_id=%s stage=DOWNLOAD error_type=%s safe_error_message=%s", paper.id, type(exc).__name__, str(exc)[:200])
            return {
                "passages": 0,
                "embedded": 0,
                "ingestion_succeeded": False,
                "error": "Original document storage was temporarily unavailable.",
                "metrics": {"download_duration_ms": round((monotonic() - total_started) * 1000)},
            }

        validation_started = monotonic()
        logger.info("PDF_VALIDATION_START paper_id=%s bytes=%s", paper.id, len(pdf_bytes))
        valid_pdf, validation_error, page_count = _validate_downloaded_pdf(pdf_bytes)
        if not valid_pdf:
            logger.warning("Downloaded invalid PDF for indexing paper_id=%s: %s", paper.id, validation_error)
            logger.warning("PDF_VALIDATION_FAILED paper_id=%s reason=%s", paper.id, validation_error)
            return {
                "passages": 0,
                "embedded": 0,
                "ingestion_succeeded": False,
                "error": validation_error,
                "metrics": {
                    "download_duration_ms": round((monotonic() - total_started) * 1000),
                    "downloaded_page_count": page_count,
                },
            }
        logger.info("PDF_VALIDATION_SUCCESS paper_id=%s pages=%s bytes=%s duration_ms=%s", paper.id, page_count, len(pdf_bytes), round((monotonic() - validation_started) * 1000))

        context_hint = f"{paper.course_code} - {paper.course_name} ({paper.year})"
        await report(stage="CLASSIFYING", message="Analyzing document pages.", percent_complete=8)
        ingestion = await DocumentIngestionService.process_pdf(
            pdf_bytes,
            document_id=paper.id,
            context_hint=context_hint,
            progress_callback=progress_callback,
        )
        await self._persist_page_extractions(paper, ingestion)
        # READY is an all-pages contract. Persist partial evidence for
        # diagnostics, but do not index/advertise a document with failed page
        # extraction as complete source material.
        if ingestion.extraction_status != "completed":
            await self.db.commit()
            return {
                "passages": 0,
                "embedded": 0,
                "ingestion_succeeded": False,
                "error": "The document could not be completely extracted.",
                "metrics": {**ingestion.metrics, "total_duration_ms": round((monotonic() - total_started) * 1000)},
            }

        # Update paper extraction provenance & status
        paper.extraction_status = ingestion.extraction_status
        paper.extraction_method = ingestion.extraction_method
        paper.extraction_quality = ingestion.extraction_quality
        paper.ocr_used = ingestion.ocr_used
        paper.failed_pages = json.dumps(ingestion.failed_pages)
        paper.extraction_version = "v2_structured"
        paper.embedding_status = "PENDING"
        paper.embedding_error = None
        paper.retrieval_mode = "KEYWORD_ONLY"

        # Safely remove existing passages before re-indexing to avoid duplicate entries
        await report(stage="STRUCTURING", message="Building document sections, questions, and provenance.", pages_total=ingestion.page_count, pages_completed=ingestion.page_count, percent_complete=75)
        logger.info("PASSAGE_INDEXING_START paper_id=%s pages=%s", paper.id, ingestion.page_count)
        await self.db.execute(delete(PaperPassage).where(PaperPassage.paper_id == paper.id))

        passages: list[PaperPassage] = []
        # Keep this defined even when extraction produced only short/empty units.
        # An empty but successfully parsed paper is still a valid ingestion result;
        # it must not fail later with an unbound local and be retried indefinitely.
        vectors: list[list[float]] = []
        passage_idx = 0

        # Build structure-aware passages if available
        if ingestion.structure.units:
            for unit in ingestion.structure.units:
                unit_text = unit.text.strip()
                if not unit_text or len(unit_text) < 15:
                    continue

                if len(unit_text) <= 1200:
                    passages.append(
                        PaperPassage(
                            paper_id=paper.id,
                            page_number=unit.page_number,
                            passage_index=passage_idx,
                            question_number=unit.question_number,
                            section_title=unit.section_title,
                            extraction_method=unit.extraction_method,
                            extraction_confidence=unit.confidence,
                            text=unit_text,
                            text_hash=hashlib.sha256(unit_text.encode("utf-8")).hexdigest(),
                            course_code=paper.course_code,
                            course_name=paper.course_name,
                            academic_year=paper.year,
                            source_file_key=paper.file_key,
                            embedding_status="pending",
                        )
                    )
                    passage_idx += 1
                else:
                    # Long unit: chunk while preserving unit question & section provenance
                    sub_chunks = chunk_page_text(unit_text, chunk_size=900, overlap=120)
                    for sub in sub_chunks:
                        passages.append(
                            PaperPassage(
                                paper_id=paper.id,
                                page_number=unit.page_number,
                                passage_index=passage_idx,
                                question_number=unit.question_number,
                                section_title=unit.section_title,
                                extraction_method=unit.extraction_method,
                                extraction_confidence=unit.confidence,
                                text=sub,
                                text_hash=hashlib.sha256(sub.encode("utf-8")).hexdigest(),
                                course_code=paper.course_code,
                                course_name=paper.course_name,
                                academic_year=paper.year,
                                source_file_key=paper.file_key,
                                embedding_status="pending",
                            )
                        )
                        passage_idx += 1
        else:
            # Fallback: page-aware chunks
            for page in ingestion.pages:
                if not page.text.strip():
                    continue
                chunks = chunk_page_text(page.text)
                for chunk in chunks:
                    passages.append(
                        PaperPassage(
                            paper_id=paper.id,
                            page_number=page.page_number,
                            passage_index=passage_idx,
                            question_number=None,
                            section_title=None,
                            extraction_method=page.extraction_method,
                            extraction_confidence=page.confidence,
                            text=chunk,
                            text_hash=hashlib.sha256(chunk.encode("utf-8")).hexdigest(),
                            course_code=paper.course_code,
                            course_name=paper.course_name,
                            academic_year=paper.year,
                            source_file_key=paper.file_key,
                            embedding_status="pending",
                        )
                    )
                    passage_idx += 1

        if passages:
            await report(stage="PERSISTING", message="Saving structured paper evidence.", percent_complete=82)
            self.db.add_all(passages)
            await self.db.flush()

            # Generate embeddings
            await report(stage="EMBEDDING", message="Creating the paper search index.", percent_complete=88)
            embedding_started = monotonic()
            outcome = await self._embed_passages(passages)
            vectors = outcome.vectors or []
            if outcome.error_type:
                logger.warning("EMBEDDING_FAILED paper_id=%s provider=%s model=%s error_type=%s", paper.id, outcome.provider, outcome.model, outcome.error_type)
                paper.embedding_status = "FAILED"
                paper.embedding_error = outcome.error_type
                paper.retrieval_mode = "KEYWORD_ONLY"
            else:
                paper.embedding_status = "READY"
                paper.embedding_error = None
                paper.retrieval_mode = "HYBRID"

            ingestion.metrics["embedding_duration_ms"] = round((monotonic() - embedding_started) * 1000)
            ingestion.metrics["embedding_calls"] = EmbeddingService.last_call_count()

        await report(stage="VALIDATING", message="Validating indexed paper evidence.", percent_complete=96)
        await self.db.commit()

        try:
            await QuestionIndexService(self.db).index_paper(paper, passages)
        except Exception as exc:
            logger.exception("PASSAGE_INDEXING_FAILED paper_id=%s error_type=%s", paper.id, type(exc).__name__)
            raise

        logger.info("PASSAGE_INDEXING_SUCCESS paper_id=%s passages=%s embedded=%s duration_ms=%s", paper.id, len(passages), len(vectors or []), round((monotonic() - total_started) * 1000))

        return {
            "passages": len(passages),
            "embedded": len(vectors or []),
            "ingestion_succeeded": True,
            "metrics": {
                **ingestion.metrics,
                "passages": len(passages),
                "embedded": len(vectors or []),
                "embedding_error": outcome.error_type if passages else None,
                "embedding_status": "ready" if vectors else ("failed" if passages else "not_required"),
                "embedding_provider": outcome.provider if passages else None,
                "embedding_model": outcome.model if passages else None,
                # This is a logical count rather than a database-driver trace:
                # delete old evidence, flush/commit new evidence, plus optional
                # pgvector updates. It makes an N+1 vector path visible in the
                # persisted run metrics without pretending it is wall-clock IO.
                "database_operations": 2 + (len(vectors) if self.db.bind and getattr(self.db.bind, "dialect", None) and self.db.bind.dialect.name == "postgresql" else 0),
                "total_duration_ms": round((monotonic() - total_started) * 1000),
            },
        }

    async def _embed_passages(self, passages: list[PaperPassage]):
        """Persist vectors when available; preserve keyword retrieval on failure."""
        outcome = await EmbeddingService().generate_embeddings(
            [item.text for item in passages],
            paper_id=getattr(passages[0], "paper_id", None) if passages else None,
        )
        vectors = outcome.vectors or []
        if len(vectors) != len(passages):
            for passage in passages:
                passage.embedding_status = "failed" if outcome.error_type else "pending"
                # A failed re-embedding attempt must not leave a stale vector
                # that could later be mistaken for the requested provider/model.
                passage.embedding_json = None
                passage.embedding_provider = None
                passage.embedding_model = None
                passage.embedding_dimension = None
            return outcome
        for passage, vector in zip(passages, vectors):
            passage.embedding_json = json.dumps(vector)
            passage.embedding_provider = outcome.provider
            passage.embedding_model = outcome.model
            passage.embedding_dimension = len(vector)
            passage.embedding_status = "ready"
            passage.embedding_updated_at = datetime.now(timezone.utc)
        return outcome

    async def _persist_page_extractions(self, paper: Papers, ingestion) -> None:
        """Store every page outcome before passages/indexing can obscure it."""
        processing_version = "v2_structured"
        await self.db.execute(delete(PaperPageExtraction).where(
            PaperPageExtraction.paper_id == paper.id,
            PaperPageExtraction.processing_version == processing_version,
        ))
        self.db.add_all([
            PaperPageExtraction(
                paper_id=paper.id,
                processing_version=processing_version,
                page_number=page.page_number,
                status="SUCCESS" if page.text.strip() else "FAILED",
                extraction_method=page.extraction_method,
                extraction_confidence=page.confidence,
                text=page.text or None,
                text_length=len(page.text or ""),
                source_file_key=paper.file_key,
                error_message=None if page.text.strip() else "No usable text was produced for this page.",
            )
            for page in ingestion.pages
        ])
        await self.db.flush()
        persisted = (await self.db.execute(text("SELECT count(*) FROM paper_page_extractions WHERE paper_id = :paper_id AND processing_version = :version"), {"paper_id": paper.id, "version": processing_version})).scalar_one()
        if persisted != len(ingestion.pages):
            logger.error("PAGE_EXTRACTION_PERSISTENCE_INTEGRITY_FAILURE paper_id=%s expected=%s actual=%s", paper.id, len(ingestion.pages), persisted)
            raise RuntimeError("Page extraction persistence integrity check failed")
        logger.info("PAGE_EXTRACTION_PERSIST_SUCCESS paper_id=%s pages=%s", paper.id, persisted)
