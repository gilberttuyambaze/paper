"""Application-facing Paper Hub AI service and provider selection."""

from __future__ import annotations

import asyncio
import json
import logging
import os
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
    PROVIDERS_CATALOG: dict[str, dict[str, Any]] = {
        "groq": {
            "label": "Groq (Fast OSS)",
            "default_url": "https://api.groq.com/openai/v1",
            "default_model": "openai/gpt-oss-120b",
            "key_prefixes": ("gsk_",),
            "env_vars": ("GROQ_API_KEY",),
        },
        "gemini": {
            "label": "Google Gemini 3.6",
            "default_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
            "default_model": "gemini-3.6-flash",
            "key_prefixes": ("AIzaSy",),
            "env_vars": ("GEMINI_API_KEY", "GOOGLE_API_KEY"),
        },
        "openrouter": {
            "label": "OpenRouter",
            "default_url": "https://openrouter.ai/api/v1",
            "default_model": "meta-llama/llama-3.3-70b-instruct",
            "key_prefixes": ("sk-or-",),
            "env_vars": ("OPENROUTER_API_KEY",),
        },
        "openai": {
            "label": "OpenAI",
            "default_url": "https://api.openai.com/v1",
            "default_model": "gpt-4.1-mini",
            "key_prefixes": ("sk-proj-", "sk-"),
            "env_vars": ("OPENAI_API_KEY", "APP_AI_KEY"),
        },
        "ollama": {
            "label": "Local Ollama",
            "default_url": "http://localhost:11434/v1",
            "default_model": "llama3.2",
            "key_prefixes": (),
            "env_vars": (),
        },
        "openai_compatible": {
            "label": "Custom AI Endpoint",
            "default_url": "http://localhost:11434/v1",
            "default_model": "gpt-4.1-mini",
            "key_prefixes": (),
            "env_vars": ("AI_COMPATIBLE_API_KEY",),
        },
    }

    @staticmethod
    def _find_key_for_provider(provider_name: str) -> str:
        name = provider_name.strip().lower()
        # 1. Check direct config settings
        if name == "groq" and getattr(settings, "groq_api_key", None):
            return settings.groq_api_key.strip()
        if name == "gemini" and getattr(settings, "gemini_api_key", None):
            return settings.gemini_api_key.strip()
        if name == "openrouter" and getattr(settings, "openrouter_api_key", None):
            return settings.openrouter_api_key.strip()
        if name == "openai" and getattr(settings, "openai_api_key", None):
            return settings.openai_api_key.strip()
        if name == "openai_compatible" and getattr(settings, "ai_compatible_api_key", None):
            return settings.ai_compatible_api_key.strip()

        # 2. Check environment variables
        spec = AIProviderFactory.PROVIDERS_CATALOG.get(name, {})
        for env_var in spec.get("env_vars", ()):
            val = os.environ.get(env_var, "").strip()
            if val:
                return val

        # 3. Check generic fallback keys by prefix matching
        generic_keys = [
            (settings.ai_compatible_api_key or "").strip(),
            (settings.openai_api_key or "").strip(),
            os.environ.get("APP_AI_KEY", "").strip(),
        ]
        for key in generic_keys:
            if not key:
                continue
            for prefix in spec.get("key_prefixes", ()):
                if key.startswith(prefix):
                    return key

        return ""

    @staticmethod
    def detect_provider(provider_name: str | None = None) -> tuple[str, str, str, str]:
        """Returns (provider_name, api_key, base_url, model)."""
        name = (provider_name or settings.ai_provider or "openai").strip().lower()
        if name not in AIProviderFactory.PROVIDERS_CATALOG:
            name = "openai"

        spec = AIProviderFactory.PROVIDERS_CATALOG[name]
        api_key = AIProviderFactory._find_key_for_provider(name)
        custom_base_url = (settings.ai_compatible_base_url or "").strip()
        custom_model = (settings.ai_compatible_model or "").strip()

        # Specific model settings
        model = spec["default_model"]
        if name == "groq" and getattr(settings, "groq_model", None):
            model = settings.groq_model
        elif name == "gemini" and getattr(settings, "gemini_model", None):
            model = settings.gemini_model
        elif name == "openrouter" and getattr(settings, "openrouter_model", None):
            model = settings.openrouter_model
        elif name == "openai" and getattr(settings, "openai_model", None):
            model = settings.openai_model
        elif custom_model:
            model = custom_model

        base_url = spec["default_url"]
        if name in ("openai_compatible", "openai") and custom_base_url:
            base_url = custom_base_url

        # Fallback auto-detection if no key was found for requested provider:
        if not api_key:
            generic_key = (settings.ai_compatible_api_key or settings.openai_api_key or "").strip()
            if generic_key.startswith("gsk_"):
                return ("groq", generic_key, "https://api.groq.com/openai/v1", "openai/gpt-oss-120b")
            elif generic_key.startswith("AIzaSy"):
                return ("gemini", generic_key, "https://generativelanguage.googleapis.com/v1beta/openai/", "gemini-3.6-flash")
            elif generic_key.startswith("sk-or-"):
                return ("openrouter", generic_key, "https://openrouter.ai/api/v1", "meta-llama/llama-3.3-70b-instruct")

        return (name, api_key, base_url, model)

    @staticmethod
    def is_configured(provider_name: str | None = None) -> bool:
        if not settings.ai_enabled:
            return False
        p_name, api_key, base_url, _ = AIProviderFactory.detect_provider(provider_name)
        if p_name == "ollama":
            return True
        if p_name == "openai_compatible" and (api_key or getattr(settings, "ai_compatible_base_url", None)):
            return True
        return bool(api_key)

    @staticmethod
    def get_configured_providers() -> list[str]:
        """Returns list of configured provider names ordered by preferences."""
        order_raw = getattr(settings, "ai_fallback_chain", "groq,gemini,deepseek,xai,openai,openrouter")
        chain_order = [p.strip().lower() for p in order_raw.split(",") if p.strip()]

        primary = (settings.ai_provider or "").strip().lower()
        if primary and primary in AIProviderFactory.PROVIDERS_CATALOG and primary not in chain_order:
            chain_order.insert(0, primary)

        configured = []
        for name in chain_order:
            if name in AIProviderFactory.PROVIDERS_CATALOG and AIProviderFactory.is_configured(name):
                if name not in configured:
                    configured.append(name)

        # Also add any other configured provider
        for name in AIProviderFactory.PROVIDERS_CATALOG:
            if name not in configured and AIProviderFactory.is_configured(name):
                configured.append(name)

        return configured

    @staticmethod
    def get_all_provider_specs() -> list[dict[str, Any]]:
        """Returns full spec details for all known providers."""
        results = []
        for name, spec in AIProviderFactory.PROVIDERS_CATALOG.items():
            p_name, api_key, base_url, model = AIProviderFactory.detect_provider(name)
            is_conf = bool(api_key) or name == "ollama"
            results.append({
                "name": name,
                "label": spec["label"],
                "model": model,
                "base_url": base_url,
                "is_configured": is_conf,
            })
        return results

    @staticmethod
    def create(provider_name: str | None = None) -> AIProvider:
        raw_name = (provider_name or settings.ai_provider or "").strip().lower()
        if provider_name and raw_name not in AIProviderFactory.PROVIDERS_CATALOG:
            raise AIProviderUnavailableError(f"Unsupported AI provider: {provider_name}")
        p_name, api_key, base_url, model = AIProviderFactory.detect_provider(raw_name)
        if p_name != "ollama" and not api_key and p_name != "openai_compatible":
            raise AIProviderUnavailableError(f"API key is not configured for provider '{p_name}'")
        return OpenAIProvider(
            api_key=api_key or "not-needed",
            default_model=model,
            embedding_model=settings.openai_embedding_model,
            timeout_seconds=min(settings.ai_timeout_seconds, 15.0),
            base_url=base_url or None,
            name=p_name,
        )


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


