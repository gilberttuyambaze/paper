"""Paginated normalized browser feed for Papers and Books."""
from typing import Literal, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from core.database import get_db
from dependencies.auth import get_current_user
from models.books import Author, Book, BookAuthor, BookCourse, BookModule, Module
from models.courses import Course
from models.papers import Papers
from models.user_profiles import User_profiles
from schemas.auth import UserResponse

router = APIRouter(prefix="/api/v1/resources", tags=["resources"])

async def _profile(db, user_id):
    row = (await db.execute(select(User_profiles).where(User_profiles.user_id == user_id))).scalar_one_or_none()
    return {"id": user_id, "name": row.display_name if row else user_id}

@router.get("")
async def list_resources(type: Literal["all", "paper", "book"] = "all", q: Optional[str] = None, course_id: Optional[int] = None, module_id: Optional[int] = None, year: Optional[int] = None, skip: int = Query(0, ge=0), limit: int = Query(30, ge=1, le=100), _user: UserResponse = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    items = []
    if type in {"all", "paper"}:
        query = select(Papers).where(Papers.is_hidden.is_not(True))
        if q:
            like = f"%{q}%"; query = query.where(or_(Papers.title.ilike(like), Papers.course_code.ilike(like), Papers.course_name.ilike(like), Papers.description.ilike(like), Papers.lecturer.ilike(like)))
        if year: query = query.where(Papers.year == year)
        papers = (await db.execute(query)).scalars().all()
        for paper in papers:
            items.append({"id": str(paper.id), "type": "paper", "title": paper.title, "description": paper.description, "year": paper.year, "created_at": paper.created_at, "thumbnail_url": None, "uploader": await _profile(db, paper.user_id), "courses": [{"id": None, "code": paper.course_code, "name": paper.course_name}], "modules": [], "authors": [], "paper": {"paper_type": paper.paper_type, "verification_status": paper.verification_status, "lecturer": paper.lecturer, "department": paper.department, "download_count": paper.download_count or 0}})
    if type in {"all", "book"}:
        query = select(Book).where(Book.deleted_at.is_(None), Book.status == "active", Book.visibility == "public")
        if q:
            like = f"%{q}%"; query = query.where(or_(Book.title.ilike(like), Book.description.ilike(like), Book.isbn.ilike(like), Book.publisher.ilike(like), Book.subject.ilike(like)))
        if year: query = query.where(Book.publication_year == year)
        if course_id: query = query.where(Book.id.in_(select(BookCourse.book_id).where(BookCourse.course_id == course_id)))
        if module_id: query = query.where(Book.id.in_(select(BookModule.book_id).where(BookModule.module_id == module_id)))
        books = (await db.execute(query)).scalars().all()
        for book in books:
            authors = (await db.execute(select(Author.name).join(BookAuthor, BookAuthor.author_id == Author.id).where(BookAuthor.book_id == book.id))).scalars().all()
            courses = (await db.execute(select(Course).join(BookCourse, BookCourse.course_id == Course.id).where(BookCourse.book_id == book.id))).scalars().all()
            modules = (await db.execute(select(Module).join(BookModule, BookModule.module_id == Module.id).where(BookModule.book_id == book.id))).scalars().all()
            items.append({"id": str(book.id), "type": "book", "title": book.title, "description": book.description, "year": book.publication_year, "created_at": book.created_at, "thumbnail_url": book.cover_key, "uploader": await _profile(db, book.uploaded_by), "courses": [{"id": row.id, "code": row.code, "name": row.name} for row in courses], "modules": [{"id": row.id, "name": row.name} for row in modules], "authors": authors, "book": {"language": book.language, "edition": book.edition, "publisher": book.publisher}})
    items.sort(key=lambda row: row.get("created_at") or 0, reverse=True)
    return {"items": items[skip:skip + limit], "total": len(items), "skip": skip, "limit": limit}
