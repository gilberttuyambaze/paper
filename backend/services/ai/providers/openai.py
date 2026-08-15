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
    def _input(messages: list) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for message in messages:
            if isinstance(message.content, str):
                content: Any = message.content
            else:
                content = []
                for part in message.content:
                    if part.get("type") == "text":
                        content.append({"type": "input_text", "text": part.get("text", "")})
                    elif part.get("type") == "image_url":
                        image_url = part.get("image_url", {})
                        content.append({"type": "input_image", "image_url": image_url.get("url", "")})
                    else:
                        raise AIInvalidRequestError("Unsupported multimodal content part")
            items.append({"role": message.role, "content": content})
        return items

    @staticmethod
    def _usage(usage: Any) -> AIUsage | None:
        if not usage:
            return None
        return AIUsage(
            input_tokens=getattr(usage, "input_tokens", None),
            output_tokens=getattr(usage, "output_tokens", None),
            total_tokens=getattr(usage, "total_tokens", None),
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

    async def generate(self, request: AIGenerationRequest) -> AIGeneration:
        started = monotonic()
        try:
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
        except Exception as exc:
            raise self._normalize_error(exc) from exc

    async def stream(self, request: AIGenerationRequest) -> AsyncIterator[str]:
        try:
            stream = await self.client.responses.create(**self._params(request), stream=True)
            async for event in stream:
                if getattr(event, "type", "") == "response.output_text.delta":
                    delta = getattr(event, "delta", "")
                    if delta:
                        yield delta
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
        if isinstance(exc, (AuthenticationError, PermissionDeniedError)):
            return AIAuthenticationError()
        if isinstance(exc, RateLimitError):
            return AIRateLimitError()
        if isinstance(exc, (APITimeoutError, asyncio.TimeoutError, httpx.TimeoutException)):
            return AITimeoutError()
        if isinstance(exc, NotFoundError):
            return AIModelUnavailableError()
        if isinstance(exc, BadRequestError):
            message = str(exc).lower()
            if "policy" in message or "safety" in message:
                return AIContentPolicyError()
            return AIInvalidRequestError()
        if isinstance(exc, (APIConnectionError, APIStatusError, httpx.HTTPError)):
            return AIProviderUnavailableError()
        return AIProviderUnavailableError()
