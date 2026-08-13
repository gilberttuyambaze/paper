"""Backward-compatible facade for the public AI Hub routes.

The actual provider interaction lives in :mod:`services.ai`; this module keeps
the existing request/response contracts intact while routes migrate gradually.
"""

from collections.abc import AsyncGenerator

from schemas.aihub import GenImgRequest, GenImgResponse, GenTxtRequest, GenTxtResponse
from services.ai.base import AIGenerationRequest, AIMessage
from services.ai.service import AIService


class InvalidImageInputError(ValueError):
    """Compatibility exception retained for callers of the legacy facade."""


class AIHubService:
    def __init__(self, service: AIService | None = None, user_id: str | None = None):
        self.service = service or AIService()
        self.user_id = user_id

    @staticmethod
    def _messages(request: GenTxtRequest) -> list[AIMessage]:
        messages: list[AIMessage] = []
        for message in request.messages:
            content = message.content
            if isinstance(content, list):
                content = [part.model_dump() for part in content]
            messages.append(AIMessage(role=message.role, content=content))
        return messages

    def _request(self, request: GenTxtRequest) -> AIGenerationRequest:
        return AIGenerationRequest(
            messages=self._messages(request),
            model=request.model,
            temperature=request.temperature,
            max_output_tokens=request.max_tokens,
            user_id=self.user_id,
        )

    async def gentxt(self, request: GenTxtRequest) -> GenTxtResponse:
        result = await self.service.generate(self._request(request))
        usage = None
        if result.usage:
            usage = {
                "prompt_tokens": result.usage.input_tokens,
                "completion_tokens": result.usage.output_tokens,
                "total_tokens": result.usage.total_tokens,
            }
        return GenTxtResponse(content=result.content, model=result.model, usage=usage)

    async def gentxt_stream(self, request: GenTxtRequest) -> AsyncGenerator[str, None]:
        async for content in self.service.stream(self._request(request)):
            yield content

    async def genimg(self, request: GenImgRequest) -> GenImgResponse:
        try:
            return await self.service.generate_image(request, user_id=self.user_id)
        except Exception as exc:
            if "base64" in str(exc).lower() or "image editing" in str(exc).lower():
                raise InvalidImageInputError(str(exc)) from exc
            raise
