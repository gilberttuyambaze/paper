from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone

from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from models.papers import Papers, PaperPassage
from services.document_ingestion import DocumentIngestionService
from services.embeddings import EmbeddingService
from services.pdf_text import chunk_page_text
from services.storage import StorageService
from services.question_classification import QuestionIndexService

logger = logging.getLogger(__name__)


class PassageIndexService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def index_paper(self, paper: Papers) -> dict[str, int]:
        if not paper.file_key:
            return {"passages": 0, "embedded": 0}

        try:
            pdf_bytes = await StorageService().download_file("papers", paper.file_key)
        except Exception as exc:
            logger.warning("Could not download file for indexing paper_id=%s: %s", paper.id, exc)
            return {"passages": 0, "embedded": 0}

        context_hint = f"{paper.course_code} - {paper.course_name} ({paper.year})"
        ingestion = await DocumentIngestionService.process_pdf(
            pdf_bytes,
            document_id=paper.id,
            context_hint=context_hint,
        )

        # Update paper extraction provenance & status
        paper.extraction_status = ingestion.extraction_status
        paper.extraction_method = ingestion.extraction_method
        paper.extraction_quality = ingestion.extraction_quality
        paper.ocr_used = ingestion.ocr_used
        paper.failed_pages = json.dumps(ingestion.failed_pages)
        paper.extraction_version = "v2_structured"

        # Safely remove existing passages before re-indexing to avoid duplicate entries
        await self.db.execute(delete(PaperPassage).where(PaperPassage.paper_id == paper.id))

        passages: list[PaperPassage] = []
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
            self.db.add_all(passages)
            await self.db.flush()

            # Generate embeddings
            vectors = await EmbeddingService().generate_embeddings([item.text for item in passages])
            if vectors and len(vectors) == len(passages):
                for passage, vector in zip(passages, vectors):
                    passage.embedding_json = json.dumps(vector)
                    passage.embedding_model = settings.embedding_model
                    passage.embedding_dimension = len(vector)
                    passage.embedding_status = "ready"
                    passage.embedding_updated_at = datetime.now(timezone.utc)
                    if self.db.bind and getattr(self.db.bind, "dialect", None) and self.db.bind.dialect.name == "postgresql":
                        try:
                            vector_literal = "[" + ",".join(str(value) for value in vector) + "]"
                            await self.db.execute(
                                text("UPDATE paper_passages SET embedding_vector = CAST(:vector AS vector) WHERE id = :id"),
                                {"vector": vector_literal, "id": passage.id},
                            )
                        except Exception:
                            pass
            else:
                for passage in passages:
                    passage.embedding_status = "pending"

        await self.db.commit()

        try:
            await QuestionIndexService(self.db).index_paper(paper, passages)
        except Exception:
            pass

        return {"passages": len(passages), "embedded": len(vectors or [])}
