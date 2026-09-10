import logging
import os
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Literal, Optional, Tuple
from uuid import uuid4

from core.auth import create_access_token, hash_password, verify_password
from core.config import settings
from core.database import db_manager
from models.auth import OIDCState, PasswordResetToken, User
from models.user_profiles import User_profiles
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

INSTITUTION_TYPES = {"ur_student", "other_university"}
UR_VERIFICATION_STATUSES = {"not_requested", "pending", "verified", "rejected"}
# This is the persistence allowlist, not the public self-registration allowlist.
# A Super Admin profile is created/synchronised during login and must therefore
# be accepted here even though it can never be selected during registration.
PROFILE_ROLES = {"normal", "verified_contributor", "cp", "lecturer", "content_manager", "admin", "super_admin"}
PUBLIC_REGISTRATION_ROLES = {"normal", "cp", "lecturer"}
REQUESTABLE_REGISTRATION_ROLES = {"cp", "lecturer"}
REQUESTABLE_ROLE_STATUSES = {"none", "pending", "approved", "rejected"}


class AccountLinkRequiredError(ValueError):
    """Raised when a Google identity matches an unlinked existing app account."""


def _admin_matches(platform_sub: str, email: str) -> bool:
    admin_user_id = getattr(settings, "admin_user_id", "") or ""
    admin_user_email = (getattr(settings, "admin_user_email", "") or "").strip().lower()
    return bool((admin_user_id and platform_sub == admin_user_id) or (admin_user_email and email.lower() == admin_user_email))


def role_for_identity(platform_sub: str, email: str) -> str:
    """Resolve configured elevated identities before issuing an app token."""
    super_admin_id = (os.getenv("SUPER_ADMIN_USER_ID", "") or "").strip()
    super_admin_email = (os.getenv("SUPER_ADMIN_USER_EMAIL", "") or "").strip().lower()
    if (super_admin_id and platform_sub == super_admin_id) or (super_admin_email and email.lower() == super_admin_email):
        return "super_admin"
    if _admin_matches(platform_sub, email):
        return "admin"
    return "user"


async def _ensure_admin_profile(db: AsyncSession, user: User) -> None:
    await ensure_user_profile_record(db, user)


