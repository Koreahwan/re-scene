"""
Reframe V7 Identity Validators (Single Source of Truth)
Enforces consistent validation rules across endpoints, Pydantic schemas, and database operations:
- Handle SSOT (2-64 alphanumeric/underscore/hyphen characters)
- Email syntax and normalization
- Password complexity requirements
Zero Paid Model Calls.
"""
import re
from typing import Tuple, Optional
from fastapi import status
from src.reframe.shared.exceptions import ReframeException

HANDLE_REGEX = re.compile(r"^[a-zA-Z0-9_-]{2,64}$")
EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")


def validate_handle(handle: Optional[str], required: bool = False) -> Tuple[Optional[str], Optional[str]]:
    """
    Validates and normalizes a user handle.
    Rules:
    - String length between 2 and 64 characters
    - Characters allowed: a-z, A-Z, 0-9, _, -
    Returns:
    - (clean_handle, normalized_handle)
    Raises:
    - ReframeException(400, "AUTH_HANDLE_INVALID") if invalid
    """
    if not handle or not isinstance(handle, str) or not handle.strip():
        if required:
            raise ReframeException(
                status_code=status.HTTP_400_BAD_REQUEST,
                code="AUTH_HANDLE_INVALID",
                message="Handle is required and must be between 2 and 64 characters."
            )
        return None, None

    clean = handle.strip()
    if not HANDLE_REGEX.match(clean):
        raise ReframeException(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="AUTH_HANDLE_INVALID",
            message="Handle must be between 2 and 64 characters and contain only letters, numbers, underscores, and hyphens."
        )

    return clean, clean.lower()


def validate_email(email: Optional[str]) -> Tuple[str, str]:
    """
    Validates and normalizes an email address.
    Returns:
    - (clean_email, normalized_email)
    """
    if not email or not isinstance(email, str) or not email.strip():
        raise ReframeException(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="INVALID_REQUEST",
            message="Email address is required."
        )

    clean = email.strip()
    if not EMAIL_REGEX.match(clean) or len(clean) > 255:
        raise ReframeException(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="INVALID_REQUEST",
            message="Invalid email address format."
        )

    return clean, clean.lower()


def validate_password(password: Optional[str]) -> str:
    """
    Validates password length and complexity (Single Source of Truth):
    - 8 to 128 characters
    - At least one letter (a-z, A-Z)
    - At least one digit or special character
    """
    if not password or not isinstance(password, str):
        raise ReframeException(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="AUTH_PASSWORD_TOO_WEAK",
            message="Password is required."
        )

    if len(password) < 8 or len(password) > 128:
        raise ReframeException(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="AUTH_PASSWORD_TOO_WEAK",
            message="Password must be between 8 and 128 characters."
        )

    if not re.search(r"[a-zA-Z]", password):
        raise ReframeException(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="AUTH_PASSWORD_TOO_WEAK",
            message="Password must contain at least one letter."
        )

    if not re.search(r"[\d\W_]", password):
        raise ReframeException(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="AUTH_PASSWORD_TOO_WEAK",
            message="Password must contain at least one digit or special character."
        )

    return password

