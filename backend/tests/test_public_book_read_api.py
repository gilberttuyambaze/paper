"""HTTP regressions for public Book reads using the normal async SQLAlchemy stack."""

from contextlib import asynccontextmanager
from datetime import datetime, timezone

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from core.database import Base, get_db
from dependencies.auth import get_optional_current_user
from models.books import Author, Book, BookAuthor, BookCourse, BookModule, Module
from models.courses import Course
from models.papers import Papers
from models.user_profiles import User_profiles
from routers.books import router as books_router
from routers.resources import router as resources_router
from routers.storage import router as storage_router
from schemas.auth import UserResponse
import routers.storage as storage_module


class FakeStorage:
    """Avoid external storage while preserving storage-router authorization."""

    async def download_file(self, _bucket_name: str, _object_key: str) -> bytes:
        return b"public book content"

    async def get_file_metadata(self, _bucket_name: str, _object_key: str) -> dict:
        return {"mime_type": "application/pdf", "file_name": "book.pdf"}

    async def create_download_url(self, request) -> dict:
        return {"download_url": f"https://storage.test/{request.bucket_name}/{request.object_key}", "expires_at": "2099-01-01T00:00:00Z"}


@asynccontextmanager
async def public_book_app(tmp_path, monkeypatch):
    """Keep aiosqlite creation, requests, and disposal on one event loop.

    The old fixture used separate ``asyncio.run`` calls for setup and requests,
    closing the loop that owned the aiosqlite worker and hanging at setup.
    """
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    # The application metadata includes unrelated legacy tables whose SQLite
    # DDL is not part of these routes and can block schema creation.  Create
    # precisely the tables exercised by this HTTP integration test.
    tables = [
        Book.__table__, Author.__table__, BookAuthor.__table__, BookCourse.__table__,
        Module.__table__, BookModule.__table__, Course.__table__,
        User_profiles.__table__, Papers.__table__,
    ]
    async with engine.begin() as connection:
        await connection.run_sync(lambda sync_connection: Base.metadata.create_all(sync_connection, tables=tables))

    now = datetime.now(timezone.utc)
    async with session_factory() as session:
        session.add_all([
            Course(id=1, code="CSC101", name="Algorithms", normalized_name="algorithms", created_by="cp-a"),
            Module(id=1, name="Algorithms module", normalized_name="algorithms module", code="CSC101-M1", course_id=1, created_by="cp-a"),
            Author(id=1, name="A. Author"),
            Book(id=1, title="Introduction to Algorithms", language="en", status="active", visibility="public", uploaded_by="cp-a", file_key="books/book-a.pdf", file_name="book-a.pdf", file_mime_type="application/pdf", cover_key="books/book-a-cover.png", created_at=now, updated_at=now),
            Book(id=2, title="Private Book", language="en", status="active", visibility="private", uploaded_by="cp-a", file_key="books/private.pdf", created_at=now, updated_at=now),
            Book(id=3, title="Inactive Book", language="en", status="inactive", visibility="public", uploaded_by="cp-a", file_key="books/inactive.pdf", created_at=now, updated_at=now),
            Book(id=4, title="Deleted Book", language="en", status="active", visibility="public", uploaded_by="cp-a", file_key="books/deleted.pdf", deleted_at=now, created_at=now, updated_at=now),
            BookAuthor(book_id=1, author_id=1), BookCourse(book_id=1, course_id=1), BookModule(book_id=1, module_id=1),
            User_profiles(user_id="cp-a", display_name="CP A", role="cp"),
        ])
        await session.commit()

    async def override_db():
        async with session_factory() as session:
            yield session

    app = FastAPI()
    app.include_router(books_router)
    app.include_router(resources_router)
    app.include_router(storage_router)
    app.dependency_overrides[get_db] = override_db
    monkeypatch.setattr(storage_module, "StorageService", lambda: FakeStorage())
    try:
        yield app
    finally:
        await engine.dispose()


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_anonymous_book_list_detail_resource_file_and_presigned_read(tmp_path, monkeypatch):
    async with public_book_app(tmp_path, monkeypatch) as app:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            resources = await client.get("/api/v1/resources")
            assert resources.status_code == 200
            assert [(item["type"], item["id"]) for item in resources.json()["items"]] == [("book", "1")]
            assert (await client.get("/api/v1/books")).json()["items"][0]["title"] == "Introduction to Algorithms"
            detail = await client.get("/api/v1/books/1")
            assert detail.status_code == 200
            assert detail.json()["authors"] == ["A. Author"]
            file_response = await client.get("/api/v1/storage/download", params={"bucket_name": "books", "object_key": "books/book-a.pdf"})
            assert file_response.status_code == 200
            assert file_response.content == b"public book content"
            signed = await client.post("/api/v1/storage/download-url", json={"bucket_name": "books", "object_key": "books/book-a.pdf"})
            assert signed.status_code == 200
            assert signed.json()["download_url"].endswith("books/book-a.pdf")
            assert (await client.get("/api/v1/storage/download", params={"bucket_name": "books", "object_key": "books/unknown.pdf"})).status_code == 404


@pytest.mark.anyio
async def test_nonpublic_books_are_hidden_from_anonymous_detail_and_storage(tmp_path, monkeypatch):
    async with public_book_app(tmp_path, monkeypatch) as app:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            assert {item["title"] for item in (await client.get("/api/v1/books")).json()["items"]} == {"Introduction to Algorithms"}
            for book_id in (2, 3, 4):
                assert (await client.get(f"/api/v1/books/{book_id}")).status_code == 404
            for key in ("books/private.pdf", "books/inactive.pdf", "books/deleted.pdf"):
                assert (await client.get("/api/v1/storage/download", params={"bucket_name": "books", "object_key": key})).status_code == 404
                assert (await client.post("/api/v1/storage/download-url", json={"bucket_name": "books", "object_key": key})).status_code == 404


@pytest.mark.anyio
async def test_public_book_uploaded_by_cp_a_is_visible_to_every_reader_role(tmp_path, monkeypatch):
    async with public_book_app(tmp_path, monkeypatch) as app:
        actors = [None, UserResponse(id="student-b", email="student@example.test", role="student"), UserResponse(id="cp-b", email="cp@example.test", role="cp"), UserResponse(id="admin", email="admin@example.test", role="admin")]
        for actor in actors:
            async def current_actor(value=actor):
                return value

            app.dependency_overrides[get_optional_current_user] = current_actor
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get("/api/v1/books")
                assert response.status_code == 200
                assert any(item["id"] == 1 for item in response.json()["items"])
