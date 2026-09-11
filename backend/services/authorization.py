"""Authoritative role-to-permission authorization policy."""

from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

CP_WINDOW = timedelta(hours=48)

ROLE_LEVELS: dict[str, int] = {
    "super_admin": 100,
    "admin": 90,
    "content_manager": 70,
    "lecturer": 60,
    "cp": 60,
    "verified_contributor": 60,
    "normal": 20,
    "user": 20,
}

PERMISSIONS = frozenset({
    "site.maintenance.bypass", "site.settings.view", "site.settings.manage", "system.health.view", "system.health.manage",
    "users.view", "users.edit_profile", "users.edit_academic", "users.change_verification", "users.change_status", "users.change_role", "users.delete", "users.transfer_super_admin", "users.manage",
    "books.view", "books.create", "books.edit", "books.edit_metadata", "books.delete", "books.replace_file", "books.replace_cover", "books.own.manage",
    "papers.view", "papers.create", "papers.edit", "papers.edit_metadata", "papers.delete", "papers.replace_file", "papers.replace_cover", "papers.manage_solutions", "papers.own.manage",
    "papers.verify", "papers.hide", "reports.manage",
    "uploads.book", "uploads.paper", "admin.dashboard.view", "storage.manage", "storage.delete",
})

ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "super_admin": PERMISSIONS,
    "admin": frozenset({
        "site.maintenance.bypass", "site.settings.view", "site.settings.manage", "system.health.view", "system.health.manage",
        "users.view", "users.edit_profile", "users.edit_academic", "users.change_verification", "users.change_status", "users.change_role", "users.delete", "users.manage",
        "books.view", "books.create", "books.edit", "books.edit_metadata", "books.delete", "books.replace_file", "books.replace_cover",
        "papers.view", "papers.create", "papers.edit", "papers.edit_metadata", "papers.delete", "papers.replace_file", "papers.replace_cover", "papers.manage_solutions",
        "papers.verify", "papers.hide", "reports.manage",
        "uploads.book", "uploads.paper", "admin.dashboard.view", "storage.manage", "storage.delete",
    }),
    "content_manager": frozenset({
        "admin.dashboard.view", "users.view",
        "books.view", "books.edit_metadata",
        "papers.view", "papers.edit_metadata", "papers.verify", "papers.hide",
        "reports.manage",
    }),
    "cp": frozenset({
        "books.view", "books.create", "books.own.manage",
        "papers.view", "papers.create", "papers.own.manage",
        "uploads.book", "uploads.paper",
    }),
    "lecturer": frozenset({"books.view", "papers.view"}),
    "verified_contributor": frozenset({"books.view", "papers.view"}),
    "normal": frozenset({"books.view", "papers.view"}),
    "user": frozenset({"books.view", "papers.view"}),
}

CONTENT_MANAGER_EDITABLE_RESOURCE_FIELDS = frozenset({
    "title", "description", "course_code", "course_name", "college", "department",
    "year", "paper_type", "lecturer", "institution_id", "campus_id", "college_id",
    "school_id", "academic_department_id", "programme_id", "programme_name_other",
    "semester", "examination_session", "category", "subject", "isbn", "edition",
    "publication_year", "language", "publisher",
})


def role_level(role: str | None) -> int:
    return ROLE_LEVELS.get((role or "user").strip().lower(), 20)


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
    return has_permission(user, "users.transfer_super_admin") or role_level(getattr(user, "role", None)) >= 100


def is_admin_or_super_admin(user) -> bool:
    return role_level(getattr(user, "role", None)) >= 90


def actor_can_manage_target(actor, target) -> bool:
    """Check if actor role level permits administrative action on target."""
    actor_role = getattr(actor, "role", None) if hasattr(actor, "role") else str(actor) if isinstance(actor, str) else None
    target_role = getattr(target, "role", None) if hasattr(target, "role") else str(target) if isinstance(target, str) else None
    actor_lvl = role_level(actor_role)
    target_lvl = role_level(target_role)

    # Content Manager and below cannot administratively manage any user
    if actor_lvl < 90:
        return False

    # Super Admin can manage all roles
    if actor_lvl >= 100:
        return True

    # Admin (90) can only manage targets strictly lower (< 90)
    # Super Admin targets are strictly rejected for normal Admin
    return target_lvl < 90


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
    return has_permission(user, "books.view") and (has_permission(user, "books.edit") or has_permission(user, "books.edit_metadata") or (book.status == "active" and book.visibility == "public"))


def can_manage_book(user, book, now: datetime) -> bool:
    if has_permission(user, "books.edit") or has_permission(user, "books.edit_metadata"):
        return True
    if not has_permission(user, "books.own.manage") or str(getattr(book, "uploaded_by", None)) != str(getattr(user, "id", None)) or not book.created_at:
        return False
    # Exactly 48 hours: access ends at the deadline.
    return _utc(now) < _utc(book.created_at) + CP_WINDOW


def can_manage_paper(user, paper, now: datetime) -> bool:
    if has_permission(user, "papers.edit") or has_permission(user, "papers.edit_metadata"):
        return True
    if not has_permission(user, "papers.own.manage") or str(getattr(paper, "user_id", None)) != str(getattr(user, "id", None)) or not paper.created_at:
        return False
    return _utc(now) < _utc(paper.created_at) + CP_WINDOW


def can_delete_book(user, book, now: datetime) -> bool:
    if has_permission(user, "books.delete"):
        return True
    if not has_permission(user, "books.own.manage") or str(getattr(book, "uploaded_by", None)) != str(getattr(user, "id", None)) or not book.created_at:
        return False
    return _utc(now) < _utc(book.created_at) + CP_WINDOW


def can_delete_paper(user, paper, now: datetime) -> bool:
    if has_permission(user, "papers.delete"):
        return True
    if not has_permission(user, "papers.own.manage") or str(getattr(paper, "user_id", None)) != str(getattr(user, "id", None)) or not paper.created_at:
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


async def require_book_deletion(db: AsyncSession, user, book) -> None:
    if not can_delete_book(user, book, await database_now(db)):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have permission to delete this book.")


async def require_paper_deletion(db: AsyncSession, user, paper) -> None:
    if not can_delete_paper(user, paper, await database_now(db)):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have permission to delete this paper.")
