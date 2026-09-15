import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from services.contribution_communications import THEMES, compose_contribution_message
from services.paper_processing import PaperProcessingService
from services.passage_indexing import PassageIndexService
from services.document_ingestion import ExtractedPageData
from services.embeddings import EmbeddingService
from services.ai.base import AIEmbeddingResult, AIRateLimitError
from services.ai.providers.openai import OpenAIProvider
from core.config import settings


class _DB:
    def __init__(self):
        self.added = []
    def add(self, value):
        self.added.append(value)
    async def execute(self, *_args, **_kwargs):
        class _Result:
            def scalar_one_or_none(self): return None
        return _Result()


def test_receipt_enqueues_a_durable_job_without_running_ingestion():
    db = _DB()
    paper = SimpleNamespace(id=7, extraction_status=None, extraction_version=None)
    job = asyncio.run(PaperProcessingService(db).enqueue(paper))
    assert job.paper_id == 7
    assert job.status == "QUEUED"
    assert paper.extraction_status == "QUEUED"
    assert db.added == [job]


def test_contributor_messages_are_grounded_and_support_meaningful_themes():
    paper = SimpleNamespace(id=7, title="Algorithms Final", course_code="CSC312", course_name="Algorithms", department="Computer Science", paper_type="Exam", year=2024)
    user = SimpleNamespace(id="u1", name="Aline", email="aline@example.test")
    receipt = compose_contribution_message("PAPER_RECEIVED", paper, user, 1)
    complete = compose_contribution_message("PAPER_PROCESSING_COMPLETED", paper, user, 2)
    assert "Algorithms Final" in receipt["text"]
    assert "Aline" in receipt["text"]
    assert "safely received" in receipt["text"]
    assert "ready for Study AI" in complete["text"]
    assert receipt["subject"] != complete["subject"]
    assert receipt["text"] != complete["text"]
    assert len(THEMES) >= 4

    # HTML Brand design assertions
    assert "UR Academic Resource Hub" in receipt["html"]
    assert "Academic Platform" in receipt["html"]
    assert "Contribution Received" in receipt["html"]
    assert "View Your Paper" in receipt["html"]
    assert "https://paperhubur.vercel.app/paper/7" in receipt["html"]
    assert "Computer Science" in receipt["html"]
    assert "CSC312 — Algorithms" in receipt["html"]
    assert "Terms of Service" in receipt["html"]
    assert "Privacy Policy" in receipt["html"]
    assert "paperhubur@gmail.com" in receipt["html"]

    assert "Study AI Ready" in complete["html"]
    assert "Explore with Study AI" in complete["html"]
    assert "https://paperhubur.vercel.app/paper/7" in complete["html"]



def test_missing_optional_metadata_is_not_fabricated_into_communication():
    paper = SimpleNamespace(id=9, title="A submitted paper", course_code=None, course_name=None)
    user = SimpleNamespace(id="u2", name=None, email="u2@example.test")
    message = compose_contribution_message("PAPER_RECEIVED", paper, user, 1)
    assert "Hello there" in message["text"]
    assert "None" not in message["text"]


def test_community_upload_route_uses_the_durable_receipt_path():
    from pathlib import Path
    route_path = Path(__file__).resolve().parent.parent / "routers" / "community.py"
    route = route_path.read_text(encoding="utf-8")
    create_start = route.index("async def create_paper(")
    create_end = route.index("\n\n@router.post(\"/papers/{paper_id}/comments\")", create_start)
    body = route[create_start:create_end]
    assert "PaperProcessingService(db).enqueue(paper)" in body
    assert 'event_type="PAPER_RECEIVED"' in body
    assert "await db.flush()" in body


def test_stalled_original_download_returns_a_retryable_ingestion_failure(monkeypatch):
    async def stalled_download(*_args, **_kwargs):
        await asyncio.sleep(1)

    paper = SimpleNamespace(id=44, file_key="papers/stalled.pdf")
    monkeypatch.setenv("PAPER_PROCESSING_DOWNLOAD_TIMEOUT_SECONDS", "15")

    async def run():
        storage = SimpleNamespace(download_file=AsyncMock(side_effect=stalled_download))
        async def force_timeout(awaitable, **_kwargs):
            awaitable.close()
            raise asyncio.TimeoutError
        with patch("services.passage_indexing.StorageService", return_value=storage):
            # The explicit environment minimum is intentionally 15 seconds in
            # production; patch wait_for here so this test proves the timeout
            # branch without waiting for a real network deadline.
            with patch("services.passage_indexing.asyncio.wait_for", side_effect=force_timeout):
                return await PassageIndexService(SimpleNamespace()).index_paper(paper)

    result = asyncio.run(run())
    assert result["ingestion_succeeded"] is False
    assert result["error"] == "Original document download timed out."


