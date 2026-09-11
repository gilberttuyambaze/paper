import os
import json
from pathlib import Path
from typing import Dict

from core.database import get_db
from dependencies.auth import get_current_user, get_admin_user
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from schemas.auth import UserResponse
from services.authorization import require_permission
from services.site_access import get_site_settings, serialize_site_settings, update_site_settings
from services.heartbeat import heartbeat_activity_stream, heartbeat_status, run_heartbeat_once, validate_heartbeat_config
from models.system_health import SystemHealthHeartbeat

router = APIRouter(prefix="/api/v1/admin/settings", tags=["admin-settings"])

SENSITIVE_ENV_TOKENS = (
    "SECRET",
    "TOKEN",
    "PASSWORD",
    "KEY",
    "PRIVATE",
    "DATABASE_URL",
    "SMTP",
)


class EnvVariable(BaseModel):
    key: str
    value: str
    description: str = ""
    is_sensitive: bool = False


class EnvConfig(BaseModel):
    backend_vars: Dict[str, EnvVariable]
    frontend_vars: Dict[str, EnvVariable]


class EnvVariableUpdate(BaseModel):
    value: str


class SiteAccessUpdate(BaseModel):
    maintenance_mode: bool | None = None
    maintenance_message: str | None = None
    upload_access_mode: str | None = None
    upload_roles: list[str] | None = None
    allowed_resource_types: list[str] | None = None
    heartbeat_enabled: bool | None = None
    heartbeat_min_weekly_checks: int | None = None
    heartbeat_max_weekly_checks: int | None = None
    heartbeat_retry_delay_hours: int | None = None
    heartbeat_max_retry_attempts: int | None = None
    heartbeat_retry_enabled: bool | None = None
    heartbeat_retry_jitter_minutes: int | None = None
    heartbeat_run_on_startup: bool | None = None
    heartbeat_notify_admin: bool | None = None


@router.get("/site-access")
async def get_site_access(_current_user: UserResponse = Depends(get_current_user), db=Depends(get_db)):
    require_permission(_current_user, "site.settings.view")
    require_permission(_current_user, "system.health.view")
    settings = await get_site_settings(db)
    payload = serialize_site_settings(settings)
    heartbeat = await db.get(SystemHealthHeartbeat, 1)
    if heartbeat:
        payload["heartbeat"] = heartbeat_status(heartbeat, settings, False)
    return payload


@router.put("/site-access")
async def save_site_access(payload: SiteAccessUpdate, _current_user: UserResponse = Depends(get_current_user), db=Depends(get_db)):
    values = payload.model_dump(exclude_none=True)
    heartbeat_fields = {
        "heartbeat_enabled", "heartbeat_min_weekly_checks", "heartbeat_max_weekly_checks",
        "heartbeat_retry_delay_hours", "heartbeat_max_retry_attempts", "heartbeat_retry_enabled",
        "heartbeat_retry_jitter_minutes", "heartbeat_run_on_startup", "heartbeat_notify_admin",
    }
    # Lock state/message are site settings; heartbeat configuration separately
    # requires the narrower system-health management capability.
    if any(field in values for field in heartbeat_fields):
        require_permission(_current_user, "system.health.manage")
    if any(field not in heartbeat_fields for field in values):
        require_permission(_current_user, "site.settings.manage")
    existing = await get_site_settings(db)
    try:
        validate_heartbeat_config({**serialize_site_settings(existing), **values})
    except (TypeError, ValueError) as error:
        raise HTTPException(status_code=400, detail=str(error))
    settings = await update_site_settings(db, values)
    await db.commit()
    await db.refresh(settings)
    return serialize_site_settings(settings)


@router.post("/heartbeat/run")
async def run_heartbeat_now(_current_user: UserResponse = Depends(get_current_user), db=Depends(get_db)):
    require_permission(_current_user, "system.health.manage")
    settings = await get_site_settings(db)
    result = await run_heartbeat_once(db, settings, manual=True)
    heartbeat = await db.get(SystemHealthHeartbeat, 1)
    return {**result, "heartbeat": heartbeat_status(heartbeat, settings, False)}


