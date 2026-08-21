"""Book management with server-enforced admin/CP ownership rules."""

from datetime import timedelta, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from dependencies.auth import get_current_user
from models.books import Author, Book, BookActivity, BookAuthor, BookCourse, BookModule, Module
from models.user_profiles import User_profiles
from models.courses import Course
from schemas.auth import UserResponse
from services.authorization import CP_WINDOW, _utc, can_create_book, can_manage_book, database_now, require_book_management

router = APIRouter(prefix="/api/v1/books", tags=["books"])
MANAGEMENT_ROLES = {"admin", "cp"}
BOOK_STATUSES = {"draft", "active", "inactive", "archived"}
VISIBILITIES = {"public", "private"}


class FileReference(BaseModel):
    key: str = Field(min_length=1, max_length=1024)
    original_filename: Optional[str] = Field(default=None, max_length=500)
    mime_type: Optional[str] = Field(default=None, max_length=150)
    size: Optional[int] = Field(default=None, ge=0)


class BookCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=500)
    description: Optional[str] = None
    isbn: Optional[str] = Field(default=None, max_length=32)
    edition: Optional[str] = Field(default=None, max_length=100)
    publication_year: Optional[int] = Field(default=None, ge=0, le=9999)
    language: Literal["en", "fr", "rw", "sw", "ar", "zh", "es", "pt", "de", "it", "ja", "ko", "hi", "ru", "other"]
    publisher: Optional[str] = Field(default=None, max_length=255)
    category: Optional[str] = Field(default=None, max_length=120)
    subject: Optional[str] = Field(default=None, max_length=120)
    status: Literal["draft", "active", "inactive", "archived"] = "draft"
    visibility: Literal["public", "private"] = "public"
    authors: list[str] = Field(min_length=1)
    course_ids: list[int] = Field(min_length=1)
    module_ids: list[int] = Field(default_factory=list)
    cover: FileReference
    file: FileReference


class BookUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: Optional[str] = Field(default=None, min_length=1, max_length=500)
    description: Optional[str] = None
    isbn: Optional[str] = Field(default=None, max_length=32)
    edition: Optional[str] = Field(default=None, max_length=100)
    publication_year: Optional[int] = Field(default=None, ge=0, le=9999)
    language: Optional[str] = Field(default=None, max_length=80)
    publisher: Optional[str] = Field(default=None, max_length=255)
    category: Optional[str] = Field(default=None, max_length=120)
    subject: Optional[str] = Field(default=None, max_length=120)
    visibility: Optional[Literal["public", "private"]] = None


class StatusUpdate(BaseModel):
    status: Literal["draft", "active", "inactive", "archived"]


class AuthorsUpdate(BaseModel):
    authors: list[str] = Field(default_factory=list)


class CoursesUpdate(BaseModel):
    course_ids: list[int] = Field(default_factory=list)


class ModulesUpdate(BaseModel):
    module_ids: list[int] = Field(default_factory=list)


class ModuleCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=2, max_length=255)
    code: Optional[str] = Field(default=None, max_length=100)
    description: Optional[str] = None
    course_id: Optional[int] = None


async def _require_manager(book: Book, actor: UserResponse, db: AsyncSession) -> None:
    await require_book_management(db, actor, book)


async def _get_book(book_id: int, db: AsyncSession, include_deleted: bool = False) -> Book:
    query = select(Book).where(Book.id == book_id)
    if not include_deleted:
        query = query.where(Book.deleted_at.is_(None))
    book = (await db.execute(query)).scalar_one_or_none()
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    return book


async def _activity(db: AsyncSession, book: Book, actor: UserResponse | None, action: str, detail: str | None = None) -> None:
    db.add(BookActivity(book_id=book.id, actor_id=str(actor.id) if actor else None, actor_role=actor.role if actor else None, action=action, detail=detail))


async def _replace_authors(db: AsyncSession, book_id: int, authors: list[str]) -> None:
    rows = (await db.execute(select(BookAuthor).where(BookAuthor.book_id == book_id))).scalars().all()
    for row in rows: await db.delete(row)
    for name in dict.fromkeys(name.strip() for name in authors if name.strip()):
        author = (await db.execute(select(Author).where(Author.name == name))).scalar_one_or_none()
        if not author:
            author = Author(name=name); db.add(author); await db.flush()
        db.add(BookAuthor(book_id=book_id, author_id=author.id))


