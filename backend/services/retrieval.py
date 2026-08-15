"""Hybrid passage retrieval: exact keyword matching plus optional semantic similarity."""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass

from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from models.papers import PaperPassage
from services.embeddings import EmbeddingService


@dataclass(frozen=True)
class RetrievedPassage:
    passage: PaperPassage
    score: float
    keyword_score: float
    semantic_score: float | None


def _terms(value: str) -> set[str]:
    return {term for term in re.findall(r"[a-zA-Z0-9]{2,}", value.lower()) if term not in {"what", "is", "the", "and", "for", "with", "this", "that", "about"}}


def _cosine(left: list[float], right: list[float]) -> float:
    denominator = math.sqrt(sum(x * x for x in left)) * math.sqrt(sum(x * x for x in right))
    return sum(x * y for x, y in zip(left, right)) / denominator if denominator else 0.0


class HybridRetrievalService:
    def __init__(self, db: AsyncSession): self.db = db

    async def retrieve(self, query: str, *, paper_id: int, course_code: str | None = None, limit: int | None = None) -> list[RetrievedPassage]:
        query_terms = _terms(query)
        try:
            result = await self.db.execute(select(PaperPassage).where(PaperPassage.paper_id == paper_id).limit(settings.hybrid_search_top_k))
        except SQLAlchemyError:
            # Allows rolling deployments where application code reaches a node
            # before its migration. The caller falls back to the existing study
            # assistant instead of exposing a 500 to students.
            # Do not call rollback here: it expires already-loaded ORM objects
            # (the paper/comments used by the caller) and can trigger async lazy
            # loading outside SQLAlchemy's greenlet context. Request teardown
            # will roll this failed read transaction back safely.
            return []
        passages = result.scalars().all()
        if not passages:
            return []
        query_embedding = await EmbeddingService().generate_embedding(query)
        postgres_scores: dict[int, float] = {}
        if query_embedding and self.db.bind and self.db.bind.dialect.name == "postgresql":
            try:
                vector_literal = "[" + ",".join(str(value) for value in query_embedding) + "]"
                rows = await self.db.execute(text("SELECT id, 1 - (embedding_vector <=> CAST(:vector AS vector)) AS score FROM paper_passages WHERE paper_id = :paper_id AND embedding_vector IS NOT NULL ORDER BY embedding_vector <=> CAST(:vector AS vector) LIMIT :limit"), {"vector": vector_literal, "paper_id": paper_id, "limit": settings.hybrid_search_top_k})
                postgres_scores = {int(row.id): float(row.score) for row in rows}
            except Exception:
                postgres_scores = {}
        ranked = []
        for passage in passages:
            text_terms = _terms(passage.text)
            keyword_score = len(query_terms & text_terms) / max(1, len(query_terms))
            if course_code and passage.course_code and passage.course_code.lower() == course_code.lower():
                keyword_score += 0.2
            semantic_score = None
            if passage.id in postgres_scores:
                semantic_score = postgres_scores[passage.id]
            elif query_embedding and passage.embedding_json and passage.embedding_model == settings.embedding_model:
                try: semantic_score = _cosine(query_embedding, json.loads(passage.embedding_json))
                except (ValueError, TypeError): pass
            score = keyword_score * 0.45 + ((semantic_score + 1) / 2 * 0.55 if semantic_score is not None else 0)
            if keyword_score or semantic_score is not None:
                ranked.append(RetrievedPassage(passage, score, keyword_score, semantic_score))
        return sorted(ranked, key=lambda item: item.score, reverse=True)[: limit or settings.vector_search_top_k]