@router.get("/heartbeat")
async def get_heartbeat(request: Request, _current_user: UserResponse = Depends(get_current_user), db=Depends(get_db)):
    """Administrative read-only health telemetry; errors are already sanitized."""
    require_permission(_current_user, "system.health.view")
    settings = await get_site_settings(db)
    heartbeat = await db.get(SystemHealthHeartbeat, 1)
    return heartbeat_status(heartbeat, settings, bool(getattr(request.app.state, "heartbeat_scheduler_running", False)))


@router.get("/heartbeat/stream")
async def heartbeat_stream(_current_user: UserResponse = Depends(get_current_user)):
    require_permission(_current_user, "system.health.view")

    async def events():
        async for event in heartbeat_activity_stream():
            yield f"event: heartbeat\ndata: {json.dumps(event)}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


def get_env_file_path(env_type: str) -> Path:
    """Get the path to the environment variable file."""
    base_path = Path(__file__).parent.parent
    if env_type == "backend":
        return base_path / ".env"
    if env_type == "frontend":
        return base_path.parent / "frontend" / ".env"
    raise ValueError("Invalid env_type")


def read_env_file(env_type: str) -> Dict[str, str]:
    """Read an environment variable file."""
    env_file = get_env_file_path(env_type)
    if not env_file.exists():
        return {}

    env_vars = {}
    with open(env_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                env_vars[key.strip()] = value.strip()
    return env_vars


def write_env_file(env_type: str, env_vars: Dict[str, str]):
    """Write to an environment variable file."""
    env_file = get_env_file_path(env_type)
    env_file.parent.mkdir(parents=True, exist_ok=True)

    with open(env_file, "w", encoding="utf-8") as f:
        for key, value in env_vars.items():
            f.write(f"{key}={value}\n")


def is_sensitive_key(key: str) -> bool:
    normalized = key.upper()
    return any(token in normalized for token in SENSITIVE_ENV_TOKENS)


def mask_sensitive_value(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:2]}{'*' * (len(value) - 6)}{value[-4:]}"