async def _replace_courses(db: AsyncSession, book_id: int, course_ids: list[int]) -> None:
    rows = (await db.execute(select(BookCourse).where(BookCourse.book_id == book_id))).scalars().all()
    for row in rows: await db.delete(row)
    selected = list(dict.fromkeys(course_ids))
    found = set((await db.execute(select(Course.id).where(Course.id.in_(selected), Course.deleted_at.is_(None)))).scalars().all()) if selected else set()
    if set(selected) - found: raise HTTPException(400, "One or more selected courses do not exist")
    for course_id in selected: db.add(BookCourse(book_id=book_id, course_id=course_id))


async def _replace_modules(db: AsyncSession, book_id: int, module_ids: list[int]) -> None:
    rows = (await db.execute(select(BookModule).where(BookModule.book_id == book_id))).scalars().all()
    for row in rows: await db.delete(row)
    if module_ids:
        found = set((await db.execute(select(Module.id).where(Module.id.in_(set(module_ids))))).scalars().all())
        missing = set(module_ids) - found
        if missing: raise HTTPException(400, f"Unknown module IDs: {', '.join(map(str, sorted(missing)))}")
        for module_id in dict.fromkeys(module_ids): db.add(BookModule(book_id=book_id, module_id=module_id))


async def _serialize(book: Book, db: AsyncSession, actor: UserResponse | None = None) -> dict:
    authors = (await db.execute(select(Author.name).join(BookAuthor, BookAuthor.author_id == Author.id).where(BookAuthor.book_id == book.id))).scalars().all()
    courses = (await db.execute(select(BookCourse.course_id).where(BookCourse.book_id == book.id))).scalars().all()
    modules = (await db.execute(select(Module).join(BookModule, BookModule.module_id == Module.id).where(BookModule.book_id == book.id))).scalars().all()
    profile = (await db.execute(select(User_profiles).where(User_profiles.user_id == book.uploaded_by))).scalar_one_or_none()
    deadline = _utc(book.created_at) + CP_WINDOW if book.created_at else None
    payload = {column.name: getattr(book, column.name) for column in Book.__table__.columns}
    payload.update({"authors": authors, "course_ids": courses, "modules": [{"id": module.id, "name": module.name, "code": module.code, "course_id": module.course_id} for module in modules], "uploader_name": profile.display_name if profile else None, "uploader_role": profile.role if profile else None, "management_deadline": deadline, "can_manage": bool(actor and can_manage_book(actor, book, await database_now(db)))})
    return payload


def _ensure_creator(actor: UserResponse) -> None:
    if not can_create_book(actor):
        raise HTTPException(status_code=403, detail="Only an administrator or CP can create books")


