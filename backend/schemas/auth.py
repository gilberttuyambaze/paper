from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field


class UserResponse(BaseModel):
    id: str  # Now a string UUID (platform sub)
    email: str
    name: Optional[str] = None
    role: str = "user"  # user/admin
    auth_provider: str = "email"
    has_password: bool = False
    last_login: Optional[datetime] = None
    permissions: list[str] = Field(default_factory=list)
    is_super_admin: bool = False

    class Config:
        from_attributes = True


class PlatformTokenExchangeRequest(BaseModel):
    """Request body for exchanging Platform token for app token."""

    platform_token: str


class FirebaseTokenExchangeRequest(BaseModel):
    """Request body for exchanging Firebase ID token for app token."""

    firebase_token: str


class GoogleTokenExchangeRequest(BaseModel):
    """Request body for exchanging a Google ID token for an application JWT."""

    credential: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)


class RegisterRequest(BaseModel):
    name: str
    email: EmailStr
    password: str = Field(min_length=6)
    role: str = "normal"
    institution_type: str
    university_name: Optional[str] = None
    ur_student_code: Optional[str] = None
    phone_number: Optional[str] = None
    college_name: Optional[str] = None
    department_name: Optional[str] = None
    institution_id: Optional[str] = None
    campus_id: Optional[str] = None
    college_id: Optional[str] = None
    school_id: Optional[str] = None
    academic_department_id: Optional[str] = None
    programme_id: Optional[str] = None
    programme_name_other: Optional[str] = Field(default=None, max_length=180)
    year_of_study: Optional[str] = None
    bio: Optional[str] = None


class TokenExchangeResponse(BaseModel):
    """Response body for issued application token."""

    token: str


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirmRequest(BaseModel):
    token: str = Field(min_length=16)
    password: str = Field(min_length=6)


class SetPasswordRequest(BaseModel):
    password: str = Field(min_length=6)


class GenericMessageResponse(BaseModel):
    message: str


class PasswordResetRequestResponse(GenericMessageResponse):
    debug_reset_url: Optional[str] = None
