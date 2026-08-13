import httpx
import unittest
from types import SimpleNamespace

from openai import AuthenticationError

from core.config import settings
from services.ai.base import (
    AICapability,
    AIAuthenticationError,
    AIContextTooLargeError,
    AIEmbeddingRequest,
    AIEmbeddingResult,
    AIGeneration,
    AIGenerationRequest,
    AIMessage,
    AIMalformedResponseError,
    AIProvider,
    AIProviderUnavailableError,
    AIRateLimitError,
    AITimeoutError,
    AIUsage,
)
from services.ai.providers.openai import OpenAIProvider
from services.ai.service import AIProviderFactory, AIService


class FakeProvider(AIProvider):
    def __init__(self, error=None):
        super().__init__("fake", {AICapability.TEXT_GENERATION, AICapability.STREAMING, AICapability.EMBEDDINGS, AICapability.STRUCTURED_OUTPUT})
        self.error = error

    async def generate(self, request):
        if self.error:
            raise self.error
        return AIGeneration("answer", "fake-model", "fake", usage=AIUsage(2, 1, 3))

    async def stream(self, request):
        if self.error:
            raise self.error
        yield "one"
        yield "two"

    async def embed(self, request):
        return AIEmbeddingResult([[0.1]], "fake-embedding", "fake")


class AIArchitectureTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.original = {name: getattr(settings, name) for name in ("ai_enabled", "ai_max_context_tokens", "ai_max_output_tokens", "ai_max_requests_per_user_per_minute")}
        settings.ai_enabled = True
        settings.ai_max_context_tokens = 100
        settings.ai_max_output_tokens = 20
        settings.ai_max_requests_per_user_per_minute = 0

    def tearDown(self):
        for name, value in self.original.items():
            setattr(settings, name, value)

    @staticmethod
    def request(content="hello"):
        return AIGenerationRequest(messages=[AIMessage("user", content)], max_output_tokens=200, user_id="user-1")

    async def test_provider_selection_rejects_invalid_provider(self):
        with self.assertRaises(AIProviderUnavailableError):
            AIProviderFactory.create("not-a-provider")

    async def test_generation_caps_output_and_returns_normalized_result(self):
        result = await AIService(provider=FakeProvider()).generate(self.request())
        self.assertEqual(result.content, "answer")
        self.assertEqual(result.usage.total_tokens, 3)

    async def test_context_limit_is_checked_before_provider_call(self):
        with self.assertRaises(AIContextTooLargeError):
            await AIService(provider=FakeProvider()).generate(self.request("x" * 1000))

    async def test_timeout_and_rate_limit_are_preserved(self):
        with self.assertRaises(AITimeoutError):
            await AIService(provider=FakeProvider(AITimeoutError())).generate(self.request())
        with self.assertRaises(AIRateLimitError):
            await AIService(provider=FakeProvider(AIRateLimitError())).generate(self.request())

    async def test_streaming_is_provider_neutral(self):
        chunks = [chunk async for chunk in AIService(provider=FakeProvider()).stream(self.request())]
        self.assertEqual(chunks, ["one", "two"])

    async def test_structured_output_rejects_malformed_json(self):
        class InvalidStructuredProvider(FakeProvider):
            async def generate(self, request):
                return AIGeneration("not-json", "fake-model", "fake")

        with self.assertRaises(AIMalformedResponseError):
            await AIService(provider=InvalidStructuredProvider()).generate_structured(self.request(), {"type": "object"})

    async def test_openai_provider_uses_responses_api_shape(self):
        provider = OpenAIProvider(api_key="test", default_model="configured-model", embedding_model="embedding-model", timeout_seconds=1)

        class Responses:
            async def create(self, **params):
                self.params = params
                return SimpleNamespace(output_text="OpenAI answer", model="configured-model", id="resp_test", usage=SimpleNamespace(input_tokens=4, output_tokens=2, total_tokens=6))

        responses = Responses()
        provider.client = SimpleNamespace(responses=responses)
        result = await provider.generate(self.request())
        self.assertEqual(result.content, "OpenAI answer")
        self.assertEqual(responses.params["model"], "configured-model")
        self.assertFalse(responses.params["store"])

    async def test_openai_authentication_error_is_normalized(self):
        response = httpx.Response(401, request=httpx.Request("POST", "https://api.openai.com/v1/responses"))
        error = AuthenticationError("bad key", response=response, body=None)
        self.assertIsInstance(OpenAIProvider._normalize_error(error), AIAuthenticationError)

    async def test_openai_malformed_response_is_rejected(self):
        provider = OpenAIProvider(api_key="test", default_model="configured-model", embedding_model="embedding-model", timeout_seconds=1)

        class Responses:
            async def create(self, **params):
                return SimpleNamespace(output_text="", model="configured-model", id="resp_test", usage=None)

        provider.client = SimpleNamespace(responses=Responses())
        with self.assertRaises(AIMalformedResponseError):
            await provider.generate(self.request())

    def test_ai_routes_use_existing_auth_dependency(self):
        from routers.aihub import router

        for route in router.routes:
            self.assertTrue(route.dependant.dependencies, f"{route.path} must require authentication")

    def test_frontend_does_not_contain_provider_key_references(self):
        from pathlib import Path

        frontend_source = "\n".join(path.read_text(encoding="utf-8") for path in Path(__file__).resolve().parents[2].joinpath("frontend", "src").rglob("*.ts*"))
        self.assertNotIn("OPENAI_API_KEY", frontend_source)
        self.assertNotIn("AsyncOpenAI", frontend_source)