@router.post("", status_code=201)
async def create_book(payload: BookCreate, actor: UserResponse = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _ensure_creator(actor)
    data = payload.model_dump(exclude={"authors", "course_ids", "module_ids", "cover", "file"})
    # Ownership, creation time, and management deadline never come from the request.
    book = Book(uploaded_by=str(actor.id), **data)
    if payload.cover:
        book.cover_key, book.cover_file_name, book.cover_mime_type = payload.cover.key, payload.cover.original_filename, payload.cover.mime_type
    if payload.file:
        book.file_key, book.file_name, book.file_mime_type, book.file_size = payload.file.key, payload.file.original_filename, payload.file.mime_type, payload.file.size
        book.file_uploaded_at = await database_now(db)
    db.add(book); await db.flush()
    await _replace_authors(db, book.id, payload.authors); await _replace_courses(db, book.id, payload.course_ids); await _replace_modules(db, book.id, payload.module_ids)
    await _activity(db, book, actor, "created", f'Created book "{book.title}"')
    await db.commit(); await db.refresh(book)
    return await _serialize(book, db, actor)


@router.get("")
async def list_books(include_deleted: bool = False, status_filter: Optional[str] = Query(None, alias="status"), uploaded_by: Optional[str] = None, uploader_role: Optional[str] = None, course_id: Optional[str] = None, author: Optional[str] = None, management_state: Optional[Literal["within_48h", "expired"]] = None, actor: UserResponse = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    query = select(Book)
    if include_deleted:
        if actor.role != "admin": raise HTTPException(403, "Only administrators can view deleted books")
    else: query = query.where(Book.deleted_at.is_(None))
    # Readers only receive published books. Management users can inspect the
    # catalogue (including drafts) as part of their review responsibilities.
    if actor.role not in MANAGEMENT_ROLES:
        query = query.where(Book.status == "active", Book.visibility == "public")
    if status_filter: query = query.where(Book.status == status_filter)
    if uploaded_by: query = query.where(Book.uploaded_by == uploaded_by)
    if course_id: query = query.where(Book.id.in_(select(BookCourse.book_id).where(BookCourse.course_id == course_id)))
    if author: query = query.where(Book.id.in_(select(BookAuthor.book_id).join(Author, Author.id == BookAuthor.author_id).where(Author.name.ilike(f"%{author}%"))))
    if uploader_role:
        query = query.where(Book.uploaded_by.in_(select(User_profiles.user_id).where(User_profiles.role == uploader_role)))
    books = (await db.execute(query.order_by(Book.created_at.desc()))).scalars().all()
    if management_state:
        now = await database_now(db)
        cp_ids = set((await db.execute(select(User_profiles.user_id).where(User_profiles.role == "cp"))).scalars().all())
        books = [
            book for book in books
            if book.uploaded_by in cp_ids
            and (now <= _utc(book.created_at) + CP_WINDOW) == (management_state == "within_48h")
        ]
    return {"items": [await _serialize(book, db, actor) for book in books], "total": len(books)}


@router.get("/stats")
async def book_stats(actor: UserResponse = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if actor.role != "admin": raise HTTPException(403, "Admin access required")
    books = (await db.execute(select(Book).where(Book.deleted_at.is_(None)))).scalars().all(); now = await database_now(db)
    today, week = now - timedelta(days=1), now - timedelta(days=7)
    cp_ids = set((await db.execute(select(User_profiles.user_id).where(User_profiles.role == "cp"))).scalars().all())
    return {"total_books": len(books), "active_books": sum(b.status == "active" for b in books), "draft_books": sum(b.status == "draft" for b in books), "archived_books": sum(b.status == "archived" for b in books), "books_added_today": sum(_utc(b.created_at) >= today for b in books), "books_added_this_week": sum(_utc(b.created_at) >= week for b in books), "books_added_by_cp": sum(b.uploaded_by in cp_ids for b in books), "books_added_by_admin": sum(b.uploaded_by not in cp_ids for b in books), "cp_books_within_48_hours": sum(b.uploaded_by in cp_ids and now <= _utc(b.created_at) + CP_WINDOW for b in books), "cp_books_past_48_hours": sum(b.uploaded_by in cp_ids and now > _utc(b.created_at) + CP_WINDOW for b in books)}


@router.post("/{book_id}/record-download")
async def record_book_download(book_id: int, actor: UserResponse = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    book = await _get_book(book_id, db)
    if actor.role not in MANAGEMENT_ROLES and (book.status != "active" or book.visibility != "public"):
        raise HTTPException(status_code=404, detail="Book not found")
    book.download_count = (book.download_count or 0) + 1
    await db.commit()
    return {"download_count": book.download_count}


@router.get("/{book_id}")
async def get_book(book_id: int, actor: UserResponse = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    book = await _get_book(book_id, db)
    if actor.role not in MANAGEMENT_ROLES and (book.status != "active" or book.visibility != "public"):
        raise HTTPException(404, "Book not found")
    return await _serialize(book, db, actor)


@router.put("/{book_id}")
async def update_book(book_id: int, payload: BookUpdate, actor: UserResponse = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    book = await _get_book(book_id, db); await _require_manager(book, actor, db)
    for key, value in payload.model_dump(exclude_unset=True).items(): setattr(book, key, value)
    await _activity(db, book, actor, "updated", "Updated book metadata"); await db.commit(); await db.refresh(book)
    return await _serialize(book, db, actor)


@router.patch("/{book_id}/status")
async def update_status(book_id: int, payload: StatusUpdate, actor: UserResponse = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    book = await _get_book(book_id, db); await _require_manager(book, actor, db); old = book.status; book.status = payload.status
    await _activity(db, book, actor, "status_updated", f"Changed status from {old} to {book.status}"); await db.commit(); await db.refresh(book)
    return await _serialize(book, db, actor)


@router.patch("/{book_id}/authors")
async def update_authors(book_id: int, payload: AuthorsUpdate, actor: UserResponse = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    book = await _get_book(book_id, db); await _require_manager(book, actor, db); await _replace_authors(db, book.id, payload.authors)
    await _activity(db, book, actor, "authors_updated", "Updated authors"); await db.commit(); return await _serialize(book, db, actor)


@router.patch("/{book_id}/courses")
async def update_courses(book_id: int, payload: CoursesUpdate, actor: UserResponse = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    book = await _get_book(book_id, db); await _require_manager(book, actor, db); await _replace_courses(db, book.id, payload.course_ids)
    await _activity(db, book, actor, "courses_updated", "Updated related courses"); await db.commit(); return await _serialize(book, db, actor)


@router.patch("/{book_id}/modules")
async def update_modules(book_id: int, payload: ModulesUpdate, actor: UserResponse = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    book = await _get_book(book_id, db); await _require_manager(book, actor, db); await _replace_modules(db, book.id, payload.module_ids)
    await _activity(db, book, actor, "modules_updated", "Updated related modules"); await db.commit(); return await _serialize(book, db, actor)


def _normalize_module_name(name: str) -> str:
    return " ".join(name.lower().split())


@router.get("/modules/catalog")
async def list_modules(query: Optional[str] = None, db: AsyncSession = Depends(get_db), _actor: UserResponse = Depends(get_current_user)):
    statement = select(Module).order_by(Module.name).limit(100)
    if query: statement = statement.where(Module.normalized_name.like(f"%{_normalize_module_name(query)}%"))
    rows = (await db.execute(statement)).scalars().all()
    return {"items": [{"id": row.id, "name": row.name, "code": row.code, "description": row.description, "course_id": row.course_id} for row in rows]}


@router.post("/modules", status_code=201)
async def create_module(payload: ModuleCreate, actor: UserResponse = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _ensure_creator(actor)
    normalized = _normalize_module_name(payload.name)
    existing = (await db.execute(select(Module).where(Module.normalized_name == normalized))).scalar_one_or_none()
    if existing:
        return {"id": existing.id, "name": existing.name, "code": existing.code, "description": existing.description, "course_id": existing.course_id, "existing": True}
    module = Module(name=payload.name.strip(), normalized_name=normalized, code=payload.code.strip() if payload.code else None, description=payload.description, course_id=payload.course_id, created_by=str(actor.id))
    db.add(module); await db.commit(); await db.refresh(module)
    return {"id": module.id, "name": module.name, "code": module.code, "description": module.description, "course_id": module.course_id, "existing": False}


@router.post("/{book_id}/file")
async def replace_file(book_id: int, payload: FileReference, actor: UserResponse = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    book = await _get_book(book_id, db); await _require_manager(book, actor, db)
    book.file_key, book.file_name, book.file_mime_type, book.file_size, book.file_uploaded_at = payload.key, payload.original_filename, payload.mime_type, payload.size, await database_now(db)
    await _activity(db, book, actor, "file_replaced", "Replaced book file"); await db.commit(); await db.refresh(book); return await _serialize(book, db, actor)


@router.post("/{book_id}/cover")
async def replace_cover(book_id: int, payload: FileReference, actor: UserResponse = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    book = await _get_book(book_id, db); await _require_manager(book, actor, db)
    book.cover_key, book.cover_file_name, book.cover_mime_type = payload.key, payload.original_filename, payload.mime_type
    await _activity(db, book, actor, "cover_replaced", "Replaced book cover"); await db.commit(); await db.refresh(book); return await _serialize(book, db, actor)


@router.delete("/{book_id}")
async def delete_book(book_id: int, actor: UserResponse = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    book = await _get_book(book_id, db); await _require_manager(book, actor, db)
    book.deleted_at, book.deleted_by = await database_now(db), str(actor.id); await _activity(db, book, actor, "deleted", "Soft deleted book")
    await db.commit(); return {"id": book_id, "message": "Book deleted"}


@router.post("/{book_id}/restore")
async def restore_book(book_id: int, actor: UserResponse = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if actor.role != "admin": raise HTTPException(403, "Only administrators can restore books")
    book = await _get_book(book_id, db, include_deleted=True)
    if book.deleted_at is None: raise HTTPException(400, "Book is not deleted")
    book.deleted_at = book.deleted_by = None; await _activity(db, book, actor, "restored", "Restored book"); await db.commit(); await db.refresh(book); return await _serialize(book, db, actor)


@router.get("/{book_id}/activity")
async def book_activity(book_id: int, actor: UserResponse = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    book = await _get_book(book_id, db, include_deleted=actor.role == "admin")
    if actor.role != "admin" and book.uploaded_by != str(actor.id): raise HTTPException(403, "You can only view activity for your own books")
    rows = (await db.execute(select(BookActivity).where(BookActivity.book_id == book_id).order_by(BookActivity.created_at.desc()))).scalars().all()
    return {"items": [{c.name: getattr(row, c.name) for c in BookActivity.__table__.columns} for row in rows]}
