"""Authoritative role-to-permission authorization policy."""

from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

CP_WINDOW = timedelta(hours=48)
PERMISSIONS = frozenset({
    "site.maintenance.bypass", "site.settings.view", "site.settings.manage", "system.health.view", "system.health.manage",
    "users.view", "users.manage", "users.delete", "users.transfer_super_admin",
    "books.view", "books.create", "books.edit", "books.delete", "books.replace_file", "books.replace_cover", "books.own.manage",
    "papers.view", "papers.create", "papers.edit", "papers.delete", "papers.replace_file", "papers.replace_cover", "papers.manage_solutions", "papers.own.manage",
    "uploads.book", "uploads.paper", "admin.dashboard.view",
})

ROLE_PERMISSIONS = {
    "super_admin": PERMISSIONS,
    "admin": frozenset({"site.maintenance.bypass", "site.settings.view", "system.health.view", "users.view", "users.manage", "users.delete", "books.view", "books.create", "books.edit", "books.delete", "books.replace_file", "books.replace_cover", "papers.view", "papers.create", "papers.edit", "papers.delete", "papers.replace_file", "papers.replace_cover", "papers.manage_solutions", "uploads.book", "uploads.paper", "admin.dashboard.view"}),
    "content_manager": frozenset({"users.view", "users.manage", "users.delete", "books.view", "papers.view", "admin.dashboard.view"}),
    "cp": frozenset({"books.view", "books.create", "books.own.manage", "papers.view", "papers.create", "papers.own.manage", "uploads.book", "uploads.paper"}),
    "lecturer": frozenset({"books.view", "papers.view"}),
    "verified_contributor": frozenset({"books.view", "papers.view"}),
    "normal": frozenset({"books.view", "papers.view"}),
    "user": frozenset({"books.view", "papers.view"}),
}


def permissions_for_role(role: str | None) -> frozenset[str]:
    return ROLE_PERMISSIONS.get((role or "user").strip().lower(), frozenset())


def role_has_permission(role: str | None, permission: str) -> bool:
    return permission in PERMISSIONS and permission in permissions_for_role(role)


def has_permission(user, permission: str) -> bool:
    return role_has_permission(getattr(user, "role", None), permission)


def require_permission(user, permission: str):
    if not has_permission(user, permission):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Permission required: {permission}")
    return user


def is_super_admin(user) -> bool:
    return has_permission(user, "users.transfer_super_admin")


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


async def database_now(db: AsyncSession) -> datetime:
    """Read the current time from the database, never from a client clock."""
    return _utc((await db.execute(select(func.now()))).scalar_one())


def can_upload(user) -> bool:
    return has_permission(user, "uploads.book") or has_permission(user, "uploads.paper")


def can_create_book(user) -> bool:
    return has_permission(user, "books.create") and has_permission(user, "uploads.book")


def can_read_book(user, book) -> bool:
    """Reading follows publication visibility; ownership only affects management."""
    if user is None:
        return book.status == "active" and book.visibility == "public"
    return has_permission(user, "books.view") and (has_permission(user, "books.edit") or (book.status == "active" and book.visibility == "public"))


def can_manage_book(user, book, now: datetime) -> bool:
    if has_permission(user, "books.edit"):
        return True
    if not has_permission(user, "books.own.manage") or book.uploaded_by != str(user.id) or not book.created_at:
        return False
    # Exactly 48 hours: access ends at the deadline.
    return _utc(now) < _utc(book.created_at) + CP_WINDOW


def can_manage_paper(user, paper, now: datetime) -> bool:
    if has_permission(user, "papers.edit"):
        return True
    if not has_permission(user, "papers.own.manage") or paper.user_id != str(user.id) or not paper.created_at:
        return False
    return _utc(now) < _utc(paper.created_at) + CP_WINDOW


async def require_upload_permission(user) -> None:
    if not can_upload(user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Upload permission required")


async def require_book_management(db: AsyncSession, user, book) -> None:
    if not can_manage_book(user, book, await database_now(db)):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You cannot manage this book. CP access ends exactly 48 hours after creating their own book.")


async def require_paper_management(db: AsyncSession, user, paper) -> None:
    if not can_manage_paper(user, paper, await database_now(db)):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You cannot manage this paper. CP access ends exactly 48 hours after creating their own paper.")
