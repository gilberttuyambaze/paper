import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from core.config import settings
from services.ai.base import (
    AIGenerationRequest,
    AIGeneration,
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
            "groq_api_key": getattr(settings, "groq_api_key", None),
            "groq_fallback_api_key": getattr(settings, "groq_fallback_api_key", None),
            "gemini_api_key": getattr(settings, "gemini_api_key", None),
            "openrouter_api_key": getattr(settings, "openrouter_api_key", None),
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

    def test_study_ai_prompt_requires_human_readable_math_tables_and_provenance(self):
        """Presentation guidance is part of the provider-independent contract."""
        from routers.study_ai import STUDY_AI_SYSTEM_PROMPT

        self.assertIn("real GitHub-Flavored Markdown tables", STUDY_AI_SYSTEM_PROMPT)
        self.assertIn("inline mathematics is \\(F = ma\\)", STUDY_AI_SYSTEM_PROMPT)
        self.assertIn("display mathematics is \\[F = ma\\]", STUDY_AI_SYSTEM_PROMPT)
        self.assertIn("Given, Find, Formula, Substitution, Calculation, and Answer", STUDY_AI_SYSTEM_PROMPT)
        self.assertIn("Do not reveal hidden chain-of-thought", STUDY_AI_SYSTEM_PROMPT)
        self.assertIn("normalized notation", STUDY_AI_SYSTEM_PROMPT)
        self.assertIn("**Source:** Page 3", STUDY_AI_SYSTEM_PROMPT)

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
        settings.groq_api_key = None
        settings.gemini_api_key = None
        settings.openrouter_api_key = None
        settings.ai_compatible_api_key = None
        self.assertFalse(AIService.is_configured("openai"))

        settings.openai_api_key = "sk-live-test"
        self.assertTrue(AIService.is_configured("openai"))

        # When configured with Gemini
        settings.ai_provider = "gemini"
        settings.openai_api_key = None
        settings.gemini_api_key = "AIzaSy_gemini_test"
        self.assertTrue(AIService.is_configured("gemini"))

        gemini_provider = AIProviderFactory.create("gemini")
        self.assertEqual(gemini_provider.name, "gemini")
        self.assertEqual(gemini_provider.default_model, "gemini-3.6-flash")

        # Groq
        settings.groq_api_key = "gsk_live_key_123"
        groq_provider = AIProviderFactory.create("groq")
        self.assertEqual(groq_provider.name, "groq")
        self.assertEqual(groq_provider.default_model, "openai/gpt-oss-120b")

        # The fallback lane uses only its explicitly supplied second key.
        settings.groq_fallback_api_key = "gsk_fallback_key_456"
        groq_fallback_provider = AIProviderFactory.create("groq_fallback")
        self.assertEqual(groq_fallback_provider.name, "groq_fallback")
        self.assertEqual(groq_fallback_provider.default_model, "openai/gpt-oss-120b")
        self.assertTrue(AIProviderFactory.is_configured("groq_fallback"))
        self.assertEqual(AIProviderFactory.detect_provider("groq_fallback")[1], "gsk_fallback_key_456")
        settings.groq_fallback_api_key = None
        self.assertFalse(AIProviderFactory.is_configured("groq_fallback"))

        # OpenRouter
        settings.openrouter_api_key = "sk-or-test"
        openrouter_provider = AIProviderFactory.create("openrouter")
        self.assertEqual(openrouter_provider.name, "openrouter")
        self.assertEqual(openrouter_provider.default_model, "meta-llama/llama-3.3-70b-instruct")

    async def test_waterfall_failover_succeeds_on_second_provider(self):
        settings.ai_enabled = True
        settings.groq_api_key = "gsk_test"
        settings.gemini_api_key = "AIzaSy_gemini_test"

        failing_groq = AsyncMock()
        failing_groq.supports = lambda cap: True
        failing_groq.name = "groq"
        failing_groq.generate.side_effect = Exception("Groq 429 Quota Exceeded")

        successful_gemini = AsyncMock()
        successful_gemini.supports = lambda cap: True
        successful_gemini.name = "gemini"
        successful_gemini.generate.return_value = AIGeneration(
            content="Gemini successful response",
            model="gemini-3.6-flash",
            provider="gemini",
            usage=AIUsage(20, 10, 30),
            duration_ms=250,
        )

        def mock_create(name):
            if name == "groq":
                return failing_groq
            return successful_gemini

        with patch.object(AIProviderFactory, "create", side_effect=mock_create), \
             patch.object(AIProviderFactory, "get_configured_providers", return_value=["groq", "gemini"]):

            service = AIService(provider=failing_groq)
            req = AIGenerationRequest(
                messages=[AIMessage(role="user", content="Test waterfall")],
                user_id="test-user",
            )
            res = await service.generate_with_waterfall(req)
            self.assertEqual(res.provider, "gemini")
            self.assertEqual(res.content, "Gemini successful response")

    async def test_waterfall_can_bound_provider_attempts_for_vision_ocr(self):
        from services.ai.service import _failed_provider_cooldown
        _failed_provider_cooldown.clear()
        failing_groq = AsyncMock()
        failing_groq.supports = lambda cap: True
        failing_groq.name = "groq"
        failing_groq.generate.side_effect = Exception("provider unavailable")

        unused_gemini = AsyncMock()
        unused_gemini.supports = lambda cap: True
        unused_gemini.name = "gemini"

        def mock_create(name):
            return failing_groq if name == "groq" else unused_gemini

        with patch.object(AIProviderFactory, "create", side_effect=mock_create), \
             patch.object(AIProviderFactory, "get_configured_providers", return_value=["groq", "gemini"]):
            service = AIService(provider=failing_groq)
            req = AIGenerationRequest(messages=[AIMessage(role="user", content="OCR page")], user_id="ocr_ingestion")
            with self.assertRaises(AIProviderUnavailableError):
                await service.generate_with_waterfall(req, max_provider_attempts=1)

        unused_gemini.generate.assert_not_called()

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
            mock_ai.generate_with_waterfall.return_value = AIGeneration(
                content="## Comprehensive Revision Guide\n1. Normalization (1NF, 2NF, 3NF, BCNF)...",
                model="gemini-3.6-flash",
                provider="gemini",
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

            self.assertEqual(response["model"], "gemini-3.6-flash")
            self.assertIn("Comprehensive Revision Guide", response["content"])
            self.assertEqual(response["usage"]["total_tokens"], 150)
            mock_ai.generate_with_waterfall.assert_called_once()

    def test_intent_classification(self):
        from services.retrieval import QuestionIntent, classify_question_intent, _extract_target_question_id, _extract_target_section_id, _section_matches

        self.assertEqual(classify_question_intent("solve question 2 on section 1"), QuestionIntent.DIRECT_ANSWER)
        self.assertEqual(classify_question_intent("what is the answer to question 5?"), QuestionIntent.DIRECT_ANSWER)
        self.assertEqual(classify_question_intent("explain question 4"), QuestionIntent.DIRECT_ANSWER)
        self.assertEqual(classify_question_intent("which option is correct for Q10"), QuestionIntent.DIRECT_ANSWER)

        self.assertEqual(classify_question_intent("why is question 2 B?"), QuestionIntent.EXPLAIN)
        self.assertEqual(classify_question_intent("why is it B?"), QuestionIntent.EXPLAIN)
        self.assertEqual(classify_question_intent("why option C?"), QuestionIntent.EXPLAIN)

        self.assertEqual(classify_question_intent("solve question 2 step by step"), QuestionIntent.STEP_BY_STEP)
        self.assertEqual(classify_question_intent("show all steps for problem 3"), QuestionIntent.STEP_BY_STEP)

        self.assertEqual(classify_question_intent("teach me how to answer questions like this"), QuestionIntent.TEACH_ME)
        self.assertEqual(classify_question_intent("exam technique for this section"), QuestionIntent.TEACH_ME)

        self.assertEqual(classify_question_intent("explain this resource"), QuestionIntent.RESOURCE_EXPLAIN)
        self.assertEqual(classify_question_intent("why did you choose this resource?"), QuestionIntent.RESOURCE_EXPLAIN)

        self.assertEqual(classify_question_intent("collect all questions"), QuestionIntent.COLLECTION)
        self.assertEqual(classify_question_intent("list all questions from the paper"), QuestionIntent.COLLECTION)

        self.assertEqual(_extract_target_question_id("solve question 2 on section 1"), "2")
        self.assertEqual(_extract_target_section_id("solve question 2 on section 1"), "1")
        self.assertEqual(_extract_target_section_id("solve question 2 section ii"), "ii")

        self.assertTrue(_section_matches("1", "SECTIONI: READINGCOMPREHENSION"))
        self.assertFalse(_section_matches("1", "SECTIONII: GRAMMAR(20marks)"))
        self.assertTrue(_section_matches("2", "SECTIONII: GRAMMAR(20marks)"))
        self.assertTrue(_section_matches("i", "SECTIONI: READINGCOMPREHENSION"))

    def test_direct_answer_noise_cleaning(self):
        from routers.study_ai import _clean_direct_answer_noise

        dirty_response = (
            "**Answer: B — insufficient without accompanying pedagogical knowledge.**\n\n"
            "**Why:** The author argues that pure subject mastery cannot produce effective teaching without pedagogical expertise.\n\n"
            "**Source:** Page 2 • Section I • Reading Comprehension\n\n"
            "## Distractor Analysis\n"
            "| Option | Evaluation |\n"
            "| --- | --- |\n"
            "| A | Incorrect because not universally agreed |\n"
            "| B | Correct option |\n\n"
            "When answering multiple-choice questions, always identify the main thesis."
        )

        cleaned = _clean_direct_answer_noise(dirty_response)
        self.assertIn("**Answer: B — insufficient without accompanying pedagogical knowledge.**", cleaned)
        self.assertIn("**Why:** The author argues", cleaned)
        self.assertIn("**Source:** Page 2 • Section I • Reading Comprehension", cleaned)
        self.assertNotIn("Distractor Analysis", cleaned)
        self.assertNotIn("When answering multiple-choice", cleaned)
        self.assertNotIn("| Option |", cleaned)

    def test_section_and_scope_extraction(self):
        from services.retrieval import _extract_target_section_id, _extract_target_question_id, is_question_collection_query, classify_question_intent, QuestionIntent

        # Section-wide queries
        self.assertEqual(_extract_target_section_id("i need answer for section 2 questions"), "2")
        self.assertIsNone(_extract_target_question_id("i need answer for section 2 questions"))
        self.assertEqual(classify_question_intent("i need answer for section 2 questions"), QuestionIntent.GENERAL)

        self.assertEqual(_extract_target_section_id("i need answer for sectionII questions"), "ii")
        self.assertIsNone(_extract_target_question_id("i need answer for sectionII questions"))

        self.assertEqual(_extract_target_section_id("solve the grammar section"), "grammar")
        self.assertIsNone(_extract_target_question_id("solve the grammar section"))

        # Collection queries with scope
        self.assertTrue(is_question_collection_query("collect all questions in vocabulary section"))
        self.assertEqual(_extract_target_section_id("collect all questions in vocabulary section"), "vocab")
        self.assertEqual(classify_question_intent("collect all questions in vocabulary section"), QuestionIntent.COLLECTION)

        self.assertTrue(is_question_collection_query("collect all questions in section 1"))
        self.assertEqual(_extract_target_section_id("collect all questions in section 1"), "1")

        # Solving vs Collecting distinction
        self.assertFalse(is_question_collection_query("solve all questions in vocabulary section"))

    def test_build_paper_intelligence_context(self):
        from models.papers import Papers, PaperPassage
        from services.ai.papers import build_paper_intelligence_context

        dummy_paper = Papers(
            id=1,
            title="English for General Purposes",
            course_code="CL80111",
            course_name="English For General Purposes",
            department="Applied Physics",
            college="CST",
            year=2026,
            paper_type="Exam",
        )

        dummy_passages = [
            PaperPassage(id=1, paper_id=1, page_number=1, passage_index=0, section_title="SECTION I: READING", question_number=None, text="Reading text about education..."),
            PaperPassage(id=2, paper_id=1, page_number=3, passage_index=1, section_title="SECTION I: READING", question_number="1", text="1. What is the purpose?\nA. ...\nB. ..."),
            PaperPassage(id=3, paper_id=1, page_number=5, passage_index=2, section_title="VOCABULARY", question_number=None, text="Fill in the blanks (1)-(4)..."),
            PaperPassage(id=4, paper_id=1, page_number=5, passage_index=3, section_title="SECTION II: GRAMMAR", question_number="1", text="1. Every Friday lecturer (gives)..."),
        ]

        ctx = build_paper_intelligence_context(paper=dummy_paper, passages=dummy_passages, max_tokens=4000)
        self.assertIn("=== 1. PAPER METADATA ===", ctx.text)
        self.assertIn("Course: CL80111 - English For General Purposes", ctx.text)
        self.assertIn("=== 2. DOCUMENT STRUCTURE & SECTIONS ===", ctx.text)
        self.assertIn("SECTION I: READING", ctx.text)
        self.assertIn("VOCABULARY", ctx.text)
        self.assertIn("SECTION II: GRAMMAR", ctx.text)
        self.assertIn("=== 3. STRUCTURED QUESTION & SECTION CONTENT ===", ctx.text)
        self.assertIn("=== 4. CANONICAL ASSESSMENT INVENTORY (complete, ordered) ===", ctx.text)
        self.assertIn("Inventory 2: SECTION I: READING • Question 1 • pages 3-3", ctx.text)
        self.assertIn("Inventory 4: SECTION II: GRAMMAR • Question 1 • pages 5-5", ctx.text)