def test_worker_downloads_with_provider_id_without_legacy_path_lookup():
    paper = SimpleNamespace(
        id=45,
        file_key="papers/fresh.pdf",
        file_drive_file_id="provider-stable-id",
    )

    async def run():
        storage = SimpleNamespace(
            download_file=AsyncMock(side_effect=AssertionError("legacy path lookup must not run")),
            download_file_by_id=AsyncMock(return_value=b""),
        )
        with patch("services.passage_indexing.StorageService", return_value=storage):
            result = await PassageIndexService(SimpleNamespace()).index_paper(paper)
        storage.download_file_by_id.assert_awaited_once_with("papers", "papers/fresh.pdf", "provider-stable-id")
        storage.download_file.assert_not_called()
        return result

    result = asyncio.run(run())
    assert result["error"] == "Original document download was empty."


def test_legacy_paper_uses_bounded_path_download_only_when_provider_id_is_absent():
    paper = SimpleNamespace(id=46, file_key="papers/legacy.pdf", file_drive_file_id=None)

    async def run():
        storage = SimpleNamespace(
            download_file=AsyncMock(return_value=b"not a pdf"),
            download_file_by_id=AsyncMock(),
        )
        with patch("services.passage_indexing.StorageService", return_value=storage):
            result = await PassageIndexService(SimpleNamespace()).index_paper(paper)
        storage.download_file.assert_awaited_once_with("papers", "papers/legacy.pdf")
        storage.download_file_by_id.assert_not_called()
        return result

    result = asyncio.run(run())
    assert result["error"] == "Downloaded original is not a PDF document."


def test_page_extraction_persistence_keeps_text_and_failure_diagnostics():
    class DB:
        def __init__(self): self.rows = []
        async def execute(self, statement, *_args, **_kwargs):
            class Result:
                def scalar_one(self): return 2
            return Result()
        def add_all(self, rows): self.rows.extend(rows)
        async def flush(self): pass

    db = DB()
    paper = SimpleNamespace(id=47, file_key="papers/evidence.pdf")
    ingestion = SimpleNamespace(pages=[
        ExtractedPageData(1, "Question 1: Explain indexing.", "native", 0.98),
        ExtractedPageData(2, "", "failed", 0.0),
    ])
    asyncio.run(PassageIndexService(db)._persist_page_extractions(paper, ingestion))
    assert [(row.status, row.text, row.text_length) for row in db.rows] == [
        ("SUCCESS", "Question 1: Explain indexing.", 29),
        ("FAILED", None, 0),
    ]
    assert db.rows[1].error_message == "No usable text was produced for this page."


def test_embeddings_use_explicit_embedding_provider_not_generation_provider(monkeypatch):
    original = (settings.ai_enabled, settings.ai_provider, settings.embedding_provider, settings.embedding_model, settings.embedding_dimension, settings.embedding_fallback_providers)
    settings.ai_enabled, settings.ai_provider = True, "groq"
    settings.embedding_provider, settings.embedding_model = "openai", "text-embedding-3-small"
    settings.embedding_dimension = 2
    settings.embedding_fallback_providers = ""
    provider = SimpleNamespace(embed=AsyncMock(return_value=AIEmbeddingResult(vectors=[[0.1, 0.2]], model="text-embedding-3-small", provider="openai")))

    async def run():
        with patch("services.embeddings.AIProviderFactory.is_embedding_configured", return_value=True):
            with patch("services.embeddings.AIProviderFactory.create_embedding", return_value=provider) as create:
                outcome = await EmbeddingService().generate_embeddings(["A durable passage."])
        create.assert_called_once_with("openai", "text-embedding-3-small")
        return outcome

    try:
        outcome = asyncio.run(run())
        assert outcome.provider == "openai"
        assert outcome.vectors == [[0.1, 0.2]]
        assert outcome.error_type is None
    finally:
        settings.ai_enabled, settings.ai_provider, settings.embedding_provider, settings.embedding_model, settings.embedding_dimension, settings.embedding_fallback_providers = original


