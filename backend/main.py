import asyncio
import importlib
import logging
import os
import pkgutil
import traceback
from contextlib import asynccontextmanager
from datetime import datetime

from core.config import settings
from core.auth import AccessTokenError, decode_access_token
from core.database import db_manager
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.routing import APIRouter
from sqlalchemy import select
from models.auth import User
from models.user_profiles import User_profiles
from schemas.auth import UserResponse
from services.site_access import get_site_settings
from services.authorization import has_permission
from services.heartbeat import scheduler_loop

MAINTENANCE_TECHNICAL_EXEMPTIONS = frozenset({
    "/api/v1/auth/login", "/api/v1/auth/token/exchange", "/api/v1/auth/firebase/exchange",
    "/api/v1/auth/google", "/api/v1/auth/password-reset/request", "/api/v1/auth/password-reset/confirm",
    "/api/v1/auth/me", "/api/v1/auth/logout",
})


def is_maintenance_technical_exemption(path: str) -> bool:
    return path in MAINTENANCE_TECHNICAL_EXEMPTIONS or path.startswith("/health")

# MODULE_IMPORTS_START
from services.database import initialize_database, close_database
from services.mock_data import initialize_mock_data
from services.auth import initialize_admin_user
from services.site_access import bootstrap_super_admin
# MODULE_IMPORTS_END


def setup_logging():
    """Configure the logging system."""
    if os.environ.get("IS_LAMBDA") == "true":
        return

    # Create the logs directory
    log_dir = "logs"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    # Generate log filename with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = f"{log_dir}/app_{timestamp}.log"

    # Configure log format
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    # Configure the root logger
    logging.basicConfig(
        level=logging.DEBUG,
        format=log_format,
        handlers=[
            # File handler
            logging.FileHandler(log_file, encoding="utf-8"),
            # Console handler
            logging.StreamHandler(),
        ],
    )

    # Set log levels for specific modules
    logging.getLogger("uvicorn").setLevel(logging.DEBUG)
    logging.getLogger("fastapi").setLevel(logging.DEBUG)

    # Log configuration details
    logger = logging.getLogger(__name__)
    logger.info("=== Logging system initialized ===")
    logger.info(f"Log file: {log_file}")
    logger.info("Log level: INFO")
    logger.info(f"Timestamp: {timestamp}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger = logging.getLogger(__name__)
    logger.info("=== Application startup initiated ===")

    # MODULE_STARTUP_START
    await initialize_database()
    await initialize_mock_data()
    await initialize_admin_user()
    if db_manager.async_session_maker:
        async with db_manager.async_session_maker() as db:
            await get_site_settings(db)
            await bootstrap_super_admin(db)
            await db.commit()
    # MODULE_STARTUP_END

    heartbeat_stop = asyncio.Event()
    heartbeat_task = None
    app.state.heartbeat_scheduler_running = False
    if db_manager.async_session_maker and os.getenv("IS_LAMBDA", "").lower() not in {"1", "true", "yes"}:
        heartbeat_task = asyncio.create_task(scheduler_loop(db_manager.async_session_maker, heartbeat_stop, startup=True))
        app.state.heartbeat_scheduler_running = True
    logger.info("=== Application startup completed successfully ===")
    yield
    if heartbeat_task:
        heartbeat_stop.set()
        await heartbeat_task
    app.state.heartbeat_scheduler_running = False
    # MODULE_SHUTDOWN_START
    await close_database()
    # MODULE_SHUTDOWN_END


app = FastAPI(
    title="FastAPI Modular Template",
    description="A best-practice FastAPI template with modular architecture",
    version="1.0.0",
    lifespan=lifespan,
)


def _parse_comma_separated_values(raw_value: str | None) -> list[str]:
    if not raw_value:
        return []

    parsed: list[str] = []
    for token in raw_value.replace("\n", ",").split(","):
        normalized = token.strip().rstrip("/")
        if normalized:
            parsed.append(normalized)
    return parsed


def _build_cors_origins() -> list[str]:
    origins = {
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
        "https://paperhubur.vercel.app",
    }

    for raw_value in (
        getattr(settings, "frontend_url", ""),
        os.getenv("FRONTEND_URL", ""),
        os.getenv("CORS_ALLOWED_ORIGINS", ""),
    ):
        for origin in _parse_comma_separated_values(raw_value):
            if origin:
                origins.add(origin)

    for origin in _parse_comma_separated_values(os.getenv("CORS_ALLOWED_ORIGINS", "")):
        origins.add(origin)

    return sorted(origins)


# MODULE_MIDDLEWARE_START
app.add_middleware(
    CORSMiddleware,
    allow_origins=_build_cors_origins(),
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1|0\.0\.0\.0)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
    allow_headers=["Authorization", "Content-Type", "Accept", "Origin", "X-Requested-With"],
    expose_headers=["Authorization", "Content-Type"],
)
# MODULE_MIDDLEWARE_END


