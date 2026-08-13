import httpx
import logging
import os
from typing import Optional
from urllib.parse import urlencode

from core.auth import IDTokenValidationError, google_oidc_configuration_issue, validate_id_token
from core.config import settings
from core.database import get_db
from dependencies.auth import get_current_user
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from models.auth import User
from schemas.auth import (
    FirebaseTokenExchangeRequest,
    GenericMessageResponse,
    GoogleTokenExchangeRequest,
    LoginRequest,
    PasswordResetConfirmRequest,
    PasswordResetRequest,
    PasswordResetRequestResponse,
    PlatformTokenExchangeRequest,
    RegisterRequest,
    TokenExchangeResponse,
    UserResponse,
)
from services.auth import AccountLinkRequiredError, AuthService
from services.mailer import send_password_reset_email, should_expose_password_reset_links
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/api/v1/auth", tags=["authentication"])
logger = logging.getLogger(__name__)


def auth_error(status_code: int, code: str, message: str) -> HTTPException:
    """Stable, safe error shape for auth API consumers."""
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


def get_dynamic_frontend_url(request: Request) -> str:
    origin = request.headers.get("origin")
    if origin:
        return origin.rstrip("/")
    frontend_url = getattr(settings, "frontend_url", "http://localhost:3000")
    return _local_patch(frontend_url).rstrip("/")


def build_frontend_error_redirect(request: Request, message: str) -> RedirectResponse:
    frontend_url = get_dynamic_frontend_url(request)
    fragment = urlencode({"msg": message})
    return RedirectResponse(
        url=f"{frontend_url}/auth/error?{fragment}",
        status_code=status.HTTP_302_FOUND,
    )


def _local_patch(url: str) -> str:
    """Patch URL for local development."""
    if os.getenv("LOCAL_PATCH", "").lower() not in ("true", "1"):
        return url

    patched_url = url.replace("https://", "http://").replace(":8000", ":3000")
    logger.debug("[get_dynamic_backend_url] patching URL from %s to %s", url, patched_url)
    return patched_url


def derive_name_from_email(email: str) -> str:
    return email.split("@", 1)[0] if email else ""


@router.get("/login")
async def redirect_to_login(request: Request):
    """Redirect browser to the frontend login page."""
    frontend_url = get_dynamic_frontend_url(request)
    query = request.url.query
    target = f"{frontend_url}/login"
    if query:
        target = f"{target}?{query}"
    return RedirectResponse(url=target, status_code=status.HTTP_302_FOUND)


@router.post("/login", response_model=TokenExchangeResponse)
async def login_user(payload: LoginRequest, db: AsyncSession = Depends(get_db)):
    """Authenticate user with email and password."""
    auth_service = AuthService(db)
    user, error_code = await auth_service.verify_user_credentials_with_reason(payload.email, payload.password)
    if not user:
        if error_code == "email_not_found":
            message = "No account was found with that email address."
        elif error_code == "password_incorrect":
            message = "The password you entered is incorrect."
        else:
            message = "We could not sign you in. Please try again."
        raise auth_error(status.HTTP_401_UNAUTHORIZED, error_code or "invalid_credentials", message)

    app_token, _, _ = await auth_service.issue_app_token(user=user)
    return TokenExchangeResponse(token=app_token)