def ensure_runtime_env_mutation_allowed() -> None:
    mutation_allowed = os.getenv("ALLOW_RUNTIME_ENV_MUTATION", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if mutation_allowed:
        return

    raise HTTPException(
        status_code=403,
        detail="Runtime environment mutation is disabled. Set ALLOW_RUNTIME_ENV_MUTATION=true only for controlled maintenance workflows.",
    )


def build_env_variable(key: str, value: str, descriptions: Dict[str, str]) -> EnvVariable:
    sensitive = is_sensitive_key(key)
    return EnvVariable(
        key=key,
        value=mask_sensitive_value(value) if sensitive else value,
        description=descriptions.get(key, ""),
        is_sensitive=sensitive,
    )


@router.get("", response_model=EnvConfig)
async def get_settings(current_user: UserResponse = Depends(get_admin_user)):
    """Retrieve environment variable configuration."""
    try:
        backend_vars = read_env_file("backend")
        frontend_vars = read_env_file("frontend")

        backend_descriptions = {
            "DATABASE_URL": "Database connection string",
            "STRIPE_SECRET_KEY": "Stripe secret key",
            "STRIPE_SUCCESS_URL": "Payment success callback URL",
            "STRIPE_CANCEL_URL": "Payment cancellation callback URL",
            "ALLOWED_DOMAINS": "Allowed domains",
            "OIDC_ISSUER_URL": "OIDC issuer URL",
            "OIDC_CLIENT_ID": "OIDC client ID",
            "OIDC_CLIENT_SECRET": "OIDC client secret",
            "OIDC_SCOPE": "OIDC scopes",
            "HOST": "Server host address",
            "PORT": "Server port",
            "FRONTEND_URL": "Frontend URL",
            "JWT_SECRET_KEY": "JWT signing secret key",
            "JWT_ALGORITHM": "JWT signing algorithm",
            "JWT_EXPIRE_MINUTES": "JWT expiration time (minutes)",
            "ADMIN_USER_ID": "Admin user ID",
            "ADMIN_USER_EMAIL": "Admin user email",
            "ALLOW_RUNTIME_ENV_MUTATION": "Allow runtime editing of env files",
        }
        frontend_descriptions = {
            "VITE_API_BASE_URL": "Base API URL",
            "VITE_FRONTEND_URL": "Frontend URL",
        }

        backend_config = {
            key: build_env_variable(key, value, backend_descriptions) for key, value in backend_vars.items()
        }
        frontend_config = {
            key: build_env_variable(key, value, frontend_descriptions) for key, value in frontend_vars.items()
        }

        return EnvConfig(backend_vars=backend_config, frontend_vars=frontend_config)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read configuration: {str(e)}")


@router.put("/backend/{key}")
async def update_backend_setting(
    key: str, update: EnvVariableUpdate, current_user: UserResponse = Depends(get_admin_user)
):
    """Update a backend environment variable."""
    try:
        ensure_runtime_env_mutation_allowed()
        env_vars = read_env_file("backend")
        env_vars[key] = update.value
        write_env_file("backend", env_vars)
        return {"message": f"Backend configuration '{key}' updated successfully; restart required to take effect."}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update configuration: {str(e)}")


@router.put("/frontend/{key}")
async def update_frontend_setting(
    key: str, update: EnvVariableUpdate, current_user: UserResponse = Depends(get_admin_user)
):
    """Update a frontend environment variable."""
    try:
        ensure_runtime_env_mutation_allowed()
        env_vars = read_env_file("frontend")
        env_vars[key] = update.value
        write_env_file("frontend", env_vars)
        return {"message": f"Frontend configuration '{key}' updated successfully; restart required to take effect."}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update configuration: {str(e)}")


@router.post("/backend/{key}")
async def add_backend_setting(
    key: str, update: EnvVariableUpdate, current_user: UserResponse = Depends(get_admin_user)
):
    """Add a backend environment variable."""
    try:
        ensure_runtime_env_mutation_allowed()
        env_vars = read_env_file("backend")
        env_vars[key] = update.value
        write_env_file("backend", env_vars)
        return {"message": f"Backend configuration '{key}' added successfully; restart required to take effect."}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to add configuration: {str(e)}")


@router.post("/frontend/{key}")
async def add_frontend_setting(
    key: str, update: EnvVariableUpdate, current_user: UserResponse = Depends(get_admin_user)
):
    """Add a frontend environment variable."""
    try:
        ensure_runtime_env_mutation_allowed()
        env_vars = read_env_file("frontend")
        env_vars[key] = update.value
        write_env_file("frontend", env_vars)
        return {"message": f"Frontend configuration '{key}' added successfully; restart required to take effect."}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to add configuration: {str(e)}")


@router.delete("/backend/{key}")
async def delete_backend_setting(key: str, current_user: UserResponse = Depends(get_admin_user)):
    """Delete a backend environment variable."""
    try:
        ensure_runtime_env_mutation_allowed()
        env_vars = read_env_file("backend")
        if key in env_vars:
            del env_vars[key]
            write_env_file("backend", env_vars)
            return {"message": f"Backend configuration '{key}' deleted successfully; restart required to take effect."}
        raise HTTPException(status_code=404, detail=f"Configuration item '{key}' does not exist")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete configuration: {str(e)}")


@router.delete("/frontend/{key}")
async def delete_frontend_setting(key: str, current_user: UserResponse = Depends(get_admin_user)):
    """Delete a frontend environment variable."""
    try:
        ensure_runtime_env_mutation_allowed()
        env_vars = read_env_file("frontend")
        if key in env_vars:
            del env_vars[key]
            write_env_file("frontend", env_vars)
            return {"message": f"Frontend configuration '{key}' deleted successfully; restart required to take effect."}
        raise HTTPException(status_code=404, detail=f"Configuration item '{key}' does not exist")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete configuration: {str(e)}")
