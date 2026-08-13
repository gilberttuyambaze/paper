"""Provider-neutral contracts for Paper Hub AI.

No route or paper workflow should import a provider SDK directly.  Provider
adapters translate these small request/response objects to their own APIs.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class AICapability(str, Enum):
    TEXT_GENERATION = "text_generation"
    STREAMING = "streaming"
    STRUCTURED_OUTPUT = "structured_output"
    VISION = "vision"
    EMBEDDINGS = "embeddings"
    IMAGE_GENERATION = "image_generation"


@dataclass(frozen=True)
class AIMessage:
    role: str
    content: str | list[dict[str, Any]]


@dataclass(frozen=True)
class AIGenerationRequest:
    messages: list[AIMessage]
    model: str | None = None
    temperature: float | None = None
    max_output_tokens: int | None = None
    response_schema: dict[str, Any] | None = None
    response_schema_name: str = "paper_hub_response"
    user_id: str | None = None


@dataclass(frozen=True)
class AIUsage:
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None


@dataclass(frozen=True)
class AIGeneration:
    content: str
    model: str
    provider: str
    request_id: str | None = None
    usage: AIUsage | None = None
    duration_ms: int | None = None


@dataclass(frozen=True)
class AIEmbeddingRequest:
    input: list[str]
    model: str | None = None
    user_id: str | None = None


@dataclass(frozen=True)
class AIEmbeddingResult:
    vectors: list[list[float]]
    model: str
    provider: str
    usage: AIUsage | None = None


class AIError(Exception):
    """Safe, normalized failure for API consumers."""

    code = "ai_error"
    public_message = "The AI service could not complete the request."

    def __init__(self, message: str | None = None):
        super().__init__(message or self.public_message)


class AIProviderUnavailableError(AIError):
    code = "provider_unavailable"
    public_message = "The configured AI provider is unavailable."


class AIAuthenticationError(AIError):
    code = "authentication_failed"
    public_message = "The AI provider credentials are invalid or unavailable."


class AIRateLimitError(AIError):
    code = "rate_limited"
    public_message = "The AI provider is rate limited. Please try again shortly."


class AITimeoutError(AIError):
    code = "timeout"
    public_message = "The AI request timed out. Please try again."


class AIContextTooLargeError(AIError):
    code = "context_too_large"
    public_message = "The selected paper context is too large for this request."


class AIInvalidRequestError(AIError):
    code = "invalid_request"
    public_message = "The AI request is invalid."


class AIModelUnavailableError(AIError):
    code = "model_unavailable"
    public_message = "The configured AI model is unavailable."


class AIContentPolicyError(AIError):
    code = "content_policy"
    public_message = "The provider could not process this request."


class AIMalformedResponseError(AIError):
    code = "malformed_response"
    public_message = "The AI provider returned an invalid response."


@dataclass
class AIProvider(ABC):
    name: str
    capabilities: set[AICapability] = field(default_factory=set)

    def supports(self, capability: AICapability) -> bool:
        return capability in self.capabilities

    @abstractmethod
    async def generate(self, request: AIGenerationRequest) -> AIGeneration:
        raise NotImplementedError

    @abstractmethod
    async def stream(self, request: AIGenerationRequest) -> AsyncIterator[str]:
        raise NotImplementedError

    @abstractmethod
    async def embed(self, request: AIEmbeddingRequest) -> AIEmbeddingResult:
        raise NotImplementedError
