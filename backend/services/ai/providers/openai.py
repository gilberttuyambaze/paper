"""OpenAI adapter using the current Responses API for text workloads."""

from __future__ import annotations

import asyncio
import base64
import io
from collections.abc import AsyncIterator
from time import monotonic
from typing import Any

import httpx
from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
    AuthenticationError,
    BadRequestError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
)

from services.ai.base import (
    AICapability,
    AIAuthenticationError,
    AIContentPolicyError,
    AIEmbeddingRequest,
    AIEmbeddingResult,
    AIError,
    AIGeneration,
    AIGenerationRequest,
    AIInvalidRequestError,
    AIMalformedResponseError,
    AIModelUnavailableError,
    AIProvider,
    AIProviderUnavailableError,
    AIRateLimitError,
    AITimeoutError,
    AIUsage,
)


class OpenAIProvider(AIProvider):
    """First-class OpenAI provider; models remain configuration/request driven."""

    def __init__(self, *, api_key: str, default_model: str, embedding_model: str, timeout_seconds: float, base_url: str | None = None, name: str = "openai"):
        if not api_key:
            raise AIAuthenticationError("OpenAI API key is not configured")
        super().__init__(
            name=name,
            capabilities={
                AICapability.TEXT_GENERATION,
                AICapability.STREAMING,
                AICapability.STRUCTURED_OUTPUT,
                AICapability.VISION,
                AICapability.EMBEDDINGS,
                AICapability.IMAGE_GENERATION,
            },
        )
        self.default_model = default_model
        self.embedding_model = embedding_model
        self.timeout_seconds = timeout_seconds
        # Endpoint-level fallbacks are faster and more useful than SDK retries
        # for interactive study help, which has a strict response budget.
        self.client = AsyncOpenAI(api_key=api_key, base_url=base_url, timeout=timeout_seconds, max_retries=0)

    @staticmethod
    def _image_upload(image: str, index: int) -> io.BytesIO:
        if not image.startswith("data:") or "," not in image:
            raise AIInvalidRequestError("Image editing requires a base64 data URI")
        header, encoded = image.split(",", 1)
        try:
            upload = io.BytesIO(base64.b64decode(encoded))
        except Exception as exc:
            raise AIInvalidRequestError("Image data URI is not valid base64") from exc
        upload.name = f"image_{index}.png"  # type: ignore[attr-defined]
        return upload

    async def generate_image(self, request: Any, default_model: str) -> Any:
        """Translate the legacy Paper Hub image schema inside the provider adapter."""
        try:
            model = request.model or default_model
            if request.image:
                inputs = [request.image] if isinstance(request.image, str) else request.image
                files = [self._image_upload(image, index) for index, image in enumerate(inputs, 1)]
                response = await self.client.images.edit(
                    model=model,
                    image=files[0] if len(files) == 1 else files,
                    prompt=request.prompt,
                    size=request.size,
                    n=request.n,
                )
            else:
                response = await self.client.images.generate(
                    model=model,
                    prompt=request.prompt,
                    size=request.size,
                    quality=request.quality,
                    n=request.n,
                )
            images = []
            for item in response.data:
                if getattr(item, "url", None):
                    images.append(item.url)
                elif getattr(item, "b64_json", None):
                    images.append(f"data:image/png;base64,{item.b64_json}")
            if not images:
                raise AIMalformedResponseError("OpenAI image response did not contain an image")
            from schemas.aihub import GenImgResponse

            return GenImgResponse(
                images=images,
                model=model,
                revised_prompt=getattr(response.data[0], "revised_prompt", None),
            )
        except Exception as exc:
            raise self._normalize_error(exc) from exc

    @staticmethod
    def _chat_messages(messages: list) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for message in messages:
            if isinstance(message.content, str):
                items.append({"role": message.role, "content": message.content})
            elif isinstance(message.content, list):
                content: list[dict[str, Any]] = []
                for part in message.content:
                    if part.get("type") in ("text", "input_text"):
                        content.append({"type": "text", "text": part.get("text", "")})
                    elif part.get("type") in ("image_url", "input_image"):
                        image_url = part.get("image_url", {})
                        url_str = image_url.get("url", "") if isinstance(image_url, dict) else str(image_url or "")
                        content.append({"type": "image_url", "image_url": {"url": url_str}})
                    else:
                        content.append(part)
                items.append({"role": message.role, "content": content})
            else:
                items.append({"role": message.role, "content": str(message.content)})
        return items

    @staticmethod
    def _input(messages: list) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for message in messages:
            if isinstance(message.content, str):
                content: Any = message.content
            else:
                content = []
                for part in message.content:
                    if part.get("type") in ("text", "input_text"):
                        content.append({"type": "input_text", "text": part.get("text", "")})
                    elif part.get("type") in ("image_url", "input_image"):
                        image_url = part.get("image_url", {})
                        url_str = image_url.get("url", "") if isinstance(image_url, dict) else str(image_url or "")
                        content.append({"type": "input_image", "image_url": url_str})
                    else:
                        raise AIInvalidRequestError("Unsupported multimodal content part")
            items.append({"role": message.role, "content": content})
        return items

    @staticmethod
    def _usage(usage: Any) -> AIUsage | None:
        if not usage:
            return None
        input_tokens = getattr(usage, "prompt_tokens", None) if hasattr(usage, "prompt_tokens") else getattr(usage, "input_tokens", None)
        output_tokens = getattr(usage, "completion_tokens", None) if hasattr(usage, "completion_tokens") else getattr(usage, "output_tokens", None)
        total_tokens = getattr(usage, "total_tokens", None)
        return AIUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
        )

    def _params(self, request: AIGenerationRequest) -> dict[str, Any]:
        params: dict[str, Any] = {
            "model": request.model or self.default_model,
            "input": self._input(request.messages),
            "max_output_tokens": request.max_output_tokens,
            "temperature": request.temperature,
            "store": False,
        }
        if request.response_schema:
            params["text"] = {
                "format": {
                    "type": "json_schema",
                    "name": request.response_schema_name,
                    "schema": request.response_schema,
                    "strict": True,
                }
            }
        return {key: value for key, value in params.items() if value is not None}

    @staticmethod
    def _normalize_model_name(model_name: str) -> str:
        name = model_name.strip()
        aliases = {
            "gpt-4.1-mini": "gpt-4o-mini",
            "gpt-4-mini": "gpt-4o-mini",
            "gpt-4.1": "gpt-4o",
            "gpt-4.5": "gpt-4o",
            "gpt-4": "gpt-4o",
            "gpt-3.5": "gpt-3.5-turbo",
        }
        return aliases.get(name.lower(), name)

    def _chat_params(self, request: AIGenerationRequest) -> dict[str, Any]:
        raw_model = request.model or self.default_model
        params: dict[str, Any] = {
            "model": request.model or self.default_model,
            "model": self._normalize_model_name(raw_model),
            "messages": self._chat_messages(request.messages),
            "temperature": request.temperature,
        }
        if request.max_output_tokens is not None:
            params["max_tokens"] = request.max_output_tokens
        if request.response_schema:
            try:
                params["response_format"] = {
                    "type": "json_schema",
                    "json_schema": {
                        "name": request.response_schema_name or "response",
                        "schema": request.response_schema,
                        "strict": True,
                    },
                }
            except Exception:
                params["response_format"] = {"type": "json_object"}
        return {key: value for key, value in params.items() if value is not None}

    async def generate(self, request: AIGenerationRequest) -> AIGeneration:
        started = monotonic()
        try:
            # Check if standard Chat Completions is available on the client
            if hasattr(self.client, "chat") and hasattr(self.client.chat, "completions"):
                response = await self.client.chat.completions.create(**self._chat_params(request))
                content = ""
                if hasattr(response, "choices") and response.choices:
                    choice = response.choices[0]
                    content = choice.message.content if hasattr(choice, "message") and hasattr(choice.message, "content") else getattr(choice, "text", "")
                elif hasattr(response, "output_text"):
                    content = response.output_text

                if not isinstance(content, str) or not content.strip():
                    raise AIMalformedResponseError("AI response did not contain text output")

                return AIGeneration(
                    content=content,
                    model=str(getattr(response, "model", request.model or self.default_model)),
                    provider=self.name,
                    request_id=getattr(response, "_request_id", None) or getattr(response, "id", None),
                    usage=self._usage(getattr(response, "usage", None)),
                    duration_ms=round((monotonic() - started) * 1000),
                )
            elif hasattr(self.client, "responses"):
                response = await self.client.responses.create(**self._params(request))
                content = getattr(response, "output_text", None)
                if not isinstance(content, str) or not content.strip():
                    raise AIMalformedResponseError("OpenAI response did not contain text output")
                return AIGeneration(
                    content=content,
                    model=str(getattr(response, "model", request.model or self.default_model)),
                    provider=self.name,
                    request_id=getattr(response, "_request_id", None) or getattr(response, "id", None),
                    usage=self._usage(getattr(response, "usage", None)),
                    duration_ms=round((monotonic() - started) * 1000),
                )
            else:
                raise AIProviderUnavailableError("OpenAI client does not support chat or responses")
        except Exception as exc:
            raise self._normalize_error(exc) from exc

    async def stream(self, request: AIGenerationRequest) -> AsyncIterator[str]:
        try:
            if hasattr(self.client, "chat") and hasattr(self.client.chat, "completions"):
                stream_or_coro = self.client.chat.completions.create(**self._chat_params(request), stream=True)
                if asyncio.iscoroutine(stream_or_coro) or hasattr(stream_or_coro, "__await__"):
                    stream = await stream_or_coro
                else:
                    stream = stream_or_coro
                async for chunk in stream:
                    if hasattr(chunk, "choices") and chunk.choices:
                        delta = chunk.choices[0].delta
                        content = getattr(delta, "content", None) or ""
                        if content:
                            yield content
            elif hasattr(self.client, "responses"):
                stream_or_coro = self.client.responses.create(**self._params(request), stream=True)
                if asyncio.iscoroutine(stream_or_coro) or hasattr(stream_or_coro, "__await__"):
                    stream = await stream_or_coro
                else:
                    stream = stream_or_coro
                async for event in stream:
                    if getattr(event, "type", "") == "response.output_text.delta":
                        delta = getattr(event, "delta", "")
                        if delta:
                            yield delta
            else:
                raise AIProviderUnavailableError("OpenAI client does not support chat or responses streaming")
        except Exception as exc:
            raise self._normalize_error(exc) from exc

    async def embed(self, request: AIEmbeddingRequest) -> AIEmbeddingResult:
        try:
            response = await self.client.embeddings.create(
                model=request.model or self.embedding_model,
                input=request.input,
            )
            vectors = [item.embedding for item in response.data]
            if len(vectors) != len(request.input):
                raise AIMalformedResponseError("OpenAI embedding response had an unexpected item count")
            return AIEmbeddingResult(
                vectors=vectors,
                model=str(getattr(response, "model", request.model or self.embedding_model)),
                provider=self.name,
                usage=self._usage(getattr(response, "usage", None)),
            )
        except Exception as exc:
            raise self._normalize_error(exc) from exc

    @staticmethod
    def _normalize_error(exc: Exception) -> AIError:
        if isinstance(exc, AIError):
            return exc
        raw_msg = str(exc)
        if isinstance(exc, RateLimitError):
            msg_lower = raw_msg.lower()
            if "quota" in msg_lower or "credit" in msg_lower or "billing" in msg_lower or "balance" in msg_lower:
                return AIRateLimitError("OpenAI account balance is exhausted (429 Insufficient Quota). Add credits at platform.openai.com or switch AI_PROVIDER in backend/.env.local.")
            return AIRateLimitError("AI provider is temporarily rate limited. Please try again shortly.")
        if isinstance(exc, (AuthenticationError, PermissionDeniedError)):
            return AIAuthenticationError(f"AI authentication failed: {raw_msg}")
        if isinstance(exc, (APITimeoutError, asyncio.TimeoutError, httpx.TimeoutException)):
            return AITimeoutError("AI request timed out. Please try again.")
        if isinstance(exc, NotFoundError):
            return AIModelUnavailableError(f"AI model not found: {raw_msg}")
        if isinstance(exc, BadRequestError):
            msg_lower = raw_msg.lower()
            if "policy" in msg_lower or "safety" in msg_lower:
                return AIContentPolicyError()
            return AIInvalidRequestError(f"Invalid AI request: {raw_msg}")
        if isinstance(exc, (APIConnectionError, APIStatusError, httpx.HTTPError)):
            return AIProviderUnavailableError(f"AI connection failed: {raw_msg}")
        return AIProviderUnavailableError(f"AI provider unavailable: {raw_msg}")