def _clean_text(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _normalize_ur_student_code(value: Optional[str]) -> Optional[str]:
    cleaned = _clean_text(value)
    if not cleaned:
        return None
    return cleaned.replace(" ", "").upper()


def _default_display_name(user: User) -> str:
    return _clean_text(user.name) or user.email.split("@", 1)[0]


async def ensure_user_profile_record(
    db: AsyncSession,
    user: User,
    updates: Optional[Dict[str, Any]] = None,
) -> User_profiles:
    payload = updates or {}
    result = await db.execute(select(User_profiles).where(User_profiles.user_id == user.id))
    profile = result.scalar_one_or_none()
    verified_ur_locked = bool(
        profile
        and profile.ur_verification_status == "verified"
        and profile.ur_student_code
    )

    def pick_text(field: str, current: Optional[str]) -> Optional[str]:
        if field not in payload:
            return current
        return _clean_text(payload.get(field))

    display_name = pick_text("display_name", profile.display_name if profile else None) or _default_display_name(user)
    institution_type = pick_text("institution_type", profile.institution_type if profile else None)
    university_name = pick_text("university_name", profile.university_name if profile else None)
    ur_student_code = (
        _normalize_ur_student_code(payload.get("ur_student_code"))
        if "ur_student_code" in payload
        else profile.ur_student_code if profile else None
    )
    ur_verification_status = pick_text(
        "ur_verification_status",
        profile.ur_verification_status if profile else None,
    )
    profile_picture_key = pick_text("profile_picture_key", profile.profile_picture_key if profile else None)
    phone_number = pick_text("phone_number", profile.phone_number if profile else None)
    college_name = pick_text("college_name", profile.college_name if profile else None)
    department_name = pick_text("department_name", profile.department_name if profile else None)
    institution_id = pick_text("institution_id", profile.institution_id if profile else None)
    campus_id = pick_text("campus_id", profile.campus_id if profile else None)
    college_id = pick_text("college_id", profile.college_id if profile else None)
    school_id = pick_text("school_id", profile.school_id if profile else None)
    academic_department_id = pick_text("academic_department_id", profile.academic_department_id if profile else None)
    programme_id = pick_text("programme_id", profile.programme_id if profile else None)
    programme_name_other = pick_text("programme_name_other", profile.programme_name_other if profile else None)
    year_of_study = pick_text("year_of_study", profile.year_of_study if profile else None)
    bio = pick_text("bio", profile.bio if profile else None)
    requested_role = pick_text("requested_role", profile.requested_role if profile else None)
    requested_role_status = pick_text("requested_role_status", profile.requested_role_status if profile else None)
    requested_profile_role = pick_text("role", profile.role if profile else None)

    if verified_ur_locked:
        if "ur_student_code" in payload:
            requested_code = _normalize_ur_student_code(payload.get("ur_student_code"))
            if requested_code != profile.ur_student_code:
                raise ValueError("Verified UR student code cannot be changed")

        if "institution_type" in payload and _clean_text(payload.get("institution_type")) != profile.institution_type:
            raise ValueError("Institution type cannot be changed after UR verification")

        if "university_name" in payload:
            requested_university = _clean_text(payload.get("university_name")) or "University of Rwanda"
            current_university = profile.university_name or "University of Rwanda"
            if requested_university != current_university:
                raise ValueError("University name cannot be changed after UR verification")

    if institution_type and institution_type not in INSTITUTION_TYPES:
        raise ValueError("Institution type must be either 'ur_student' or 'other_university'")

    if institution_type is None:
        if ur_student_code or university_name == "University of Rwanda":
            institution_type = "ur_student"
        elif university_name:
            institution_type = "other_university"

    if institution_type == "ur_student":
        university_name = "University of Rwanda"
        if not ur_student_code:
            raise ValueError("UR student code is required for University of Rwanda verification")
        if "ur_verification_status" not in payload:
            was_verified = (
                profile is not None
                and profile.ur_verification_status == "verified"
                and profile.ur_student_code == ur_student_code
            )
            ur_verification_status = "verified" if was_verified else "pending"
    elif institution_type == "other_university":
        ur_student_code = None
        if not university_name:
            raise ValueError("University name is required when selecting another university")
        ur_verification_status = "not_requested"
    elif not ur_verification_status:
        ur_verification_status = "not_requested"

    if ur_verification_status and ur_verification_status not in UR_VERIFICATION_STATUSES:
        raise ValueError("Invalid UR verification status")

    role = requested_profile_role or (profile.role if profile and profile.role else "normal")
    if user.role == "super_admin":
        role = "super_admin"
    if role not in PROFILE_ROLES:
        raise ValueError("Invalid account role")
    if user.role == "admin":
        role = "admin"

    if requested_role and requested_role not in REQUESTABLE_REGISTRATION_ROLES:
        raise ValueError("Invalid requested role")
    if requested_role_status and requested_role_status not in REQUESTABLE_ROLE_STATUSES:
        raise ValueError("Invalid requested role status")
    if requested_role is None:
        requested_role_status = "none"
    elif requested_role_status is None:
        requested_role_status = "pending"
    if role in REQUESTABLE_REGISTRATION_ROLES:
        requested_role = role
        requested_role_status = "approved"

    trust_score = profile.trust_score if profile and profile.trust_score is not None else 0
    if role == "admin":
        trust_score = max(trust_score, 100)

    upload_count = profile.upload_count if profile and profile.upload_count is not None else 0
    download_count = profile.download_count if profile and profile.download_count is not None else 0
    account_status = profile.account_status if profile and profile.account_status else "active"
    suspension_reason = profile.suspension_reason if profile else None
    suspended_until = profile.suspended_until if profile else None

    if profile:
        profile.display_name = display_name
        profile.role = role
        profile.trust_score = trust_score
        profile.upload_count = upload_count
        profile.download_count = download_count
        profile.institution_type = institution_type
        profile.university_name = university_name
        profile.ur_student_code = ur_student_code
        profile.ur_verification_status = ur_verification_status or "not_requested"
        profile.profile_picture_key = profile_picture_key
        profile.phone_number = phone_number
        profile.college_name = college_name
        profile.department_name = department_name
        profile.institution_id = institution_id; profile.campus_id = campus_id; profile.college_id = college_id; profile.school_id = school_id; profile.academic_department_id = academic_department_id; profile.programme_id = programme_id
        profile.programme_name_other = programme_name_other
        profile.year_of_study = year_of_study
        profile.bio = bio
        profile.requested_role = requested_role
        profile.requested_role_status = requested_role_status
        profile.account_status = account_status
        profile.suspension_reason = suspension_reason
        profile.suspended_until = suspended_until
    else:
        profile = User_profiles(
            user_id=user.id,
            display_name=display_name,
            role=role,
            trust_score=trust_score,
            upload_count=upload_count,
            download_count=download_count,
            institution_type=institution_type,
            university_name=university_name,
            ur_student_code=ur_student_code,
            ur_verification_status=ur_verification_status or "not_requested",
            profile_picture_key=profile_picture_key,
            phone_number=phone_number,
            college_name=college_name,
            department_name=department_name,
            institution_id=institution_id, campus_id=campus_id, college_id=college_id, school_id=school_id, academic_department_id=academic_department_id, programme_id=programme_id,
            programme_name_other=programme_name_other,
            year_of_study=year_of_study,
            bio=bio,
            requested_role=requested_role,
            requested_role_status=requested_role_status,
            account_status=account_status,
            suspension_reason=suspension_reason,
            suspended_until=suspended_until,
            created_at=datetime.now(timezone.utc),
        )
        db.add(profile)

    user.name = display_name
    return profile


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _hash_reset_token(token: str) -> str:
    import hashlib

    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class AuthService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def find_user_by_email(self, email: str) -> Optional[User]:
        email = _normalize_email(email)
        result = await self.db.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def find_user_by_google_sub(self, google_sub: str) -> Optional[User]:
        result = await self.db.execute(select(User).where(User.google_sub == google_sub))
        return result.scalar_one_or_none()

    async def get_user_by_id(self, user_id: str) -> Optional[User]:
        return await self.db.get(User, user_id)

    def hash_password(self, password: str) -> str:
        if not password or len(password) < 6:
            raise ValueError("Password is too weak. Use at least 6 characters.")
        return hash_password(password)

    async def create_user_with_password(
        self,
        email: str,
        name: str,
        password: str,
        profile_data: Optional[Dict[str, Any]] = None,
    ) -> User:
        normalized_email = _normalize_email(email)
        requested_role = _clean_text((profile_data or {}).get("role"))
        if not password or len(password) < 6:
            raise ValueError("Password is too weak. Use at least 6 characters.")
        if requested_role and requested_role not in PUBLIC_REGISTRATION_ROLES:
            raise ValueError("Only normal, class representative, or lecturer roles can be chosen during registration")

        existing_user = await self.find_user_by_email(normalized_email)
        if existing_user:
            raise ValueError("This email is already in use. Try signing in instead.")

        password_hash = hash_password(password)
        user = User(
            id=str(uuid4()),
            email=normalized_email,
            name=name,
            password_hash=password_hash,
            last_login=datetime.now(timezone.utc),
        )
        self.db.add(user)

        resolved_role = role_for_identity(user.id, normalized_email)
        if resolved_role != "user":
            user.role = resolved_role

        profile_payload = dict(profile_data or {})
        if requested_role in REQUESTABLE_REGISTRATION_ROLES and user.role not in {"admin", "super_admin"}:
            profile_payload["role"] = "normal"
            profile_payload["requested_role"] = requested_role
            profile_payload["requested_role_status"] = "pending"
        else:
            profile_payload["requested_role"] = None
            profile_payload["requested_role_status"] = "none"

        await ensure_user_profile_record(self.db, user, profile_payload)
        await self.db.commit()
        await self.db.refresh(user)

        return user

    async def verify_user_credentials(self, email: str, password: str) -> Optional[User]:
        user, error_code = await self.verify_user_credentials_with_reason(email, password)
        if error_code:
            return None
        return user

    async def verify_user_credentials_with_reason(
        self, email: str, password: str
    ) -> Tuple[Optional[User], Optional[Literal["email_not_found", "password_incorrect"]]]:
        normalized_email = _normalize_email(email)
        result = await self.db.execute(select(User).where(User.email == normalized_email))
        user = result.scalar_one_or_none()
        if not user or not user.password_hash:
            return None, "email_not_found"
        if not verify_password(password, user.password_hash):
            return None, "password_incorrect"

        user.last_login = datetime.now(timezone.utc)

        resolved_role = role_for_identity(user.id, normalized_email)
        if resolved_role == "super_admin" or (resolved_role == "admin" and user.role != "super_admin"):
            user.role = resolved_role

        await ensure_user_profile_record(self.db, user)
        await self.db.commit()
        await self.db.refresh(user)

        return user, None

    async def create_password_reset_token(self, email: str) -> Optional[Tuple[User, str, datetime]]:
        normalized_email = _normalize_email(email)
        result = await self.db.execute(select(User).where(User.email == normalized_email))
        user = result.scalar_one_or_none()
        if not user:
            return None

        now = datetime.now(timezone.utc)
        await self.db.execute(
            delete(PasswordResetToken).where(
                (PasswordResetToken.user_id == user.id)
                | (PasswordResetToken.expires_at < now)
                | (PasswordResetToken.used_at.is_not(None))
            )
        )

        raw_token = secrets.token_urlsafe(32)
        expires_minutes = int(getattr(settings, "password_reset_token_ttl_minutes", 30) or 30)
        expires_at = now + timedelta(minutes=expires_minutes)
        reset_token = PasswordResetToken(
            user_id=user.id,
            token_hash=_hash_reset_token(raw_token),
            expires_at=expires_at,
        )
        self.db.add(reset_token)
        await self.db.commit()
        return user, raw_token, expires_at

    async def reset_password_with_token(self, token: str, new_password: str) -> User:
        if not new_password or len(new_password) < 6:
            raise ValueError("Password is too weak. Use at least 6 characters.")

        now = datetime.now(timezone.utc)
        result = await self.db.execute(
            select(PasswordResetToken).where(
                PasswordResetToken.token_hash == _hash_reset_token(token),
                PasswordResetToken.used_at.is_(None),
                PasswordResetToken.expires_at > now,
            )
        )
        reset_token = result.scalar_one_or_none()
        if not reset_token:
            raise ValueError("Password reset link is invalid or has expired")

        user = await self.db.get(User, reset_token.user_id)
        if not user:
            raise ValueError("Password reset link is invalid or has expired")

        user.password_hash = hash_password(new_password)
        user.last_login = now
        reset_token.used_at = now

        await self.db.execute(
            delete(PasswordResetToken).where(
                PasswordResetToken.user_id == user.id,
                PasswordResetToken.id != reset_token.id,
            )
        )
        await self.db.commit()
        await self.db.refresh(user)
        return user

    async def get_or_create_user(self, platform_sub: str, email: str, name: Optional[str] = None, google_sub: Optional[str] = None) -> User:
        """Get an existing app user or create one while preserving account linkage."""
        start_time = time.time()
        logger.debug(f"[DB_OP] Starting get_or_create_user - platform_sub: {platform_sub}, google_sub={google_sub}")

        normalized_email = _normalize_email(email)
        candidate_by_id = await self.db.get(User, platform_sub)
        candidate_by_google_sub = await self.find_user_by_google_sub(google_sub) if google_sub else None
        candidate_by_email = await self.find_user_by_email(normalized_email)
        user = candidate_by_google_sub or candidate_by_id

        # Do not treat control of an email address as permission to attach a new
        # Google identity to an existing password account. Account linking needs a
        # separately authenticated, explicit flow.
        if google_sub and candidate_by_email and candidate_by_email is not user:
            raise AccountLinkRequiredError("An account already exists for this email. Sign in with your password to link Google securely.")

        if user:
            if normalized_email and user.email != normalized_email:
                user.email = normalized_email
            if name and user.name != name:
                user.name = name
            if google_sub and user.google_sub != google_sub:
                raise AccountLinkRequiredError("This Google account is not linked to the existing application account.")
            if user.auth_provider in (None, ""):
                user.auth_provider = "email"
            user.last_login = datetime.now(timezone.utc)
        else:
            user = User(
                id=platform_sub,
                email=normalized_email,
                name=name,
                google_sub=google_sub,
                auth_provider="google" if google_sub else "email",
                last_login=datetime.now(timezone.utc),
            )
            self.db.add(user)

        resolved_role = role_for_identity(platform_sub, normalized_email)
        if resolved_role == "super_admin" or (resolved_role == "admin" and user.role != "super_admin"):
            user.role = resolved_role
        if google_sub:
            user.google_sub = google_sub
            user.auth_provider = "google"

        await ensure_user_profile_record(self.db, user)

        start_time_commit = time.time()
        logger.debug("[DB_OP] Starting user commit/refresh")
        await self.db.commit()
        await self.db.refresh(user)
        logger.debug(f"[DB_OP] User commit/refresh completed in {time.time() - start_time_commit:.4f}s")
        return user

    async def issue_app_token(
        self,
        user: User,
    ) -> Tuple[str, datetime, Dict[str, Any]]:
        """Generate application JWT token for the authenticated user."""
        try:
            expires_minutes = int(getattr(settings, "jwt_expire_minutes", 60))
        except (TypeError, ValueError):
            logger.warning("Invalid JWT_EXPIRE_MINUTES value; fallback to 60 minutes")
            expires_minutes = 60
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=expires_minutes)

        claims: Dict[str, Any] = {
            "sub": user.id,
            "email": user.email,
            "role": user.role,
        }

        if user.name:
            claims["name"] = user.name
        if user.last_login:
            claims["last_login"] = user.last_login.isoformat()
        token = create_access_token(claims, expires_minutes=expires_minutes)

        return token, expires_at, claims

    async def store_oidc_state(self, state: str, nonce: str, code_verifier: str):
        """Store OIDC state in database."""
        # Clean up expired states first
        await self.db.execute(delete(OIDCState).where(OIDCState.expires_at < datetime.now(timezone.utc)))

        expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)  # 10 minute expiry

        oidc_state = OIDCState(state=state, nonce=nonce, code_verifier=code_verifier, expires_at=expires_at)

        self.db.add(oidc_state)
        await self.db.commit()

    async def get_and_delete_oidc_state(self, state: str) -> Optional[dict]:
        """Get and delete OIDC state from database."""
        # Clean up expired states first
        await self.db.execute(delete(OIDCState).where(OIDCState.expires_at < datetime.now(timezone.utc)))

        # Find and validate state
        result = await self.db.execute(select(OIDCState).where(OIDCState.state == state))
        oidc_state = result.scalar_one_or_none()

        if not oidc_state:
            return None

        # Extract data before deleting
        state_data = {"nonce": oidc_state.nonce, "code_verifier": oidc_state.code_verifier}

        # Delete the used state (one-time use)
        await self.db.delete(oidc_state)
        await self.db.commit()

        return state_data