@router.post("/register", response_model=TokenExchangeResponse)
async def register_user(payload: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """Create a new user account and return an app token."""
    auth_service = AuthService(db)
    try:
        user = await auth_service.create_user_with_password(
            payload.email,
            payload.name,
            payload.password,
            profile_data={
                "display_name": payload.name,
                "role": payload.role,
                "institution_type": payload.institution_type,
                "university_name": payload.university_name,
                "ur_student_code": payload.ur_student_code,
                "phone_number": payload.phone_number,
                "college_name": payload.college_name,
                "department_name": payload.department_name,
                "year_of_study": payload.year_of_study,
                "bio": payload.bio,
            },
        )
    except ValueError as exc:
        message = str(exc)
        code = "email_already_registered" if "already in use" in message.lower() else "registration_validation_failed"
        raise auth_error(status.HTTP_409_CONFLICT if code == "email_already_registered" else status.HTTP_400_BAD_REQUEST, code, message) from exc

    app_token, _, _ = await auth_service.issue_app_token(user=user)
    return TokenExchangeResponse(token=app_token)


@router.post("/password-reset/request", response_model=PasswordResetRequestResponse)
async def request_password_reset(payload: PasswordResetRequest, request: Request, db: AsyncSession = Depends(get_db)):
    """Create a password reset token and send a reset email when possible."""
    auth_service = AuthService(db)
    reset_result = await auth_service.create_password_reset_token(payload.email)
    debug_reset_url: Optional[str] = None

    if reset_result:
        user, raw_token, expires_at = reset_result
        frontend_url = get_dynamic_frontend_url(request)
        reset_url = f"{frontend_url}/reset-password?{urlencode({'token': raw_token})}"
        sent = await send_password_reset_email(user.email, reset_url, expires_at)
        if not sent and should_expose_password_reset_links():
            debug_reset_url = reset_url

    return PasswordResetRequestResponse(
        message="If an account matches that email, a password reset link has been prepared.",
        debug_reset_url=debug_reset_url,
    )


@router.post("/password-reset/confirm", response_model=GenericMessageResponse)
async def confirm_password_reset(payload: PasswordResetConfirmRequest, db: AsyncSession = Depends(get_db)):
    """Consume a password reset token and store a new password."""
    auth_service = AuthService(db)
    try:
        await auth_service.reset_password_with_token(payload.token, payload.password)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return GenericMessageResponse(message="Password updated successfully. You can now sign in.")


@router.post("/token/exchange", response_model=TokenExchangeResponse)
async def exchange_platform_token(
    payload: PlatformTokenExchangeRequest,
    db: AsyncSession = Depends(get_db),
):
    """Exchange Platform token for app token. Admin gets admin role, team members get user role."""
    logger.info("[token/exchange] Received platform token exchange request")

    verify_url = f"{settings.oidc_issuer_url}/platform/tokens/verify"
    logger.debug(f"[token/exchange] Verifying token with issuer: {verify_url}")

    try:
        async with httpx.AsyncClient() as client:
            verify_response = await client.post(
                verify_url,
                json={"platform_token": payload.platform_token},
                headers={"Content-Type": "application/json"},
            )
        logger.debug(f"[token/exchange] Issuer response status: {verify_response.status_code}")
    except httpx.HTTPError as exc:
        logger.error(f"[token/exchange] HTTP error verifying platform token: {exc}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Unable to verify platform token") from exc

    try:
        verify_body = verify_response.json()
        logger.debug(f"[token/exchange] Issuer response body: {verify_body}")
    except ValueError:
        logger.error(f"[token/exchange] Failed to parse issuer response as JSON: {verify_response.text}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Invalid response from platform token verification service",
        )

    if not isinstance(verify_body, dict):
        logger.error(f"[token/exchange] Unexpected response type: {type(verify_body)}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Unexpected response from platform token verification service",
        )

    if verify_response.status_code != status.HTTP_200_OK or not verify_body.get("success"):
        message = verify_body.get("message", "") if isinstance(verify_body, dict) else ""
        logger.warning(
            f"[token/exchange] Token verification failed: status={verify_response.status_code}, message={message}"
        )
        raise HTTPException(
            status_code=verify_response.status_code,
            detail=message or "Platform token verification failed",
        )

    payload_data = verify_body.get("data") or {}
    raw_user_id = payload_data.get("user_id")
    logger.info(f"[token/exchange] Token verified, platform_user_id={raw_user_id}, email={payload_data.get('email')}")

    if not raw_user_id:
        logger.error("[token/exchange] Platform token payload missing user_id")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Platform token payload missing user_id")

    platform_user_id = str(raw_user_id)
    is_admin = platform_user_id == str(settings.admin_user_id)
    role = "admin" if is_admin else "user"

    logger.info(f"[token/exchange] User verified: platform_user_id={platform_user_id}, role={role}")
    auth_service = AuthService(db)

    user_email = payload_data.get("email", "") or (getattr(settings, "admin_user_email", "") if is_admin else "")
    user_name = payload_data.get("name") or payload_data.get("username")
    if not user_name:
        user_name = derive_name_from_email(user_email)

    user = User(id=platform_user_id, email=user_email, name=user_name, role=role)
    logger.debug(
        f"[token/exchange] User object for token issuance: id={user.id}, email={user.email}, role={user.role}"
    )

    app_token, expires_at, _ = await auth_service.issue_app_token(user=user)
    logger.info(f"[token/exchange] Token issued successfully for user_id={user.id}, expires_at={expires_at}")

    return TokenExchangeResponse(
        token=app_token,
    )


@router.post("/firebase/exchange", response_model=TokenExchangeResponse)
async def exchange_firebase_token(
    payload: FirebaseTokenExchangeRequest,
    db: AsyncSession = Depends(get_db),
):
    """Exchange Firebase ID token for app token."""
    logger.info("[firebase/exchange] Received Firebase token exchange request")

    try:
        firebase_claims = await validate_firebase_id_token(payload.firebase_token)
    except IDTokenValidationError as exc:
        logger.warning("[firebase/exchange] Firebase token validation failed: type=%s detail=%s", exc.error_type, exc.message)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=exc.message) from exc

    firebase_uid = str(firebase_claims["sub"])
    email = firebase_claims.get("email", "") or ""
    name = firebase_claims.get("name") or derive_name_from_email(email)

    auth_service = AuthService(db)
    user = await auth_service.get_or_create_user(
        platform_sub=firebase_uid,
        email=email,
        name=name,
    )
    app_token, expires_at, _ = await auth_service.issue_app_token(user=user)

    logger.info("[firebase/exchange] Token issued successfully for user_id=%s, expires_at=%s", user.id, expires_at)
    return TokenExchangeResponse(token=app_token)


