from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from models.papers import Papers, PaperPassage
from services.embeddings import EmbeddingService
from services.pdf_text import chunk_page_text, extract_pdf_pages
from services.storage import StorageService
from services.question_classification import QuestionIndexService


class PassageIndexService:
    def __init__(self, db: AsyncSession): self.db = db

    async def index_paper(self, paper: Papers) -> dict[str, int]:
        if not paper.file_key: return {"passages": 0, "embedded": 0}
        pages = extract_pdf_pages(await StorageService().download_file("papers", paper.file_key))
        await self.db.execute(delete(PaperPassage).where(PaperPassage.paper_id == paper.id))
        passages = []
        for page in pages:
            for index, text in enumerate(chunk_page_text(page.text)):
                passages.append(PaperPassage(paper_id=paper.id, page_number=page.page_number, passage_index=index, text=text, text_hash=hashlib.sha256(text.encode()).hexdigest(), course_code=paper.course_code, course_name=paper.course_name, academic_year=paper.year, source_file_key=paper.file_key, embedding_status="pending"))
        self.db.add_all(passages)
        await self.db.flush()
        vectors = await EmbeddingService().generate_embeddings([item.text for item in passages])
        if vectors and len(vectors) == len(passages):
            for passage, vector in zip(passages, vectors):
                passage.embedding_json = json.dumps(vector)
                passage.embedding_model = settings.embedding_model
                passage.embedding_dimension = len(vector)
                passage.embedding_status = "ready"
                passage.embedding_updated_at = datetime.now(timezone.utc)
                if self.db.bind and self.db.bind.dialect.name == "postgresql":
                    try:
                        vector_literal = "[" + ",".join(str(value) for value in vector) + "]"
                        await self.db.execute(text("UPDATE paper_passages SET embedding_vector = CAST(:vector AS vector) WHERE id = :id"), {"vector": vector_literal, "id": passage.id})
                    except Exception:
                        pass
        elif passages:
            for passage in passages: passage.embedding_status = "pending"
        await self.db.commit()
        try:
            await QuestionIndexService(self.db).index_paper(paper, passages)
        except Exception:
            # Classification remains optional and must not invalidate passages.
            pass
        return {"passages": len(passages), "embedded": len(vectors or [])}
