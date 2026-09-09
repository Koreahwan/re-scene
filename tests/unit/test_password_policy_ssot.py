"""
Unit tests for Password Policy SSOT.
Verifies exact requirements:
- 8 to 128 characters
- At least one letter
- At least one digit or special character
- Exact test assertions:
  aaaaaaaa -> rejected
  12345678 -> rejected
  short1!  -> rejected (< 8 chars)
  Password123! -> accepted
"""
import pytest
from src.reframe.identity.validators import validate_password
from src.reframe.identity.crypto import validate_password_strength
from src.reframe.shared.exceptions import ReframeException


def test_password_policy_ssot_exact_matrix():
    # 1. 'aaaaaaaa' (no digit or special character) -> Rejected
    with pytest.raises(ReframeException) as exc1:
        validate_password("aaaaaaaa")
    assert exc1.value.code == "AUTH_PASSWORD_TOO_WEAK"

    is_valid, msg = validate_password_strength("aaaaaaaa")
    assert is_valid is False

    # 2. '12345678' (no letter) -> Rejected
    with pytest.raises(ReframeException) as exc2:
        validate_password("12345678")
    assert exc2.value.code == "AUTH_PASSWORD_TOO_WEAK"

    is_valid, msg = validate_password_strength("12345678")
    assert is_valid is False

    # 3. 'short1!' (< 8 characters) -> Rejected
    with pytest.raises(ReframeException) as exc3:
        validate_password("short1!")
    assert exc3.value.code == "AUTH_PASSWORD_TOO_WEAK"

    is_valid, msg = validate_password_strength("short1!")
    assert is_valid is False

    # 4. 'Password123!' (meets length, letters, digits, and special char) -> Accepted
    assert validate_password("Password123!") == "Password123!"

    is_valid, msg = validate_password_strength("Password123!")
    assert is_valid is True
    assert msg is None