def test_embedding_provider_failure_is_typed_not_a_nonetype_crash(monkeypatch):
    original = (settings.embedding_provider, settings.embedding_model, settings.embedding_fallback_providers)
    settings.embedding_provider, settings.embedding_model = "openai", "text-embedding-3-small"
    settings.embedding_fallback_providers = ""
    provider = SimpleNamespace(embed=AsyncMock(side_effect=RuntimeError("404 Not Found")))

    async def run():
        with patch("services.embeddings.AIProviderFactory.is_embedding_configured", return_value=True):
            with patch("services.embeddings.AIProviderFactory.create_embedding", return_value=provider):
                return await EmbeddingService().generate_embeddings(["Passage text"])

    try:
        outcome = asyncio.run(run())
        assert outcome.vectors is None
        assert outcome.error_type == "EMBEDDING_PROVIDER_ERROR"
        assert "404" in (outcome.error_message or "")
    finally:
        settings.embedding_provider, settings.embedding_model, settings.embedding_fallback_providers = original


def test_embedding_fallback_uses_next_configured_provider(monkeypatch):
    original = (settings.embedding_provider, settings.embedding_fallback_providers, settings.embedding_dimension)
    settings.embedding_provider, settings.embedding_fallback_providers, settings.embedding_dimension = "openai", "gemini,openrouter", 2
    openai = SimpleNamespace(embed=AsyncMock(side_effect=RuntimeError("429")))
    gemini = SimpleNamespace(embed=AsyncMock(return_value=AIEmbeddingResult(vectors=[[0.2, 0.3]], model="gemini-embedding-001", provider="gemini")))

    async def run():
        with patch("services.embeddings.AIProviderFactory.is_embedding_configured", side_effect=lambda p: p in {"openai", "gemini"}):
            with patch("services.embeddings.AIProviderFactory.create_embedding", side_effect=[openai, gemini]) as create:
                outcome = await EmbeddingService().generate_embeddings(["Persisted passage"])
        assert [call.args[0] for call in create.call_args_list] == ["openai", "gemini"]
        return outcome

    try:
        outcome = asyncio.run(run())
        assert outcome.provider == "gemini"
        assert outcome.vectors == [[0.2, 0.3]]
    finally:
        settings.embedding_provider, settings.embedding_fallback_providers, settings.embedding_dimension = original


def test_groq_xai_and_deepseek_are_removed_from_embedding_fallback_providers():
    original = (settings.embedding_provider, settings.embedding_fallback_providers)
    settings.embedding_provider, settings.embedding_fallback_providers = "openai", "gemini,groq,xai,deepseek,openrouter"
    try:
        assert EmbeddingService._providers() == ["openai", "gemini", "openrouter"]
    finally:
        settings.embedding_provider, settings.embedding_fallback_providers = original


def test_openrouter_is_first_embedding_provider_and_short_circuits_fallbacks():
    original = (settings.embedding_provider, settings.embedding_fallback_providers, settings.embedding_dimension)
    settings.embedding_provider, settings.embedding_fallback_providers, settings.embedding_dimension = "openrouter", "openai,gemini", 2
    openrouter = SimpleNamespace(embed=AsyncMock(return_value=AIEmbeddingResult(vectors=[[0.1, 0.2]], model="configured-router-model", provider="openrouter")))
    try:
        async def run():
            with patch("services.embeddings.AIProviderFactory.is_embedding_configured", return_value=True):
                with patch("services.embeddings.AIProviderFactory.create_embedding", return_value=openrouter) as create:
                    outcome = await EmbeddingService().generate_embeddings(["One passage"])
            assert [call.args[0] for call in create.call_args_list] == ["openrouter"]
            return outcome
        outcome = asyncio.run(run())
        assert outcome.provider == "openrouter"
        assert outcome.vectors == [[0.1, 0.2]]
    finally:
        settings.embedding_provider, settings.embedding_fallback_providers, settings.embedding_dimension = original


