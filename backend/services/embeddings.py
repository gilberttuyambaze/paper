"""Provider-neutral embedding boundary. A missing provider never blocks indexing or retrieval."""
from __future__ import annotations
import asyncio
import logging

from services.ai.base import AIEmbeddingRequest
from services.ai.service import AIService
from core.config import settings

logger = logging.getLogger(__name__)


class EmbeddingService:
    @property
    def model(self) -> str:
        return settings.embedding_model

    async def generate_embeddings(self, texts: list[str]) -> list[list[float]] | None:
        if not texts or settings.embedding_provider == "disabled" or not settings.ai_enabled or not settings.openai_api_key:
            return None

        cleaned = [t.strip() for t in texts]
        if not any(cleaned):
            return None

        batch_size = 25
        all_vectors: list[list[float]] = []

        try:
            for i in range(0, len(cleaned), batch_size):
                chunk = cleaned[i : i + batch_size]
                timeout_sec = max(8.0, len(chunk) * 0.5)
                result = await asyncio.wait_for(
                    AIService().embed(AIEmbeddingRequest(input=chunk, model=self.model)),
                    timeout=timeout_sec,
                )
                if not result or not result.vectors:
                    return None
                all_vectors.extend(result.vectors)

            return all_vectors if len(all_vectors) == len(texts) else None
        except Exception as exc:
            logger.debug("Embedding service gracefully skipped: %s", exc)
            return None

    async def generate_embedding(self, text: str) -> list[float] | None:
        try:
            vectors = await self.generate_embeddings([text])
            return vectors[0] if vectors else None
        except Exception:
            return None
