"""Application-facing Paper Hub AI service and provider selection."""

from __future__ import annotations

import json
import logging
from collections import defaultdict, deque
from collections.abc import AsyncIterator
from time import monotonic
from typing import Any

from core.config import settings
from services.ai.base import (
    AICapability,
    AIContextTooLargeError,
    AIEmbeddingRequest,
    AIEmbeddingResult,
    AIError,
    AIGeneration,
    AIGenerationRequest,
    AIMalformedResponseError,
    AIProvider,
    AIProviderUnavailableError,
    AIRateLimitError,
)
from services.ai.providers.openai import OpenAIProvider

logger = logging.getLogger(__name__)


class AIProviderFactory:
    @staticmethod
    def create(provider_name: str | None = None) -> AIProvider:
        provider_name = (provider_name or settings.ai_provider).strip().lower()
        if provider_name == "openai":
            return OpenAIProvider(
                api_key=settings.openai_api_key or "",
                default_model=settings.openai_model,
                embedding_model=settings.openai_embedding_model,
                timeout_seconds=settings.ai_timeout_seconds,
            )
        if provider_name == "openai_compatible":
            if not settings.ai_compatible_base_url:
                raise AIProviderUnavailableError("AI_COMPATIBLE_BASE_URL is required for the compatible provider")
            return OpenAIProvider(
                api_key=settings.ai_compatible_api_key or "",
                default_model=settings.ai_compatible_model or settings.openai_model,
                embedding_model=settings.ai_compatible_embedding_model or settings.openai_embedding_model,
                timeout_seconds=settings.ai_timeout_seconds,
                base_url=settings.ai_compatible_base_url,
                name="openai_compatible",
            )
        raise AIProviderUnavailableError(f"Unsupported AI provider: {provider_name}")


class _UserRequestLimiter:
    """Small process-local guard against accidental per-user cost spikes."""

    def __init__(self) -> None:
        self.requests: dict[str, deque[float]] = defaultdict(deque)

    def check(self, user_id: str | None, limit: int) -> None:
        if not user_id or limit <= 0:
            return
        now = monotonic()
        window = self.requests[user_id]
        while window and now - window[0] >= 60:
            window.popleft()
        if len(window) >= limit:
            raise AIRateLimitError("Paper Hub AI request limit reached")
        window.append(now)


_limiter = _UserRequestLimiter()