# Auto-discover and include all routers from the local `routers` package
def include_routers_from_package(app: FastAPI, package_name: str = "routers") -> None:
    """Discover and include all APIRouter objects from a package.

    This scans the given package (and subpackages) for module-level variables that
    are instances of FastAPI's APIRouter. It supports "router", "admin_router" names.
    """

    logger = logging.getLogger(__name__)

    try:
        pkg = importlib.import_module(package_name)
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.debug("Routers package '%s' not loaded: %s", package_name, exc)
        return

    discovered: int = 0
    for _finder, module_name, is_pkg in pkgutil.walk_packages(pkg.__path__, pkg.__name__ + "."):
        # Only import leaf modules; subpackages will be walked automatically
        if is_pkg:
            continue
        try:
            module = importlib.import_module(module_name)
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.warning("Failed to import module '%s': %s", module_name, exc)
            continue

        # Check for router variable names: router and admin_router
        for attr_name in ("router", "admin_router"):
            if not hasattr(module, attr_name):
                continue

            attr = getattr(module, attr_name)

            if isinstance(attr, APIRouter):
                app.include_router(attr)
                discovered += 1
                logger.info("Included router: %s.%s", module_name, attr_name)
            elif isinstance(attr, (list, tuple)):
                for idx, item in enumerate(attr):
                    if isinstance(item, APIRouter):
                        app.include_router(item)
                        discovered += 1
                        logger.info("Included router from list: %s.%s[%d]", module_name, attr_name, idx)

    if discovered == 0:
        logger.debug("No routers discovered in package '%s'", package_name)


# Setup logging before router discovery
setup_logging()
include_routers_from_package(app, "routers")


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    # Required for Firebase popup auth in modern browsers.
    response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin-allow-popups")
    return response


@app.middleware("http")
async def enforce_maintenance_mode(request: Request, call_next):
    path = request.url.path
    exempt = is_maintenance_technical_exemption(path)
    if not exempt and db_manager.async_session_maker:
        try:
            async with db_manager.async_session_maker() as db:
                site_settings = await get_site_settings(db)
                if site_settings.maintenance_mode:
                    role = None
                    user_id = None
                    authorization = request.headers.get("Authorization", "")
                    if authorization.lower().startswith("bearer "):
                        try:
                            payload = decode_access_token(authorization[7:].strip())
                            user_id = payload.get("sub")
                            user = await db.get(User, user_id) if user_id else None
                            role = user.role if user else None
                            profile = await db.scalar(select(User_profiles).where(User_profiles.user_id == user_id)) if user_id else None
                            if not has_permission(UserResponse(id=user_id, email="", role=role or "user"), "site.maintenance.bypass") and profile:
                                role = profile.role
                        except (AccessTokenError, ValueError):
                            role = None
                    if not has_permission(UserResponse(id=user_id or "", email="", role=role or "user"), "site.maintenance.bypass"):
                        return JSONResponse(status_code=503, content={"detail": site_settings.maintenance_message, "code": "SITE_MAINTENANCE", "maintenance": True})
        except Exception:
            logger.exception("Maintenance access check failed")
            return JSONResponse(status_code=503, content={"detail": "Site is currently under maintenance", "code": "SITE_MAINTENANCE", "maintenance": True})
    return await call_next(request)


