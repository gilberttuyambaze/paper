"""Provider-neutral embedding boundary. A missing provider never blocks indexing or retrieval."""
from __future__ import annotations
import asyncio
import hashlib
import logging
from dataclasses import dataclass
from time import monotonic
from urllib.parse import urlparse

from services.ai.base import (
    AIAuthenticationError,
    AIEmbeddingRequest,
    AIError,
    AIModelUnavailableError,
    AIMalformedResponseError,
    AIProviderUnavailableError,
    AIRateLimitError,
    AITimeoutError,
)
from services.ai.service import AIProviderFactory
from core.config import settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EmbeddingOutcome:
    vectors: list[list[float]] | None
    provider: str
    model: str
    error_type: str | None = None
    error_message: str | None = None


class EmbeddingValidationError(AIMalformedResponseError):
    """A provider responded but not with a complete compatible vector set."""


class EmbeddingService:
    _last_calls: int = 0
    # Groq is a generation provider in this application, not an embedding
    # provider. Keeping this capability boundary prevents another /embeddings
    # 404 and avoids spending time on a request that cannot succeed.
    SUPPORTED_PROVIDERS = {"openai", "gemini", "openrouter"}
    BATCH_SIZE = 25
    MAX_RATE_LIMIT_ATTEMPTS = 3
    MAX_RATE_LIMIT_DELAY_SECONDS = 5.0

    @property
    def model(self) -> str:
        return settings.embedding_model

    @staticmethod
    def _model_for(provider: str) -> str:
        return str(getattr(settings, f"{provider}_embedding_model", None) or settings.embedding_model)

    @classmethod
    def _providers(cls) -> list[str]:
        primary = (settings.embedding_provider or "openai").strip().lower()
        fallbacks = [item.strip().lower() for item in (settings.embedding_fallback_providers or "").split(",") if item.strip()]
        # Never route embedding traffic through generation-only or removed
        # providers, even if an obsolete environment value still names one.
        return [provider for provider in dict.fromkeys([primary, *fallbacks]) if provider in cls.SUPPORTED_PROVIDERS]

    async def generate_embeddings(self, texts: list[str], *, providers: list[str] | None = None, paper_id: int | None = None) -> EmbeddingOutcome:
        type(self)._last_calls = 0
        total_started = monotonic()
        provider_names = providers or self._providers()
        provider_names = [name for name in provider_names if name in self.SUPPORTED_PROVIDERS]
        provider_name = provider_names[0] if provider_names else "disabled"
        model = self._model_for(provider_name)
        if not texts or provider_name == "disabled":
            return EmbeddingOutcome(None, provider_name, model, "EMBEDDING_CONFIGURATION_ERROR", "Embeddings are disabled or no passages were supplied.")

        cleaned = [t.strip() for t in texts]
        if not any(cleaned):
            return EmbeddingOutcome(None, provider_name, model, "EMBEDDING_CONFIGURATION_ERROR", "No non-empty passages were supplied.")

        logger.info("EMBEDDING_START paper_id=%s passages=%s providers=%s", paper_id, len(cleaned), ",".join(provider_names))
        last_error: EmbeddingOutcome | None = None
        for attempt, provider_name in enumerate(provider_names, start=1):
            model = self._model_for(provider_name)
            if not AIProviderFactory.is_embedding_configured(provider_name):
                logger.info("EMBEDDING_PROVIDER_SKIPPED provider=%s reason=not_configured", provider_name)
                continue
            diagnostic = self._configuration_diagnostic(provider_name, model)
            logger.info(
                "EMBEDDING_PROVIDER_CONFIG provider=%s configured=%s key_fingerprint=%s model=%s base_url=%s",
                provider_name, diagnostic["configured"], diagnostic["key_fingerprint"], model, diagnostic["base_url"],
            )
            try:
                provider = AIProviderFactory.create_embedding(provider_name, model)
                logger.info("EMBEDDING_PROVIDER_ATTEMPT paper_id=%s provider=%s model=%s passages=%s attempt=%s", paper_id, provider_name, model, len(cleaned), attempt)
                all_vectors: list[list[float]] = []
                for i in range(0, len(cleaned), self.BATCH_SIZE):
                    chunk = cleaned[i : i + self.BATCH_SIZE]
                    timeout_sec = max(8.0, len(chunk) * 0.5)
                    batch_number = i // self.BATCH_SIZE + 1
                    result = await self._embed_batch(
                        provider, chunk, model, provider_name, attempt, batch_number, timeout_sec, paper_id,
                    )
                    if not result or not result.vectors:
                        raise EmbeddingValidationError("EMBEDDING_INVALID_RESPONSE: provider returned no vectors")
                    if len(result.vectors) != len(chunk):
                        raise EmbeddingValidationError(
                            f"EMBEDDING_INVALID_RESPONSE expected_vectors={len(chunk)} actual_vectors={len(result.vectors)}"
                        )
                    all_vectors.extend(result.vectors)

                if len(all_vectors) != len(texts):
                    raise EmbeddingValidationError(
                        f"EMBEDDING_INVALID_RESPONSE expected_vectors={len(texts)} actual_vectors={len(all_vectors)}"
                    )
                dimensions = {len(vector) for vector in all_vectors}
                if len(dimensions) != 1 or next(iter(dimensions)) != settings.embedding_dimension:
                    raise EmbeddingValidationError(
                        f"EMBEDDING_INVALID_RESPONSE expected_dimension={settings.embedding_dimension} actual_dimensions={sorted(dimensions)}"
                    )
                logger.info("EMBEDDING_PROVIDER_SUCCESS paper_id=%s provider=%s model=%s vectors=%s duration_ms=%s", paper_id, provider_name, model, len(all_vectors), round((monotonic() - total_started) * 1000))
                logger.info("EMBEDDING_SUCCESS provider=%s model=%s vectors=%s", provider_name, model, len(all_vectors))
                return EmbeddingOutcome(all_vectors, provider_name, model)
            except Exception as exc:
                error_type = self._error_type(exc)
                last_error = EmbeddingOutcome(None, provider_name, model, error_type, str(exc)[:300])
                logger.warning("EMBEDDING_PROVIDER_FAILED paper_id=%s provider=%s model=%s attempt=%s error_type=%s elapsed_ms=%s error=%s", paper_id, provider_name, model, attempt, error_type, round((monotonic() - total_started) * 1000), type(exc).__name__)
                continue
        logger.warning("EMBEDDING_EXHAUSTED providers=%s", ",".join(provider_names))
        return last_error or EmbeddingOutcome(None, provider_name, model, "EMBEDDING_CONFIGURATION_ERROR", "No embedding provider is configured.")

    async def _embed_batch(self, provider, chunk: list[str], model: str, provider_name: str, attempt: int, batch_number: int, timeout_sec: float, paper_id: int | None):
        """Retry only transient rate limits; never let partial provider vectors escape."""
        for request_attempt in range(1, self.MAX_RATE_LIMIT_ATTEMPTS + 1):
            started = monotonic()
            logger.info("EMBEDDING_BATCH_START paper_id=%s provider=%s model=%s batch=%s batch_size=%s provider_attempt=%s request_attempt=%s", paper_id, provider_name, model, batch_number, len(chunk), attempt, request_attempt)
            try:
                result = await asyncio.wait_for(provider.embed(AIEmbeddingRequest(input=chunk, model=model)), timeout=timeout_sec)
                type(self)._last_calls += 1
                logger.info("EMBEDDING_BATCH_SUCCESS paper_id=%s provider=%s model=%s batch=%s batch_size=%s duration_ms=%s", paper_id, provider_name, model, batch_number, len(chunk), round((monotonic() - started) * 1000))
                return result
            except AIRateLimitError as exc:
                quota_exhausted = bool(getattr(exc, "quota_exhausted", False))
                if quota_exhausted or request_attempt == self.MAX_RATE_LIMIT_ATTEMPTS:
                    logger.warning("EMBEDDING_BATCH_FAILED provider=%s batch=%s error_type=%s retryable=%s duration_ms=%s", provider_name, batch_number, "EMBEDDING_QUOTA_EXCEEDED" if quota_exhausted else "EMBEDDING_RATE_LIMITED", not quota_exhausted and request_attempt < self.MAX_RATE_LIMIT_ATTEMPTS, round((monotonic() - started) * 1000))
                    raise
                retry_after = getattr(exc, "retry_after", None)
                delay = min(self.MAX_RATE_LIMIT_DELAY_SECONDS, retry_after if retry_after is not None else 0.5 * (2 ** (request_attempt - 1)))
                logger.info("EMBEDDING_RATE_LIMIT_RETRY provider=%s batch=%s retry_in_seconds=%s", provider_name, batch_number, delay)
                await asyncio.sleep(delay)
            except Exception as exc:
                logger.warning("EMBEDDING_BATCH_FAILED provider=%s batch=%s error_type=%s duration_ms=%s", provider_name, batch_number, self._error_type(exc), round((monotonic() - started) * 1000))
                raise

    @staticmethod
    def _error_type(exc: Exception | None) -> str:
        if isinstance(exc, AIRateLimitError):
            return "EMBEDDING_QUOTA_EXCEEDED" if getattr(exc, "quota_exhausted", False) else "EMBEDDING_RATE_LIMITED"
        if isinstance(exc, (AIAuthenticationError,)):
            return "EMBEDDING_AUTH_FAILED"
        if isinstance(exc, AIModelUnavailableError):
            return "EMBEDDING_MODEL_UNAVAILABLE"
        if isinstance(exc, (AIMalformedResponseError, EmbeddingValidationError)):
            return "EMBEDDING_INVALID_RESPONSE"
        if isinstance(exc, (AITimeoutError, asyncio.TimeoutError)):
            return "EMBEDDING_TIMEOUT"
        if isinstance(exc, AIProviderUnavailableError):
            return "EMBEDDING_NETWORK_ERROR"
        return "EMBEDDING_PROVIDER_ERROR"

    @staticmethod
    def _configuration_diagnostic(provider: str, model: str) -> dict[str, str | bool]:
        key = (getattr(settings, f"{provider}_embedding_api_key", None) or "").strip()
        spec = AIProviderFactory.PROVIDERS_CATALOG[provider]
        base_url = str(spec["default_url"])
        parsed = urlparse(base_url)
        safe_base = f"{parsed.scheme}://{parsed.netloc}{parsed.path.rstrip('/')}"
        fingerprint = hashlib.sha256(key.encode("utf-8")).hexdigest()[:12] if key else "none"
        return {"configured": bool(key), "key_fingerprint": fingerprint, "model": model, "base_url": safe_base}

    @classmethod
    def last_call_count(cls) -> int:
        return cls._last_calls

    async def generate_embedding(self, text: str, *, provider: str | None = None) -> list[float] | None:
        try:
            vectors = await self.generate_embeddings([text], providers=[provider] if provider else None)
            return vectors.vectors[0] if vectors.vectors else None
        except Exception:
            return None
