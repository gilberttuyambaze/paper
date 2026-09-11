"""Central site access, upload policy, and Super Admin invariants."""

import json
import os
from typing import Iterable

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.auth import User
from models.site_settings import SiteSettings
from services.authorization import has_permission, is_super_admin


def user_can_bypass_maintenance(user) -> bool:
    if user is None:
        return False
    return bool(is_super_admin(user) or has_permission(user, "site.maintenance.bypass"))

UPLOAD_MODES = {"nobody", "authenticated", "selected_roles"}
RESOURCE_TYPES = {"book", "paper"}
DEFAULT_UPLOAD_ROLES = ["admin", "cp"]
DEFAULT_RESOURCE_TYPES = ["book", "paper"]


def require_super_admin(user):
    if not is_super_admin(user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Super Admin access required")
    return user


def _json_list(raw: str | None, default: list[str]) -> list[str]:
    try:
        value = json.loads(raw or "")
        if isinstance(value, list):
            return [str(item).strip().lower() for item in value if str(item).strip()]
    except (TypeError, ValueError):
        pass
    return list(default)


async def get_site_settings(db: AsyncSession) -> SiteSettings:
    settings = await db.get(SiteSettings, 1)
    if settings is None:
        settings = SiteSettings(id=1)
        db.add(settings)
        await db.flush()
    return settings


def serialize_site_settings(settings: SiteSettings) -> dict:
    return {
        "maintenance_mode": bool(settings.maintenance_mode),
        "maintenance_message": settings.maintenance_message,
        "upload_access_mode": settings.upload_access_mode,
        "upload_roles": _json_list(settings.upload_roles, DEFAULT_UPLOAD_ROLES),
        "allowed_resource_types": _json_list(settings.allowed_resource_types, DEFAULT_RESOURCE_TYPES),
        "heartbeat_enabled": bool(getattr(settings, "heartbeat_enabled", True)),
        "heartbeat_min_weekly_checks": getattr(settings, "heartbeat_min_weekly_checks", 2),
        "heartbeat_max_weekly_checks": getattr(settings, "heartbeat_max_weekly_checks", 3),
        "heartbeat_retry_delay_hours": getattr(settings, "heartbeat_retry_delay_hours", 6),
        "heartbeat_max_retry_attempts": getattr(settings, "heartbeat_max_retry_attempts", 2),
        "heartbeat_retry_enabled": bool(getattr(settings, "heartbeat_retry_enabled", True)),
        "heartbeat_retry_jitter_minutes": getattr(settings, "heartbeat_retry_jitter_minutes", 30),
        "heartbeat_run_on_startup": bool(getattr(settings, "heartbeat_run_on_startup", True)),
    }


def _set_json_list(values: Iterable[str], allowed: set[str]) -> str:
    normalized = sorted({str(value).strip().lower() for value in values if str(value).strip()} & allowed)
    return json.dumps(normalized)


async def can_upload_resource(db: AsyncSession, user, resource_type: str) -> bool:
    if not user or resource_type not in RESOURCE_TYPES:
        return False
    settings = await get_site_settings(db)
    if settings.maintenance_mode and not is_super_admin(user):
        return False
    if resource_type not in _json_list(settings.allowed_resource_types, DEFAULT_RESOURCE_TYPES):
        return False
    mode = settings.upload_access_mode
    if mode == "nobody":
        return False
    if mode == "authenticated":
        return True
    return has_permission(user, f"uploads.{resource_type}") and user.role in _json_list(settings.upload_roles, DEFAULT_UPLOAD_ROLES)


async def require_resource_upload(db: AsyncSession, user, resource_type: str):
    if not await can_upload_resource(db, user, resource_type):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Upload access is not enabled for {resource_type}s")


async def update_site_settings(db: AsyncSession, payload: dict) -> SiteSettings:
    settings = await get_site_settings(db)
    if "maintenance_mode" in payload:
        settings.maintenance_mode = bool(payload["maintenance_mode"])
    if "maintenance_message" in payload and payload["maintenance_message"] is not None:
        settings.maintenance_message = str(payload["maintenance_message"]).strip() or settings.maintenance_message
    if "upload_access_mode" in payload:
        mode = str(payload["upload_access_mode"]).strip().lower()
        if mode not in UPLOAD_MODES:
            raise HTTPException(status_code=400, detail="Invalid upload access mode")
        settings.upload_access_mode = mode
    if "upload_roles" in payload and payload.get("upload_access_mode", settings.upload_access_mode) == "selected_roles":
        settings.upload_roles = json.dumps(sorted({str(value).strip().lower() for value in payload["upload_roles"] if str(value).strip()}))
    if "allowed_resource_types" in payload:
        settings.allowed_resource_types = _set_json_list(payload["allowed_resource_types"], RESOURCE_TYPES)
    for key in ("heartbeat_enabled", "heartbeat_min_weekly_checks", "heartbeat_max_weekly_checks", "heartbeat_retry_delay_hours", "heartbeat_max_retry_attempts", "heartbeat_retry_enabled", "heartbeat_retry_jitter_minutes", "heartbeat_run_on_startup"):
        if key in payload:
            setattr(settings, key, payload[key])
    return settings


async def bootstrap_super_admin(db: AsyncSession) -> None:
    configured_id = os.getenv("SUPER_ADMIN_USER_ID", "").strip()
    configured_email = os.getenv("SUPER_ADMIN_USER_EMAIL", "").strip().lower()
    if not configured_id and not configured_email:
        return
    query = select(User).where(User.id == configured_id) if configured_id else select(User).where(User.email.ilike(configured_email))
    user = (await db.execute(query)).scalar_one_or_none()
    if user is None:
        raise RuntimeError("Configured Super Admin account does not exist")
    existing = (await db.execute(select(User).where(User.role == "super_admin", User.id != user.id))).scalars().all()
    if existing:
        raise RuntimeError("More than one Super Admin would exist; resolve the database before startup")
    user.role = "super_admin"
    await db.commit()