def safe_error_message(status_code: int) -> str:
    messages = {
        400: "The request could not be processed.",
        401: "Your session has expired. Please sign in again.",
        403: "You do not have permission to perform this action.",
        404: "The requested resource was not found.",
        409: "This change conflicts with the current record state.",
        413: "The uploaded file is too large.",
        422: "Some information needs attention.",
        429: "Too many requests have been made. Please try again later.",
    }
    return messages.get(status_code, "We couldn't complete this action. Please try again.")


@app.exception_handler(RequestValidationError)
async def request_validation_handler(request: Request, exc: RequestValidationError):
    """Return field-level validation without exposing Pydantic internals."""
    fields = {}
    for error in exc.errors():
        location = [str(part) for part in error.get("loc", []) if part != "body"]
        field = ".".join(location) or "request"
        fields.setdefault(field, "Please check this field.")
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": {"code": "VALIDATION_ERROR", "message": safe_error_message(422), "fields": fields}},
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Keep HTTP error responses useful while filtering implementation details."""
    detail = exc.detail
    if isinstance(detail, dict) and isinstance(detail.get("code"), str) and isinstance(detail.get("message"), str):
        content = {"detail": {"code": detail["code"], "message": detail["message"]}}
        if isinstance(detail.get("fields"), dict):
            content["detail"]["fields"] = {
                str(key): str(value) for key, value in detail["fields"].items() if isinstance(value, (str, int, float))
            }
    else:
        content = {"detail": {"code": f"HTTP_{exc.status_code}", "message": safe_error_message(exc.status_code)}}
    return JSONResponse(status_code=exc.status_code, content=content, headers=exc.headers)


# Add exception handler for all remaining exceptions
@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Log technical details while returning a safe user-facing response."""

    logger = logging.getLogger(__name__)
    error_message = str(exc)
    error_type = type(exc).__name__

    # Log full error details regardless of environment
    logger.error(f"Exception: {error_type}: {error_message}\n{traceback.format_exc()}")

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": {"code": "INTERNAL_ERROR", "message": "We couldn't complete this action. Please try again."}},
    )


@app.get("/")
def root():
    return {"message": "FastAPI Modular Template is running"}


@app.get("/health")
def health_check():
    return {"status": "healthy"}


@app.get("/api/config")
def frontend_runtime_config(request: Request):
    origin = str(request.base_url).rstrip("/")
    return {
        "API_BASE_URL": os.getenv("FRONTEND_API_BASE_URL")
        or os.getenv("PYTHON_BACKEND_URL")
        or origin,
    }


def run_in_debug_mode(app: FastAPI):
    """Run the FastAPI app in debug mode with proper asyncio handling.

    This function handles the special case of running in a debugger (PyCharm, VS Code, etc.)
    where asyncio is patched, causing conflicts with uvicorn's asyncio_run.

    It loads environment variables from ../.env and uses asyncio.run() directly
    to avoid uvicorn's asyncio_run conflicts.

    Args:
        app: The FastAPI application instance
    """
    import asyncio
    from pathlib import Path

    import uvicorn
    from dotenv import load_dotenv

    # Load environment variables from ../.env in debug mode
    # If `LOCAL_DEBUG=true` is set, then MetaGPT's `ProjectBuilder.build()` will generate the `.env` file
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path, override=True)
        logger = logging.getLogger(__name__)
        logger.info(f"Loaded environment variables from {env_path}")

    # In debug mode, use asyncio.run() directly to avoid uvicorn's asyncio_run conflicts
    config = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=int(settings.port),
        log_level="info",
    )
    server = uvicorn.Server(config)
    asyncio.run(server.serve())


if __name__ == "__main__":
    import sys

    import uvicorn

    # Detect if running in debugger (PyCharm, VS Code, etc.)
    # Debuggers patch asyncio which conflicts with uvicorn's asyncio_run
    is_debugging = "pydevd" in sys.modules or (hasattr(sys, "gettrace") and sys.gettrace() is not None)

    if is_debugging:
        run_in_debug_mode(app)
    else:
        # Enable reload in normal mode
        uvicorn.run(
            app,
            host="0.0.0.0",
            port=int(settings.port),
            reload_excludes=["**/*.py"],
        )
