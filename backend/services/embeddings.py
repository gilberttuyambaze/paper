"""Provider-neutral embedding boundary. A missing provider never blocks indexing."""
from __future__ import annotations
import asyncio

from services.ai.base import AIEmbeddingRequest
from services.ai.service import AIService
from core.config import settings


class EmbeddingService:
    @property
    def model(self) -> str:
        return settings.embedding_model

    async def generate_embeddings(self, texts: list[str]) -> list[list[float]] | None:
        if not texts or settings.embedding_provider == "disabled" or not settings.ai_enabled or not settings.openai_api_key:
            return None
        try:
            result = await asyncio.wait_for(AIService().embed(AIEmbeddingRequest(input=texts, model=self.model)), timeout=3)
            return result.vectors
        except Exception:
            return None

    async def generate_embedding(self, text: str) -> list[float] | None:
        vectors = await self.generate_embeddings([text])
        return vectors[0] if vectors else None
