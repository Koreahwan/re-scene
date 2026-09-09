"""
Reframe V7 Identity Crypto Module
Implements secure Argon2id password hashing and constant-time verification.
Uses official cryptography library primitives.
Zero Paid Model Calls.
"""
import os
import base64
import re
from typing import Tuple, Optional
from cryptography.hazmat.primitives.kdf.argon2 import Argon2id
from cryptography.exceptions import InvalidKey
import structlog
from src.reframe.shared.exceptions import ReframeException

logger = structlog.get_logger(__name__)

# Argon2id Parameter Configuration (RFC 9106 recommended defaults for interactive auth)
ARGON2_MEMORY_COST = 65536  # 64 MiB
ARGON2_ITERATIONS = 2
ARGON2_LANES = 4
ARGON2_KEY_LENGTH = 32
ARGON2_SALT_LENGTH = 16


from src.reframe.identity.validators import validate_password


def validate_password_strength(password: str) -> Tuple[bool, Optional[str]]:
    """Delegates to SSOT validate_password."""
    try:
        validate_password(password)
        return True, None
    except ReframeException as e:
        return False, e.message



def hash_password(password: str) -> str:
    """
    Derives Argon2id hash for password and returns formatted string.
    Format: $argon2id$v=19$m=65536,t=2,p=4$<salt_b64>$<hash_b64>
    """
    salt = os.urandom(ARGON2_SALT_LENGTH)
    kdf = Argon2id(
        salt=salt,
        length=ARGON2_KEY_LENGTH,
        iterations=ARGON2_ITERATIONS,
        lanes=ARGON2_LANES,
        memory_cost=ARGON2_MEMORY_COST,
        ad=None,
        secret=None
    )
    derived = kdf.derive(password.encode("utf-8"))
    salt_b64 = base64.b64encode(salt).decode("ascii")
    hash_b64 = base64.b64encode(derived).decode("ascii")
    return f"$argon2id$v=19$m={ARGON2_MEMORY_COST},t={ARGON2_ITERATIONS},p={ARGON2_LANES}${salt_b64}${hash_b64}"


def verify_password(password: str, formatted_hash: str) -> bool:
    """
    Verifies a plaintext password against an Argon2id formatted hash in constant time.
    """
    try:
        parts = formatted_hash.split("$")
        # Format: ["", "argon2id", "v=19", "m=65536,t=2,p=4", salt_b64, hash_b64]
        if len(parts) != 6 or parts[1] != "argon2id":
            logger.warning("invalid_password_hash_format")
            return False

        params_str = parts[3]
        params = dict(item.split("=") for item in params_str.split(","))
        memory_cost = int(params.get("m", ARGON2_MEMORY_COST))
        iterations = int(params.get("t", ARGON2_ITERATIONS))
        lanes = int(params.get("p", ARGON2_LANES))

        salt = base64.b64decode(parts[4].encode("ascii"))
        expected_hash = base64.b64decode(parts[5].encode("ascii"))

        kdf = Argon2id(
            salt=salt,
            length=len(expected_hash),
            iterations=iterations,
            lanes=lanes,
            memory_cost=memory_cost,
            ad=None,
            secret=None
        )
        kdf.verify(password.encode("utf-8"), expected_hash)
        return True
    except (InvalidKey, Exception) as e:
        logger.debug("password_verification_failed", error=str(e))
        return False