# Session-level failure tracker: noted failed providers so subsequent prompts skip them immediately
_failed_provider_cooldown: dict[str, float] = {}


class AIService:
    """Provider-neutral service with fast multi-provider failover."""

    @classmethod
    def is_configured(cls, provider_name: str | None = None) -> bool:
        if provider_name:
            return AIProviderFactory.is_configured(provider_name)
        return len(AIProviderFactory.get_configured_providers()) > 0 

    def __init__(self, provider: AIProvider | None = None, fallback_provider: AIProvider | None = None):
        if not settings.ai_enabled and provider is None:
            raise AIProviderUnavailableError("Paper Hub AI is disabled")
        self.provider = provider or AIProviderFactory.create()
        self.fallback_provider = fallback_provider
        if self.fallback_provider is None and settings.ai_fallback_provider:
            try:
                self.fallback_provider = AIProviderFactory.create(settings.ai_fallback_provider)
            except Exception:
                self.fallback_provider = None

    @staticmethod
    def estimate_tokens(messages: list) -> int:
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

    async def generate_with_waterfall(
        self,
        request: AIGenerationRequest,
        preferred_provider: str | None = None,
        per_provider_timeout: float = 10.0,
    ) -> AIGeneration:
        """Attempts healthy providers first, noting failures so subsequent prompts don't retry failed providers."""
        request = self._prepare(request, AICapability.STRUCTURED_OUTPUT if request.response_schema else AICapability.TEXT_GENERATION)

        configured = AIProviderFactory.get_configured_providers()
        candidates: list[str] = []
        if preferred_provider and preferred_provider.strip().lower() in AIProviderFactory.PROVIDERS_CATALOG:
            p_clean = preferred_provider.strip().lower()
            if AIProviderFactory.is_configured(p_clean):
                candidates.append(p_clean)

        for name in configured:
            if name not in candidates:
                candidates.append(name)

        if not candidates and AIProviderFactory.is_configured():
            candidates = [settings.ai_provider or "openai"]

        if not candidates:
            raise AIProviderUnavailableError("No AI providers configured on the server.")

        now = monotonic()
        # Separate candidates into healthy (active) vs in-cooldown (previously failed)
        active_candidates = [p for p in candidates if _failed_provider_cooldown.get(p, 0) < now]
        cooldown_candidates = [p for p in candidates if _failed_provider_cooldown.get(p, 0) >= now]
        ordered_candidates = active_candidates + cooldown_candidates

        errors: list[str] = []
        for prov_name in ordered_candidates:
            started = monotonic()
            try:
                prov = AIProviderFactory.create(prov_name)
                logger.info("Attempting AI generation with provider=%s model=%s", prov.name, prov.default_model)
                response = await asyncio.wait_for(
                    prov.generate(request),
                    timeout=per_provider_timeout,
                )
                # Success: clear from failure memory
                _failed_provider_cooldown.pop(prov_name, None)
                logger.info(
                    "AI generation succeeded: provider=%s model=%s duration_ms=%s",
                    response.provider,
                    response.model,
                    response.duration_ms,
                )
                return response
            except Exception as exc:
                elapsed_ms = round((monotonic() - started) * 1000)
                # Note failure in session memory for 5 minutes so it doesn't slow down the user again
                _failed_provider_cooldown[prov_name] = monotonic() + 300.0
                logger.warning(
                    "AI provider '%s' failed after %sms: %s. Noted failure; failing over to next provider...",
                    prov_name,
                    elapsed_ms,
                    exc,
                )
                errors.append(f"{prov_name}: {exc}")
                continue

        raise AIProviderUnavailableError(f"All AI providers failed: {'; '.join(errors)}")

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
        except (AIProviderUnavailableError, AIRateLimitError, Exception) as exc:
            logger.warning("ai_request provider=%s success=false code=%s duration_ms=%s", self.provider.name, getattr(exc, "code", "error"), round((monotonic() - started) * 1000))
            if not self.fallback_provider:
                raise
            logger.warning("ai_fallback provider=%s fallback_provider=%s", self.provider.name, self.fallback_provider.name)
            return await getattr(self.fallback_provider, method)(request)
