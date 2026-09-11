import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from core.config import settings
from services.ai.base import (
    AIGenerationRequest,
    AIMessage,
    AIProviderUnavailableError,
    AIUsage,
)
from services.ai.providers.openai import OpenAIProvider
from services.ai.service import AIProviderFactory, AIService


class StudyAIAndProviderTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.original_settings = {
            "ai_enabled": settings.ai_enabled,
            "ai_provider": settings.ai_provider,
            "openai_api_key": settings.openai_api_key,
            "ai_compatible_api_key": settings.ai_compatible_api_key,
            "ai_compatible_base_url": settings.ai_compatible_base_url,
            "ai_compatible_model": settings.ai_compatible_model,
            "ai_max_context_tokens": settings.ai_max_context_tokens,
            "ai_max_output_tokens": settings.ai_max_output_tokens,
            "ai_max_requests_per_user_per_minute": settings.ai_max_requests_per_user_per_minute,
            "ai_timeout_seconds": settings.ai_timeout_seconds,
        }
        settings.ai_enabled = True
        settings.ai_max_context_tokens = 8000
        settings.ai_max_output_tokens = 2048
        settings.ai_max_requests_per_user_per_minute = 0
        settings.ai_timeout_seconds = 30.0

    def tearDown(self):
        for key, value in self.original_settings.items():
            setattr(settings, key, value)

    async def test_openai_provider_uses_chat_completions(self):
        provider = OpenAIProvider(
            api_key="sk-test-key",
            default_model="gpt-4.1-mini",
            embedding_model="text-embedding-3-small",
            timeout_seconds=30.0,
        )

        mock_choice = SimpleNamespace(
            message=SimpleNamespace(content="Detailed solution to exam question: 1. Core theorem..."),
            finish_reason="stop",
        )
        mock_usage = SimpleNamespace(prompt_tokens=42, completion_tokens=18, total_tokens=60)
        mock_response = SimpleNamespace(
            choices=[mock_choice],
            model="gpt-4.1-mini",
            id="chatcmpl-test-123",
            usage=mock_usage,
        )

        class MockCompletions:
            async def create(self, **kwargs):
                self.called_kwargs = kwargs
                return mock_response

        completions = MockCompletions()
        provider.client = SimpleNamespace(chat=SimpleNamespace(completions=completions))

        req = AIGenerationRequest(
            messages=[
                AIMessage(role="system", content="You are a tutor"),
                AIMessage(role="user", content="Explain paper"),
            ],
            max_output_tokens=1000,
            temperature=0.3,
            user_id="user-42",
        )

        result = await provider.generate(req)
        self.assertEqual(result.content, "Detailed solution to exam question: 1. Core theorem...")
        self.assertEqual(result.model, "gpt-4.1-mini")
        self.assertIsNotNone(result.usage)
        self.assertEqual(result.usage.input_tokens, 42)
        self.assertEqual(result.usage.output_tokens, 18)
        self.assertEqual(result.usage.total_tokens, 60)

        # Verify chat messages formatting and model normalization
        called = completions.called_kwargs
        self.assertEqual(called["model"], "gpt-4o-mini")
        self.assertEqual(called["max_tokens"], 1000)
        self.assertEqual(called["temperature"], 0.3)
        self.assertEqual(
            called["messages"],
            [
                {"role": "system", "content": "You are a tutor"},
                {"role": "user", "content": "Explain paper"},
            ],
        )

    async def test_openai_provider_streaming_chat_completions(self):
        provider = OpenAIProvider(
            api_key="sk-test",
            default_model="gpt-4.1-mini",
            embedding_model="text-embedding-3-small",
            timeout_seconds=30.0,
        )

        class MockStreamChunk:
            def __init__(self, text):
                self.choices = [SimpleNamespace(delta=SimpleNamespace(content=text))]

        async def mock_stream(**kwargs):
            for part in ["Part 1: ", "Calculus ", "Derivation"]:
                yield MockStreamChunk(part)

        class MockCompletions:
            def create(self, **kwargs):
                return mock_stream(**kwargs)

        provider.client = SimpleNamespace(chat=SimpleNamespace(completions=MockCompletions()))

        req = AIGenerationRequest(
            messages=[AIMessage(role="user", content="Stream this")],
            user_id="user-1",
        )
        streamed = [chunk async for chunk in provider.stream(req)]
        self.assertEqual("".join(streamed), "Part 1: Calculus Derivation")

    def test_provider_factory_and_is_configured_logic(self):
        # When AI is disabled
        settings.ai_enabled = False
        self.assertFalse(AIService.is_configured())

        # When AI is enabled with OpenAI
        settings.ai_enabled = True
        settings.ai_provider = "openai"
        settings.openai_api_key = None
        self.assertFalse(AIService.is_configured())

        settings.openai_api_key = "sk-live-test"
        self.assertTrue(AIService.is_configured())

        # When configured with compatible provider (e.g. DeepSeek or Groq)
        settings.ai_provider = "deepseek"
        settings.openai_api_key = None
        settings.ai_compatible_api_key = "sk-deepseek-key"
        self.assertTrue(AIService.is_configured())

        provider = AIProviderFactory.create("deepseek")
        self.assertEqual(provider.name, "deepseek")
        self.assertEqual(provider.default_model, "deepseek-chat")

        # Groq
        groq_provider = AIProviderFactory.create("groq")
        self.assertEqual(groq_provider.name, "groq")
        self.assertEqual(groq_provider.default_model, "llama-3.3-70b-versatile")

        # Gemini
        gemini_provider = AIProviderFactory.create("gemini")
        self.assertEqual(gemini_provider.name, "gemini")
        self.assertEqual(gemini_provider.default_model, "gemini-2.0-flash")

        # Ollama
        ollama_provider = AIProviderFactory.create("ollama")
        self.assertEqual(ollama_provider.name, "ollama")
        self.assertEqual(ollama_provider.default_model, "llama3.2")
        self.assertTrue(AIProviderFactory.is_configured("ollama"))

    def test_fallback_response_formatting(self):
        from models.papers import Papers
        from routers.study_ai import _build_fallback_response

        dummy_paper = Papers(
            id=1,
            title="Advanced Algorithms 2024",
            course_code="CSC401",
            course_name="Algorithms",
            department="Computer Science",
            college="CST",
            year=2024,
            paper_type="Final Exam",
            lecturer="Dr. Smith",
            description="End of semester exam",
        )

        explain_res = _build_fallback_response("explain", dummy_paper, [], [], fallback_reason="cloud_ai_not_configured")
        self.assertEqual(explain_res["model"], "local-study-guide")
        self.assertEqual(explain_res["fallback_reason"], "cloud_ai_not_configured")
        self.assertIn("## Study Guide: CSC401 - Algorithms", explain_res["content"])
        self.assertIn("### 1. Paper Overview", explain_res["content"])
        self.assertIn("### 2. High-Yield Revision Strategy", explain_res["content"])

        summarize_res = _build_fallback_response("summarize", dummy_paper, [], [])
        self.assertIn("## Study Brief: Advanced Algorithms 2024", summarize_res["content"])

        question_res = _build_fallback_response("question", dummy_paper, [], [], question="What is Dijkstra algorithm?")
        self.assertIn("## Local Paper Study Guide", question_res["content"])
        self.assertIn("What is Dijkstra algorithm?", question_res["content"])

        quiz_res = _build_fallback_response("quiz", dummy_paper, [], [])
        self.assertIn("## Practice Self-Assessment Quiz: CSC401", quiz_res["content"])

        formulas_res = _build_fallback_response("formulas", dummy_paper, [], [])
        self.assertIn("## Core Formulas & Definitions: CSC401", formulas_res["content"])

        pitfalls_res = _build_fallback_response("pitfalls", dummy_paper, [], [])
        self.assertIn("## Common Exam Pitfalls & Mistakes: CSC401", pitfalls_res["content"])

        broad_question_res = _build_fallback_response("question", dummy_paper, [], [], question="what is on this document", extracted_text="Section 1: Binary Search Trees\nSection 2: Dynamic Programming")
        self.assertIn("## Local Paper Study Guide", broad_question_res["content"])
        self.assertIn("Section 1: Binary Search Trees", broad_question_res["content"])

    async def test_study_paper_endpoint_invokes_ai_service_when_configured(self):
        from models.papers import Papers
        from routers.study_ai import AIActionRequest, study_paper
        from schemas.auth import UserResponse
        from services.ai.base import AIGeneration, AIUsage

        dummy_paper = Papers(
            id=10,
            title="Database Systems Midterm",
            course_code="CSC302",
            course_name="Database Systems",
            department="Computer Science",
            college="CST",
            year=2024,
            paper_type="Midterm",
            file_key="papers/test_paper.pdf",
        )

        mock_db = AsyncMock()
        mock_db.get.return_value = dummy_paper

        mock_scalars = SimpleNamespace(all=lambda: [])
        mock_result = SimpleNamespace(scalars=lambda: mock_scalars)
        mock_db.execute.return_value = mock_result

        mock_user = UserResponse(
            id="user-123",
            email="student@ur.ac.rw",
            role="student",
            status="active",
            is_verified=True,
            created_at=None,
        )

        with patch.object(AIService, "is_configured", return_value=True), \
             patch("routers.study_ai.HybridRetrievalService") as mock_retrieval_cls, \
             patch("routers.study_ai.AIService") as mock_ai_service_cls:

            mock_retrieval = AsyncMock()
            mock_retrieval.retrieve.return_value = []
            mock_retrieval_cls.return_value = mock_retrieval

            mock_ai = AsyncMock()
            mock_ai.analyze_paper.return_value = AIGeneration(
                content="## Comprehensive Revision Guide\n1. Normalization (1NF, 2NF, 3NF, BCNF)...",
                model="deepseek-chat",
                provider="deepseek",
                usage=AIUsage(100, 50, 150),
            )
            mock_ai_service_cls.return_value = mock_ai

            payload = AIActionRequest(action="explain")
            response = await study_paper(
                paper_id=10,
                payload=payload,
                _current_user=mock_user,
                db=mock_db,
            )

            self.assertEqual(response["model"], "deepseek-chat")
            self.assertIn("Comprehensive Revision Guide", response["content"])
            self.assertEqual(response["usage"]["total_tokens"], 150)
            mock_ai.analyze_paper.assert_called_once()