class AIService:
    """Provider-neutral service used by routers and paper workflows."""

    def __init__(self, provider: AIProvider | None = None, fallback_provider: AIProvider | None = None):
        if not settings.ai_enabled and provider is None:
            raise AIProviderUnavailableError("Paper Hub AI is disabled")
        self.provider = provider or AIProviderFactory.create()
        self.fallback_provider = fallback_provider
        if self.fallback_provider is None and settings.ai_fallback_provider:
            self.fallback_provider = AIProviderFactory.create(settings.ai_fallback_provider)

    @staticmethod
    def estimate_tokens(messages: list) -> int:
        """Conservative provider-neutral estimate used before sending document context."""
        total_chars = 0
        for message in messages:
            if isinstance(message.content, str):
                total_chars += len(message.content)
            else:
                total_chars += len(json.dumps(message.content, ensure_ascii=False))
        return max(1, total_chars // 4)

    def _prepare(self, request: AIGenerationRequest, capability: AICapability) -> AIGenerationRequest:
        if not self.provider.supports(capability):
            raise AIProviderUnavailableError(f"Provider {self.provider.name} does not support {capability.value}")
        if self.estimate_tokens(request.messages) > settings.ai_max_context_tokens:
            raise AIContextTooLargeError()
        _limiter.check(request.user_id, settings.ai_max_requests_per_user_per_minute)
        max_output = min(request.max_output_tokens or settings.ai_max_output_tokens, settings.ai_max_output_tokens)
        return AIGenerationRequest(**{**request.__dict__, "max_output_tokens": max_output})

    async def generate(self, request: AIGenerationRequest) -> AIGeneration:
        request = self._prepare(request, AICapability.STRUCTURED_OUTPUT if request.response_schema else AICapability.TEXT_GENERATION)
        return await self._call_with_explicit_fallback("generate", request)

    async def stream(self, request: AIGenerationRequest) -> AsyncIterator[str]:
        request = self._prepare(request, AICapability.STREAMING)
        try:
            async for item in self.provider.stream(request):
                yield item
        except (AIProviderUnavailableError, AIRateLimitError) as exc:
            logger.info("AI stream failed provider=%s code=%s", self.provider.name, exc.code)
            if not self.fallback_provider:
                raise
            async for item in self.fallback_provider.stream(request):
                yield item

    async def embed(self, request: AIEmbeddingRequest) -> AIEmbeddingResult:
        if not self.provider.supports(AICapability.EMBEDDINGS):
            raise AIProviderUnavailableError(f"Provider {self.provider.name} does not support embeddings")
        if sum(len(value) for value in request.input) // 4 > settings.ai_max_context_tokens:
            raise AIContextTooLargeError()
        _limiter.check(request.user_id, settings.ai_max_requests_per_user_per_minute)
        return await self.provider.embed(request)

    async def generate_image(self, request: Any, user_id: str | None = None) -> Any:
        if not self.provider.supports(AICapability.IMAGE_GENERATION) or not hasattr(self.provider, "generate_image"):
            raise AIProviderUnavailableError(f"Provider {self.provider.name} does not support image generation")
        _limiter.check(user_id, settings.ai_max_requests_per_user_per_minute)
        return await self.provider.generate_image(request, settings.openai_image_model)  # type: ignore[attr-defined]

    async def generate_structured(self, request: AIGenerationRequest, schema: dict[str, Any]) -> dict[str, Any]:
        response = await self.generate(AIGenerationRequest(**{**request.__dict__, "response_schema": schema}))
        try:
            parsed = json.loads(response.content)
        except json.JSONDecodeError as exc:
            raise AIMalformedResponseError("Provider returned invalid structured output") from exc
        if not isinstance(parsed, dict):
            raise AIMalformedResponseError("Provider returned a non-object structured output")
        self._validate_schema(parsed, schema)
        return parsed

    @classmethod
    def _validate_schema(cls, value: Any, schema: dict[str, Any], path: str = "response") -> None:
        """Validate the JSON Schema subset used by Paper Hub response contracts."""
        expected_type = schema.get("type")
        type_checks = {"object": dict, "array": list, "string": str, "number": (int, float), "integer": int, "boolean": bool}
        if expected_type and (expected_type not in type_checks or not isinstance(value, type_checks[expected_type])):
            raise AIMalformedResponseError(f"Structured output has an invalid {path} type")
        if "enum" in schema and value not in schema["enum"]:
            raise AIMalformedResponseError(f"Structured output has an invalid {path} value")
        if isinstance(value, dict):
            properties = schema.get("properties", {})
            for field in schema.get("required", []):
                if field not in value:
                    raise AIMalformedResponseError(f"Structured output is missing {path}.{field}")
            for field, field_value in value.items():
                if field in properties:
                    cls._validate_schema(field_value, properties[field], f"{path}.{field}")
        elif isinstance(value, list) and schema.get("items"):
            for index, item in enumerate(value):
                cls._validate_schema(item, schema["items"], f"{path}[{index}]")

    async def answer_question(self, request: AIGenerationRequest) -> AIGeneration:
        return await self.generate(request)

    async def analyze_paper(self, request: AIGenerationRequest) -> AIGeneration:
        return await self.generate(request)

    async def _call_with_explicit_fallback(self, method: str, request: AIGenerationRequest) -> AIGeneration:
        started = monotonic()
        try:
            response = await getattr(self.provider, method)(request)
            logger.info("ai_request provider=%s model=%s success=true duration_ms=%s input_tokens=%s output_tokens=%s request_id=%s", response.provider, response.model, response.duration_ms, response.usage.input_tokens if response.usage else None, response.usage.output_tokens if response.usage else None, response.request_id)
            return response
        except (AIProviderUnavailableError, AIRateLimitError) as exc:
            logger.warning("ai_request provider=%s success=false code=%s duration_ms=%s", self.provider.name, exc.code, round((monotonic() - started) * 1000))
            if not self.fallback_provider:
                raise
            logger.warning("ai_fallback provider=%s fallback_provider=%s", self.provider.name, self.fallback_provider.name)
            return await getattr(self.fallback_provider, method)(request)