def test_transient_openai_rate_limit_is_bounded_then_falls_back():
    original = (settings.embedding_provider, settings.embedding_fallback_providers, settings.embedding_dimension)
    settings.embedding_provider, settings.embedding_fallback_providers, settings.embedding_dimension = "openai", "gemini", 2
    openai = SimpleNamespace(embed=AsyncMock(side_effect=AIRateLimitError("temporary")))
    gemini = SimpleNamespace(embed=AsyncMock(return_value=AIEmbeddingResult(vectors=[[0.4, 0.5]], model="gemini-embedding-001", provider="gemini")))
    try:
        async def run():
            with patch("services.embeddings.AIProviderFactory.is_embedding_configured", return_value=True):
                with patch("services.embeddings.AIProviderFactory.create_embedding", side_effect=[openai, gemini]):
                    with patch("services.embeddings.asyncio.sleep", new=AsyncMock()) as sleep:
                        outcome = await EmbeddingService().generate_embeddings(["One passage"])
            assert openai.embed.await_count == EmbeddingService.MAX_RATE_LIMIT_ATTEMPTS
            assert sleep.await_count == EmbeddingService.MAX_RATE_LIMIT_ATTEMPTS - 1
            return outcome
        outcome = asyncio.run(run())
        assert outcome.provider == "gemini"
    finally:
        settings.embedding_provider, settings.embedding_fallback_providers, settings.embedding_dimension = original


def test_partial_provider_batches_are_discarded_before_full_fallback():
    original = (settings.embedding_provider, settings.embedding_fallback_providers, settings.embedding_dimension, EmbeddingService.BATCH_SIZE)
    settings.embedding_provider, settings.embedding_fallback_providers, settings.embedding_dimension = "openrouter", "openai", 2
    EmbeddingService.BATCH_SIZE = 2
    openrouter = SimpleNamespace(embed=AsyncMock(side_effect=[AIEmbeddingResult(vectors=[[1.0, 1.0], [1.0, 1.0]], model="router", provider="openrouter"), RuntimeError("second batch failed")]))
    openai = SimpleNamespace(embed=AsyncMock(side_effect=[AIEmbeddingResult(vectors=[[2.0, 2.0], [2.0, 2.0]], model="openai", provider="openai"), AIEmbeddingResult(vectors=[[2.0, 2.0]], model="openai", provider="openai")]))
    try:
        async def run():
            with patch("services.embeddings.AIProviderFactory.is_embedding_configured", return_value=True):
                with patch("services.embeddings.AIProviderFactory.create_embedding", side_effect=[openrouter, openai]):
                    return await EmbeddingService().generate_embeddings(["one", "two", "three"])
        outcome = asyncio.run(run())
        assert [[*call.args[0].input] for call in openai.embed.await_args_list] == [["one", "two"], ["three"]]
        assert outcome.provider == "openai"
        assert outcome.vectors == [[2.0, 2.0], [2.0, 2.0], [2.0, 2.0]]
    finally:
        settings.embedding_provider, settings.embedding_fallback_providers, settings.embedding_dimension, EmbeddingService.BATCH_SIZE = original


def test_gemini_native_embedding_response_uses_requested_dimension():
    original_dimension = settings.embedding_dimension
    settings.embedding_dimension = 2

    class Response:
        status_code = 200
        headers = {}
        text = ""
        def raise_for_status(self): pass
        def json(self): return {"embeddings": [{"values": [0.1, 0.2]}, {"values": [0.3, 0.4]}]}

    class Client:
        async def __aenter__(self): return self
        async def __aexit__(self, *_args): pass
        async def post(self, url, headers, json):
            assert url.endswith("models/gemini-embedding-001:batchEmbedContents")
            assert len(json["requests"]) == 2
            assert all(item["outputDimensionality"] == 2 for item in json["requests"])
            assert headers["x-goog-api-key"] == "AIza-safe-test"
            return Response()

    try:
        provider = OpenAIProvider(api_key="AIza-safe-test", default_model="gemini", embedding_model="gemini-embedding-001", timeout_seconds=1, name="gemini")
        with patch("services.ai.providers.openai.httpx.AsyncClient", return_value=Client()):
            result = asyncio.run(provider.embed(SimpleNamespace(input=["first", "second"], model="gemini-embedding-001")))
        assert result.vectors == [[0.1, 0.2], [0.3, 0.4]]
    finally:
        settings.embedding_dimension = original_dimension
