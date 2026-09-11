"""Unit and integration tests for storage key candidates, storage download resolution, and schema sync."""

from datetime import datetime, timezone

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from core.database import Base, DatabaseManager, get_db
from dependencies.auth import get_optional_current_user
from models.books import Book
from models.comments import Comments
from models.papers import Papers
from models.solutions import Solutions
from models.user_profiles import User_profiles
from routers.comments import router as comments_router
from routers.storage import router as storage_router
import routers.storage as storage_module
from services.storage import GoogleDriveStorageService, storage_key_candidates


def test_storage_key_candidates_preserves_case_and_underscores():
    """Ensure filenames with uppercase and underscores preserve exact raw shapes."""
    paper_key = "IEEE754_CAT_2026_1786829715097.pdf"
    candidates = storage_key_candidates("papers", paper_key)

    assert paper_key in candidates
    assert f"papers/{paper_key}" in candidates

    solution_key = "solutions/IEEE754_CAT_2026_sol_1786829728393.pdf"
    sol_candidates = storage_key_candidates("papers", solution_key)

    assert solution_key in sol_candidates
    assert f"papers/{solution_key}" in sol_candidates
    assert "IEEE754_CAT_2026_sol_1786829728393.pdf" in sol_candidates


def test_storage_key_candidates_prefixed_variants():
    """Ensure prefixed keys can be stripped or resolved in multiple forms."""
    prefixed_key = "papers/solutions/IEEE754_CAT_2026_sol_1786829728393.pdf"
    candidates = storage_key_candidates("papers", prefixed_key)

    assert prefixed_key in candidates
    assert "solutions/IEEE754_CAT_2026_sol_1786829728393.pdf" in candidates


@pytest.mark.anyio
async def test_google_drive_provider_id_delete_verifies_bucket_and_deletes_id():
    service = object.__new__(GoogleDriveStorageService)
    deleted = []
    service._find_file_by_id = lambda provider_id: _async_value({"id": provider_id, "trashed": False, "parents": ["bucket"]})
    service._file_is_in_bucket = lambda bucket_name, file: _async_value(bucket_name == "papers")
    service._execute = lambda request: _async_value(deleted.append(request))
    service._service = type("Drive", (), {"files": lambda self: type("Files", (), {"delete": lambda self, **kwargs: FakeDriveRequest(**kwargs)})()})()

    result = await service.delete_object_by_id("papers", "papers/original.pdf", "drive-123")

    assert result.success is True
    assert len(deleted) == 1
    assert deleted[0].kwargs == {"fileId": "drive-123", "supportsAllDrives": True}


async def _async_value(value):
    return value


class FakeStorageService:
    async def download_file(self, bucket_name: str, object_key: str) -> bytes:
        return b"%PDF-1.4 test document content"

    async def get_file_metadata(self, bucket_name: str, object_key: str) -> dict:
        return {"mime_type": "application/pdf", "file_name": object_key.split("/")[-1]}

    async def create_download_url(self, request) -> dict:
        return {"download_url": f"https://storage.test/{request.bucket_name}/{request.object_key}", "expires_at": "2099-01-01T00:00:00Z"}


class FakeDriveRequest:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class FakeDriveFiles:
    def list(self, **kwargs):
        return FakeDriveRequest(**kwargs)

    def get(self, **kwargs):
        return FakeDriveRequest(**kwargs)


class FakeDriveService:
    def files(self):
        return FakeDriveFiles()


def make_drive_resolver(file_results):
    service = object.__new__(GoogleDriveStorageService)
    service.root_folder_id = "root"
    service._bucket_folder_ids = {}
    service._service = FakeDriveService()
    async def find_folder(name, parent):
        return "bucket-books" if name == "books" and parent == "root" else ("nested-books" if name == "books" else "")

    service._find_folder = find_folder

    async def execute(request):
        query = request.kwargs.get("q", "")
        return file_results(query)

    service._execute = execute
    return service


@pytest.mark.anyio
async def test_google_drive_resolver_uses_bucket_scope_and_legacy_name_deterministically():
    actual_name = "1787330846448-0qza3avi7b7d-electromagnetism-group-assignment-applied-physics-y1.pdf"

    def results(query):
        return {"files": [{"id": "drive-book-1", "name": actual_name, "parents": ["bucket-books"]}]} if actual_name in query else {"files": []}

    resolver = make_drive_resolver(results)
    found = await resolver._find_file("books", "books/1787330846448-0qza3avi7b7d-Electromagnetism_Group_Assignment_Applied_Physics_Y1.pdf")

    assert found["id"] == "drive-book-1"
    assert resolver._provider_path_candidates("books", "books/example.pdf") == ["example.pdf", "books/example.pdf"]


