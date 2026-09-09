"""
Reframe V7 Identity & User DTO Schemas
"""
import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class ProfileDTO(BaseModel):
    display_name: str
    bio: Optional[str] = None
    avatar_url: Optional[str] = None
    locale: str = "en"
    fan_depth: str = "REGULAR"


class SpoilerPreferencesDTO(BaseModel):
    default_mode: str = "STRICT"  # STRICT, ASK, ALL
    mask_titles: bool = True
    mask_thumbnails: bool = True
    mask_comments: bool = True


class WatchProgressDTO(BaseModel):
    work_id: str
    edition_id: str
    state: str  # NOT_STARTED, WATCHING, COMPLETED, ALL_SPOILERS_ALLOWED
    progress_ms: int
    completed_reveal_ids: List[str] = Field(default_factory=list)
    updated_at: Optional[datetime] = None


class UserMeResponse(BaseModel):
    id: Optional[uuid.UUID] = None
    display_name: str
    role: str
    fan_depth: str
    spoiler_preferences: SpoilerPreferencesDTO


class UpdateWatchProgressRequest(BaseModel):
    edition_id: str
    state: str
    progress_ms: int
    completed_reveal_ids: List[str] = Field(default_factory=list)


class UpdateSpoilerPreferencesRequest(BaseModel):
    default_mode: str = "STRICT"
    mask_titles: bool = True
    mask_thumbnails: bool = True
    mask_comments: bool = True


class DevLoginRequest(BaseModel):
    email: str
    display_name: Optional[str] = None


class SignupRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=8, max_length=128)
    email_verification_ticket: str = Field(min_length=10, max_length=255)
    display_name: Optional[str] = Field(default=None, max_length=100)
    handle: Optional[str] = Field(default=None, max_length=64)
    locale: str = Field(default="en", max_length=10)


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=128)


class AuthUserDTO(BaseModel):
    user_id: str
    email: str
    display_name: str
    handle: Optional[str] = None
    role: str
    fan_depth: str = "REGULAR"
    csrf_token: str


class CsrfResponseDTO(BaseModel):
    csrf_token: str


class EmailVerificationRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)


class EmailVerificationConfirmRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    code: str = Field(min_length=4, max_length=16)


class PasswordResetRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)


class PasswordResetVerifyRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    code: str = Field(min_length=4, max_length=16)


class PasswordResetCompleteRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password_reset_ticket: str = Field(min_length=10, max_length=255)
    new_password: str = Field(min_length=8, max_length=128)


class HandleAvailabilityResponseDTO(BaseModel):
    handle: str
    available: bool

