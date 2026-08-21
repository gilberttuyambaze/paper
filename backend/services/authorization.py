"""Single source of truth for upload and book ownership authorization."""

from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

CP_WINDOW = timedelta(hours=48)
UPLOAD_ROLES = {"admin", "cp"}


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


async def database_now(db: AsyncSession) -> datetime:
    """Read the current time from the database, never from a client clock."""
    return _utc((await db.execute(select(func.now()))).scalar_one())


def can_upload(user) -> bool:
    return user.role in UPLOAD_ROLES


def can_create_book(user) -> bool:
    return can_upload(user)


def can_manage_book(user, book, now: datetime) -> bool:
    if user.role == "admin":
        return True
    if user.role != "cp" or book.uploaded_by != str(user.id) or not book.created_at:
        return False
    # Exactly 48 hours: access ends at the deadline.
    return _utc(now) < _utc(book.created_at) + CP_WINDOW


def can_manage_paper(user, paper, now: datetime) -> bool:
    if user.role == "admin":
        return True
    if user.role != "cp" or paper.user_id != str(user.id) or not paper.created_at:
        return False
    return _utc(now) < _utc(paper.created_at) + CP_WINDOW


async def require_upload_permission(user) -> None:
    if not can_upload(user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only administrators and CPs can upload")


async def require_book_management(db: AsyncSession, user, book) -> None:
    if not can_manage_book(user, book, await database_now(db)):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You cannot manage this book. CP access ends exactly 48 hours after creating their own book.")


async def require_paper_management(db: AsyncSession, user, paper) -> None:
    if not can_manage_paper(user, paper, await database_now(db)):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You cannot manage this paper. CP access ends exactly 48 hours after creating their own paper.")