@pytest.mark.anyio
async def test_google_drive_resolver_rejects_ambiguous_files():
    resolver = make_drive_resolver(lambda query: {"files": [{"id": "one"}, {"id": "two"}]})

    with pytest.raises(ValueError, match="ambiguous"):
        await resolver._find_file("books", "books/duplicate.pdf")


@pytest.mark.anyio
async def test_google_drive_provider_id_lookup_does_not_search_by_name():
    calls = []
    resolver = make_drive_resolver(lambda query: calls.append(query) or {"files": []})

    async def execute(request):
        calls.append(request.kwargs)
        return {"id": "drive-id-1", "name": "stable.pdf", "mimeType": "application/pdf", "size": "10", "parents": ["bucket-books"]}

    resolver._execute = execute
    found = await resolver._find_file_by_id("drive-id-1")

    assert found["id"] == "drive-id-1"
    assert calls == [{"fileId": "drive-id-1", "fields": "id,name,mimeType,size,modifiedTime,parents,trashed", "supportsAllDrives": True}]


@pytest.mark.anyio
async def test_storage_download_paper_and_solution_exact_keys(monkeypatch):
    """Verify papers and solutions with uppercase/underscore keys can be downloaded."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    tables = [Papers.__table__, Solutions.__table__, Book.__table__, User_profiles.__table__]
    async with engine.begin() as conn:
        await conn.run_sync(lambda sync_conn: Base.metadata.create_all(sync_conn, tables=tables))

    now = datetime.now(timezone.utc)
    paper_file_key = "IEEE754_CAT_2026_1786829715097.pdf"
    paper_solution_key = "solutions/IEEE754_CAT_2026_sol_1786829728393.pdf"
    community_sol_key = "community_solutions/CS_SOL_2026.pdf"

    async with session_factory() as session:
        session.add(
            Papers(
                id=5,
                user_id="user_123",
                title="IEEE 754 CAT 2026",
                course_code="CS101",
                course_name="Computer Systems",
                college="CST",
                department="CS",
                year=2026,
                paper_type="CAT",
                file_key=paper_file_key,
                solution_key=paper_solution_key,
                verification_status="verified",
                is_hidden=False,
                created_at=now,
            )
        )
        session.add(
            Solutions(
                id=1,
                user_id="user_456",
                paper_id=5,
                content="Alternative community solution",
                file_key=community_sol_key,
                created_at=now,
            )
        )
        await session.commit()

    test_app = FastAPI()
    test_app.include_router(storage_router)

    async def override_get_db():
        async with session_factory() as s:
            yield s

    test_app.dependency_overrides[get_db] = override_get_db
    test_app.dependency_overrides[get_optional_current_user] = lambda: None
    monkeypatch.setattr(storage_module, "StorageService", FakeStorageService)

    transport = httpx.ASGITransport(app=test_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Download paper file
        resp_paper = await client.get("/api/v1/storage/download", params={"bucket_name": "papers", "object_key": paper_file_key})
        assert resp_paper.status_code == 200
        assert resp_paper.content == b"%PDF-1.4 test document content"

        # Download paper solution
        resp_sol = await client.get("/api/v1/storage/download", params={"bucket_name": "papers", "object_key": paper_solution_key})
        assert resp_sol.status_code == 200
        assert resp_sol.content == b"%PDF-1.4 test document content"

        # Download community solution
        resp_comm_sol = await client.get("/api/v1/storage/download", params={"bucket_name": "papers", "object_key": community_sol_key})
        assert resp_comm_sol.status_code == 200
        assert resp_comm_sol.content == b"%PDF-1.4 test document content"

        # Download paper file with prefix
        resp_paper_prefixed = await client.get("/api/v1/storage/download", params={"bucket_name": "papers", "object_key": f"papers/{paper_file_key}"})
        assert resp_paper_prefixed.status_code == 200
        assert resp_paper_prefixed.content == b"%PDF-1.4 test document content"

        # Download paper solution with prefix
        resp_sol_prefixed = await client.get("/api/v1/storage/download", params={"bucket_name": "papers", "object_key": f"papers/{paper_solution_key}"})
        assert resp_sol_prefixed.status_code == 200
        assert resp_sol_prefixed.content == b"%PDF-1.4 test document content"

        # Download non-existent file returns 404 Resource not found
        resp_404 = await client.get("/api/v1/storage/download", params={"bucket_name": "papers", "object_key": "non_existent.pdf"})
        assert resp_404.status_code == 404
        assert "Resource not found" in resp_404.json()["detail"]


@pytest.mark.anyio
async def test_storage_download_missing_from_storage_when_db_record_exists(monkeypatch):
    """Verify that when a DB record exists but storage throws ValueError/missing, 404 File missing from storage is returned."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    tables = [Papers.__table__]
    async with engine.begin() as conn:
        await conn.run_sync(lambda sync_conn: Base.metadata.create_all(sync_conn, tables=tables))

    now = datetime.now(timezone.utc)
    paper_key = "MissingFile_CAT_2026.pdf"

    async with session_factory() as session:
        session.add(
            Papers(
                id=10,
                user_id="user_123",
                title="Missing File Paper",
                course_code="CS102",
                course_name="Data Structures",
                college="CST",
                department="CS",
                year=2026,
                paper_type="CAT",
                file_key=paper_key,
                verification_status="verified",
                is_hidden=False,
                created_at=now,
            )
        )
        await session.commit()

    class MissingStorageService:
        async def download_file(self, bucket_name: str, object_key: str) -> bytes:
            raise ValueError("File not found in storage bucket")

        async def get_file_metadata(self, bucket_name: str, object_key: str) -> dict:
            raise ValueError("File not found")

    test_app = FastAPI()
    test_app.include_router(storage_router)

    async def override_get_db():
        async with session_factory() as s:
            yield s

    test_app.dependency_overrides[get_db] = override_get_db
    test_app.dependency_overrides[get_optional_current_user] = lambda: None
    monkeypatch.setattr(storage_module, "StorageService", MissingStorageService)

    transport = httpx.ASGITransport(app=test_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/storage/download", params={"bucket_name": "papers", "object_key": paper_key})
        assert resp.status_code == 404
        assert resp.json()["detail"] == "File missing from storage"


@pytest.mark.anyio
async def test_storage_download_book_resolution(monkeypatch):
    """Verify book file and cover downloads resolve correctly."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    tables = [Book.__table__]
    async with engine.begin() as conn:
        await conn.run_sync(lambda sync_conn: Base.metadata.create_all(sync_conn, tables=tables))

    now = datetime.now(timezone.utc)
    book_file_key = "books/1787330846448-0qza3avi7b7d-Electromagnetism_Group_Assignment_Applied_Physics_Y1.pdf"
    book_cover_key = "book-covers/1787330846448-0qza3avi7b7d-1000167092.jpg"

    async with session_factory() as session:
        session.add(
            Book(
                id=1,
                title="Testing Book",
                file_key=book_file_key,
                cover_key=book_cover_key,
                visibility="public",
                status="active",
                uploaded_by="user_test",
                created_at=now,
                updated_at=now,
            )
        )
        await session.commit()

    test_app = FastAPI()
    test_app.include_router(storage_router)

    async def override_get_db():
        async with session_factory() as s:
            yield s

    test_app.dependency_overrides[get_db] = override_get_db
    test_app.dependency_overrides[get_optional_current_user] = lambda: None
    monkeypatch.setattr(storage_module, "StorageService", FakeStorageService)

    transport = httpx.ASGITransport(app=test_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Download book with exact key
        resp_book = await client.get("/api/v1/storage/download", params={"bucket_name": "books", "object_key": book_file_key})
        assert resp_book.status_code == 200
        assert resp_book.content == b"%PDF-1.4 test document content"

        # Download book cover
        resp_cover = await client.get("/api/v1/storage/download", params={"bucket_name": "book-covers", "object_key": book_cover_key})
        assert resp_cover.status_code == 200


@pytest.mark.anyio
async def test_schema_sync_adds_missing_columns_to_existing_table():
    """Verify that ensure_model_columns_for_existing_tables adds missing columns like comments.book_id."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    # Manually create comments table WITHOUT book_id
    async with engine.begin() as conn:
        await conn.execute(text("""
            CREATE TABLE comments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id VARCHAR NOT NULL,
                paper_id INTEGER,
                content VARCHAR NOT NULL,
                parent_id INTEGER,
                upvotes INTEGER,
                created_at TIMESTAMP
            )
        """))

    manager = DatabaseManager()
    manager.engine = engine
    manager.async_session_maker = session_factory

    # Run schema column synchronization
    await manager.ensure_model_columns_for_existing_tables("comments")

    # Verify book_id was added to table
    async with session_factory() as session:
        # Insert a comment with book_id
        await session.execute(text("INSERT INTO comments (user_id, book_id, content) VALUES ('u1', 10, 'Great book!')"))
        await session.commit()

        result = await session.execute(text("SELECT id, user_id, book_id, content FROM comments WHERE book_id = 10"))
        row = result.first()
        assert row is not None
        assert row[2] == 10
        assert row[3] == "Great book!"


@pytest.mark.anyio
async def test_comments_api_with_synced_book_id():
    """Verify comments query route works properly after schema synchronization."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    tables = [Comments.__table__]
    async with engine.begin() as conn:
        await conn.run_sync(lambda sync_conn: Base.metadata.create_all(sync_conn, tables=tables))

    now = datetime.now(timezone.utc)
    async with session_factory() as session:
        session.add(
            Comments(
                id=1,
                user_id="user_123",
                paper_id=5,
                book_id=None,
                content="Great paper!",
                created_at=now,
            )
        )
        await session.commit()

    test_app = FastAPI()
    test_app.include_router(comments_router)

    async def override_get_db():
        async with session_factory() as s:
            yield s

    test_app.dependency_overrides[get_db] = override_get_db

    transport = httpx.ASGITransport(app=test_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get('/api/v1/entities/comments/all', params={'query': '{"paper_id": 5}'})
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["content"] == "Great paper!"


@pytest.mark.anyio
async def test_site_settings_heartbeat_notify_admin_schema_sync():
    """Verify that ensure_model_columns_for_existing_tables adds missing site_settings.heartbeat_notify_admin column."""
    from models.site_settings import SiteSettings

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    # Manually create site_settings table WITHOUT heartbeat_notify_admin
    async with engine.begin() as conn:
        await conn.execute(text("""
            CREATE TABLE site_settings (
                id INTEGER PRIMARY KEY,
                maintenance_mode BOOLEAN NOT NULL DEFAULT 0,
                maintenance_message TEXT NOT NULL,
                upload_access_mode VARCHAR(32) NOT NULL DEFAULT 'selected_roles',
                upload_roles TEXT NOT NULL DEFAULT '["admin", "cp"]',
                allowed_resource_types TEXT NOT NULL DEFAULT '["book", "paper"]',
                heartbeat_enabled BOOLEAN NOT NULL DEFAULT 1,
                heartbeat_min_weekly_checks INTEGER NOT NULL DEFAULT 2,
                heartbeat_max_weekly_checks INTEGER NOT NULL DEFAULT 3,
                heartbeat_retry_delay_hours INTEGER NOT NULL DEFAULT 6,
                heartbeat_max_retry_attempts INTEGER NOT NULL DEFAULT 2,
                heartbeat_retry_enabled BOOLEAN NOT NULL DEFAULT 1,
                heartbeat_retry_jitter_minutes INTEGER NOT NULL DEFAULT 30,
                heartbeat_run_on_startup BOOLEAN NOT NULL DEFAULT 1,
                heartbeat_week_start TIMESTAMP,
                heartbeat_schedule TEXT NOT NULL DEFAULT '[]',
                heartbeat_completed_checks INTEGER NOT NULL DEFAULT 0,
                heartbeat_retry_attempts INTEGER NOT NULL DEFAULT 0,
                heartbeat_next_attempt_at TIMESTAMP,
                heartbeat_scheduler_status VARCHAR(32) NOT NULL DEFAULT 'stopped'
            )
        """))
        await conn.execute(text("INSERT INTO site_settings (id, maintenance_message) VALUES (1, 'Maintenance')"))

    manager = DatabaseManager()
    manager.engine = engine
    manager.async_session_maker = session_factory

    # Run schema column synchronization
    await manager.ensure_model_columns_for_existing_tables("site_settings")

    # Verify heartbeat_notify_admin was added and SiteSettings ORM can query without UndefinedColumnError
    async with session_factory() as session:
        settings = await session.get(SiteSettings, 1)
        assert settings is not None
        assert settings.heartbeat_notify_admin is True