@router.post("/google", response_model=TokenExchangeResponse)
async def exchange_google_token(
    payload: GoogleTokenExchangeRequest,
    db: AsyncSession = Depends(get_db),
):
    """Validate a Google ID token, link it to the app user, and issue the existing app JWT."""
    logger.info("[google/exchange] Received Google token exchange request")

    config_issue = google_oidc_configuration_issue()
    if config_issue:
        logger.error("Google OIDC configuration incomplete: missing_or_invalid=%s", config_issue)
        raise auth_error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "google_configuration_incomplete",
            "Google Sign-In is temporarily unavailable because the server's Google authentication configuration is incomplete.",
        )

    try:
        google_claims = await validate_id_token(payload.credential)
    except IDTokenValidationError as exc:
        logger.warning("[google/exchange] Google token validation failed: type=%s detail=%s", exc.error_type, exc.message)
        raise auth_error(status.HTTP_401_UNAUTHORIZED, exc.error_type, "Google sign-in could not be verified. Please try again.") from exc

    google_sub = str(google_claims.get("sub") or "")
    email = (google_claims.get("email") or "").strip().lower()
    if not google_sub or not email:
        raise auth_error(status.HTTP_401_UNAUTHORIZED, "google_account_incomplete", "Google did not provide the account details needed to sign in.")

    auth_service = AuthService(db)
    try:
        user = await auth_service.get_or_create_user(
            platform_sub=google_sub,
            email=email,
            name=google_claims.get("name") or derive_name_from_email(email),
            google_sub=google_sub,
        )
    except AccountLinkRequiredError as exc:
        raise auth_error(status.HTTP_409_CONFLICT, "account_link_required", str(exc)) from exc
    app_token, expires_at, _ = await auth_service.issue_app_token(user=user)

    logger.info("[google/exchange] Token issued successfully for user_id=%s, expires_at=%s", user.id, expires_at)
    return TokenExchangeResponse(token=app_token)


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user: UserResponse = Depends(get_current_user)):
    """Get current user info."""
    return current_user


@router.get("/logout")
async def logout():
    """Logout user."""
    frontend_url = getattr(settings, "frontend_url", "http://localhost:3000")
    return {"redirect_url": frontend_url}