async def initialize_admin_user():
    """Initialize admin user if not exists"""
    if "URHUD_IGNORE_INIT_ADMIN" in os.environ:
        logger.info("Ignore initialize admin")
        return

    admin_user_id = getattr(settings, "admin_user_id", "")
    admin_user_email = getattr(settings, "admin_user_email", "")

    if not admin_user_id and not admin_user_email:
        logger.warning("Admin user ID or email not configured, skipping admin initialization")
        return

    async with db_manager.async_session_maker() as db:
        user = None
        if admin_user_id:
            result = await db.execute(select(User).where(User.id == admin_user_id))
            user = result.scalar_one_or_none()

        if user is None and admin_user_email:
            result = await db.execute(select(User).where(User.email == admin_user_email))
            user = result.scalar_one_or_none()

        if user:
            if user.role != "super_admin":
                user.role = "super_admin" if role_for_identity(user.id, user.email) == "super_admin" else "admin"
            if admin_user_email:
                user.email = admin_user_email
            await _ensure_admin_profile(db, user)
            await db.commit()
            logger.debug("Ensured admin privileges for user %s", user.id)
            return

        if admin_user_id and admin_user_email:
            configured_role = role_for_identity(admin_user_id, admin_user_email)
            admin_user = User(id=admin_user_id, email=admin_user_email, role=configured_role if configured_role != "user" else "admin")
            db.add(admin_user)
            await _ensure_admin_profile(db, admin_user)
            await db.commit()
            logger.debug("Created admin user: %s with email: %s", admin_user_id, admin_user_email)
            return

        logger.info("Admin bootstrap email is configured, but no matching user exists yet. First sign-in with that email will be promoted to admin.")
