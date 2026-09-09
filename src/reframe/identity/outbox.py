"""
Reframe V7 Identity Outbox & Atomic Challenge Store.
Implements secure, atomic Redis Lua scripts for:
1. One-time 6-digit email verification & password reset challenges.
2. Anti-enumeration and atomic resend cooldown.
3. Invalidation of prior active challenges and tickets upon resend.
4. Fail-closed production enforcement with 503 AUTH_CHALLENGE_STORE_UNAVAILABLE.
5. Three-step ticket lifecycle state machine (AVAILABLE -> RESERVED -> CONSUMED / RELEASED)
   for both Signup and Password-Reset idempotent sagas.
6. Unified key namespacing:
   - Verification: purpose = "verification" / "VERIFICATION", token = "verification"
   - Password Reset: purpose = "password_reset" / "PASSWORD_RESET", token = "password_reset"
Zero Paid Model Calls. Zero External Email API Calls.
"""
import os
import hmac
import hashlib
import json
import secrets
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List, Tuple
from fastapi import status
import structlog

from src.reframe.shared.config import settings
from src.reframe.shared.exceptions import ReframeException
from src.reframe.identity.delivery import get_email_delivery_backend

logger = structlog.get_logger(__name__)

PURPOSE_VERIFICATION = "verification"
PURPOSE_PASSWORD_RESET = "password_reset"


def _canonical_purpose(purpose: str) -> Tuple[str, str]:
    """
    Returns (purpose_enum, key_token) for canonical namespaces.
    verification -> ("VERIFICATION", "verification")
    password_reset -> ("PASSWORD_RESET", "password_reset")
    """
    p = purpose.strip().lower()
    if p in ("verification", "signup", "email_verification"):
        return "VERIFICATION", "verification"
    elif p in ("password_reset", "reset", "forgot_password"):
        return "PASSWORD_RESET", "password_reset"
    return p.upper(), p


def _hash_token(token: str) -> str:
    """Computes HMAC-SHA256 of code/ticket with server secret."""
    secret = getattr(settings, "AUTH_CODE_HMAC_SECRET", None) or settings.SECRET_KEY
    return hmac.new(
        secret.encode("utf-8"),
        token.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()



# -----------------------------------------------------------------------------
# Redis Lua Scripts for Atomicity & Strict Invariants
# -----------------------------------------------------------------------------

LUA_ISSUE_CHALLENGE = """
-- KEYS[1]: challenge_key
-- KEYS[2]: dev_outbox_key
-- KEYS[3]: active_challenge_key
-- KEYS[4]: active_ticket_key
-- KEYS[5]: cooldown_key
-- ARGV[1]: challenge_json
-- ARGV[2]: ttl_seconds
-- ARGV[3]: cooldown_json
-- ARGV[4]: cooldown_ttl_seconds
-- ARGV[5]: dev_msg_json

-- 1. Check if cooldown active
local in_cooldown = redis.call('GET', KEYS[5])
if in_cooldown then
    local ttl_rem = redis.call('TTL', KEYS[5])
    if ttl_rem <= 0 then ttl_rem = 1 end
    return -2
end

-- 2. Atomically acquire cooldown
redis.call('SETEX', KEYS[5], tonumber(ARGV[4]), ARGV[3])

-- 3. Invalidate prior active challenge
local old_challenge = redis.call('GET', KEYS[3])
if old_challenge and old_challenge ~= KEYS[1] then
    redis.call('DEL', old_challenge)
end

-- 4. Invalidate prior active ticket
local old_ticket = redis.call('GET', KEYS[4])
if old_ticket then
    redis.call('DEL', old_ticket, KEYS[4])
end

-- 5. Persist new challenge and active pointer
redis.call('SETEX', KEYS[1], tonumber(ARGV[2]), ARGV[1])
redis.call('SETEX', KEYS[3], tonumber(ARGV[2]), KEYS[1])

-- 6. Persist outbox message if configured
if ARGV[5] ~= '' then
    redis.call('SETEX', KEYS[2], tonumber(ARGV[2]), ARGV[5])
end

return 1
"""

LUA_VERIFY_CODE = """
-- KEYS[1]: challenge_key
-- KEYS[2]: dev_outbox_key
-- KEYS[3]: active_challenge_key
-- ARGV[1]: expected_code_hash
-- ARGV[2]: max_attempts
-- ARGV[3]: current_timestamp

local data = redis.call('GET', KEYS[1])
if not data then
    return 0
end
local obj = cjson.decode(data)
if tonumber(obj.expires_at_ts) < tonumber(ARGV[3]) then
    redis.call('DEL', KEYS[1], KEYS[2], KEYS[3])
    return 0
end

local attempts = tonumber(obj.attempts or 0) + 1
obj.attempts = attempts
local max_att = tonumber(ARGV[2])

if attempts > max_att then
    redis.call('DEL', KEYS[1], KEYS[2], KEYS[3])
    return -1
end

if obj.code_hash == ARGV[1] then
    redis.call('DEL', KEYS[1], KEYS[2], KEYS[3])
    return 1
else
    if attempts >= max_att then
        redis.call('DEL', KEYS[1], KEYS[2], KEYS[3])
        return -1
    else
        local ttl = redis.call('TTL', KEYS[1])
        if ttl > 0 then
            redis.call('SETEX', KEYS[1], ttl, cjson.encode(obj))
        end
        return 2
    end
end
"""

LUA_ISSUE_TICKET = """
-- KEYS[1]: ticket_key
-- KEYS[2]: active_ticket_key
-- ARGV[1]: ticket_json
-- ARGV[2]: ttl_seconds

local old_ticket = redis.call('GET', KEYS[2])
if old_ticket and old_ticket ~= KEYS[1] then
    redis.call('DEL', old_ticket)
end
redis.call('SETEX', KEYS[1], tonumber(ARGV[2]), ARGV[1])
redis.call('SETEX', KEYS[2], tonumber(ARGV[2]), KEYS[1])
return 1
"""

LUA_RESERVE_TICKET = """
-- KEYS[1]: ticket_key
-- ARGV[1]: email_normalized
-- ARGV[2]: operation_id
-- ARGV[3]: current_timestamp
-- ARGV[4]: required_purpose (SIGNUP or PASSWORD_RESET)

local data = redis.call('GET', KEYS[1])
if not data then
    return 0
end
local obj = cjson.decode(data)
if tonumber(obj.expires_at_ts) < tonumber(ARGV[3]) then
    redis.call('DEL', KEYS[1])
    return 0
end
if obj.email_normalized ~= ARGV[1] or obj.purpose ~= ARGV[4] then
    return 0
end
if obj.state ~= 'AVAILABLE' then
    return 0
end

obj.state = 'RESERVED'
obj.operation_id = ARGV[2]
obj.reserved_at_ts = tonumber(ARGV[3])
local ttl = redis.call('TTL', KEYS[1])
if ttl <= 0 then ttl = 600 end
redis.call('SETEX', KEYS[1], ttl, cjson.encode(obj))
return 1
"""

LUA_CONSUME_TICKET = """
-- KEYS[1]: ticket_key
-- KEYS[2]: active_ticket_key
-- ARGV[1]: email_normalized
-- ARGV[2]: operation_id

local data = redis.call('GET', KEYS[1])
if not data then return 0 end
local obj = cjson.decode(data)
if obj.operation_id == ARGV[2] and (obj.state == 'RESERVED' or obj.state == 'AVAILABLE') then
    redis.call('DEL', KEYS[1], KEYS[2])
    return 1
end
return 0
"""

LUA_RELEASE_TICKET = """
-- KEYS[1]: ticket_key
-- ARGV[1]: operation_id

local data = redis.call('GET', KEYS[1])
if not data then return 0 end
local obj = cjson.decode(data)
if obj.operation_id == ARGV[1] and obj.state == 'RESERVED' then
    obj.state = 'AVAILABLE'
    obj.operation_id = nil
    local ttl = redis.call('TTL', KEYS[1])
    if ttl <= 0 then ttl = 600 end
    redis.call('SETEX', KEYS[1], ttl, cjson.encode(obj))
    return 1
end
return 0
"""


class IdentityChallengeStore:
    def __init__(self, redis_client=None, allow_in_memory: Optional[bool] = None):
        self._redis_client = redis_client
        self._allow_in_memory = (
            allow_in_memory
            if allow_in_memory is not None
            else (settings.ENVIRONMENT != "production")
        )
        self._memory_store: Dict[str, Dict[str, Any]] = {}
        self._memory_expiries: Dict[str, float] = {}
        self._lock = threading.Lock()

    def _get_redis(self):
        if self._redis_client is False:
            if settings.ENVIRONMENT in ("production", "staging") or not self._allow_in_memory:
                raise ReframeException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    code="AUTH_CHALLENGE_STORE_UNAVAILABLE",
                    message="Authentication challenge store is temporarily unavailable."
                )
            return None

        if self._redis_client is not None:
            return self._redis_client

        try:
            import redis
            client = redis.from_url(
                settings.REDIS_URL,
                decode_responses=True,
                socket_connect_timeout=0.1,
                socket_timeout=0.1
            )
            client.ping()
            self._redis_client = client
            return client
        except Exception as e:
            self._redis_client = False
            if settings.ENVIRONMENT in ("production", "staging") or not self._allow_in_memory:
                logger.error("production_redis_challenge_store_unavailable", error=str(e))
                raise ReframeException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    code="AUTH_CHALLENGE_STORE_UNAVAILABLE",
                    message="Authentication challenge store is temporarily unavailable."
                )
            logger.warning("redis_unavailable_dev_memory_fallback", error=str(e))
            return None

    # -------------------------------------------------------------------------
    # Cooldown & Key Utilities
    # -------------------------------------------------------------------------
    def check_resend_cooldown(self, email: str, purpose: str = "verification") -> Optional[int]:
        _, p_token = _canonical_purpose(purpose)
        email_norm = email.strip().lower()
        key = f"auth:cooldown:{p_token}:{email_norm}"
        r = self._get_redis()
        if r:
            ttl = r.ttl(key)
            if ttl > 0:
                return ttl
            return None

        with self._lock:
            now = time.time()
            exp = self._memory_expiries.get(key, 0)
            if now < exp:
                return max(int(exp - now), 1)
            return None

    # -------------------------------------------------------------------------
    # Code Challenge Dispatch & Verification
    # -------------------------------------------------------------------------
    def create_code_challenge(self, email: str, purpose: str = "verification") -> str:
        """
        Atomically creates a 6-digit challenge, invalidates prior active
        challenges/tickets for this email + purpose, acquires cooldown,
        and dispatches via the configured delivery backend.
        """
        p_enum, p_token = _canonical_purpose(purpose)
        email_norm = email.strip().lower()

        raw_code = f"{secrets.randbelow(900000) + 100000}"
        code_hash = _hash_token(raw_code)
        ttl = settings.AUTH_CODE_TTL_SECONDS
        cooldown_ttl = settings.AUTH_CODE_RESEND_COOLDOWN_SECONDS
        now = time.time()
        expires_at_ts = now + ttl

        challenge_key = f"auth:challenge:{p_token}:{email_norm}"
        dev_outbox_key = f"auth:dev_outbox:{email_norm}:{p_token}"
        active_challenge_key = f"auth:active:challenge:{p_token}:{email_norm}"
        active_ticket_key = f"auth:active:ticket:{p_token}:{email_norm}"
        cooldown_key = f"auth:cooldown:{p_token}:{email_norm}"

        challenge_data = {
            "email_normalized": email_norm,
            "code_hash": code_hash,
            "purpose": p_enum,
            "created_at_ts": now,
            "expires_at_ts": expires_at_ts,
            "attempts": 0,
            "max_attempts": settings.AUTH_CODE_MAX_ATTEMPTS
        }

        dev_msg_json = ""
        if settings.AUTH_EMAIL_DELIVERY_MODE == "DEV_OUTBOX":
            dev_msg_json = json.dumps({
                "recipient": email_norm,
                "purpose": p_token,
                "raw_code": raw_code,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "expires_at": datetime.fromtimestamp(expires_at_ts, timezone.utc).isoformat()
            })

        # 1. Atomic Storage & Cooldown Acquisition
        r = self._get_redis()
        if r:
            res = r.eval(
                LUA_ISSUE_CHALLENGE,
                5,
                challenge_key,
                dev_outbox_key,
                active_challenge_key,
                active_ticket_key,
                cooldown_key,
                json.dumps(challenge_data),
                ttl,
                json.dumps({"expires_at_ts": now + cooldown_ttl}),
                cooldown_ttl,
                dev_msg_json
            )
            if res == -2:
                ttl_rem = r.ttl(cooldown_key)
                if ttl_rem <= 0: ttl_rem = cooldown_ttl
                raise ReframeException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    code="AUTH_RATE_LIMITED",
                    message=f"Please wait {ttl_rem} seconds before requesting a new code."
                )
        else:
            with self._lock:
                now_t = time.time()
                exp_c = self._memory_expiries.get(cooldown_key, 0)
                if now_t < exp_c:
                    rem = max(int(exp_c - now_t), 1)
                    raise ReframeException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        code="AUTH_RATE_LIMITED",
                        message=f"Please wait {rem} seconds before requesting a new code."
                    )

                # Acquire cooldown
                self._memory_store[cooldown_key] = {"expires_at_ts": now_t + cooldown_ttl}
                self._memory_expiries[cooldown_key] = now_t + cooldown_ttl

                # Invalidate prior challenge & active ticket
                old_c = self._memory_store.pop(active_challenge_key, None)
                if old_c and isinstance(old_c, str):
                    self._memory_store.pop(old_c, None)
                old_t = self._memory_store.pop(active_ticket_key, None)
                if old_t and isinstance(old_t, str):
                    self._memory_store.pop(old_t, None)

                self._memory_store[challenge_key] = challenge_data
                self._memory_expiries[challenge_key] = expires_at_ts

                self._memory_store[active_challenge_key] = challenge_key
                self._memory_expiries[active_challenge_key] = expires_at_ts

                if dev_msg_json:
                    self._memory_store[dev_outbox_key] = json.loads(dev_msg_json)
                    self._memory_expiries[dev_outbox_key] = expires_at_ts

        # 2. Dispatch delivery
        try:
            delivery = get_email_delivery_backend()
            delivery.send_code(email_norm, p_token, raw_code, ttl)
        except Exception as e:
            # If delivery fails, roll back challenge
            self.invalidate_challenge(email_norm, p_token)
            raise e

        return raw_code

    def invalidate_challenge(self, email: str, purpose: str = "verification") -> None:
        """Explicitly deletes active challenge and dev outbox message on error."""
        _, p_token = _canonical_purpose(purpose)
        email_norm = email.strip().lower()
        challenge_key = f"auth:challenge:{p_token}:{email_norm}"
        dev_outbox_key = f"auth:dev_outbox:{email_norm}:{p_token}"
        active_challenge_key = f"auth:active:challenge:{p_token}:{email_norm}"
        r = self._get_redis()
        if r:
            r.delete(challenge_key, dev_outbox_key, active_challenge_key)
        with self._lock:
            self._memory_store.pop(challenge_key, None)
            self._memory_store.pop(dev_outbox_key, None)
            self._memory_store.pop(active_challenge_key, None)

    def verify_and_consume_code(self, email: str, code: str, purpose: str = "verification") -> bool:
        """
        Atomically verifies the 6-digit code.
        Returns True on success, False if code is invalid/expired.
        Raises 400 AUTH_CODE_INVALID if attempt limit is reached.
        """
        _, p_token = _canonical_purpose(purpose)
        email_norm = email.strip().lower()
        expected_hash = _hash_token(code)
        now = time.time()

        challenge_key = f"auth:challenge:{p_token}:{email_norm}"
        dev_outbox_key = f"auth:dev_outbox:{email_norm}:{p_token}"
        active_challenge_key = f"auth:active:challenge:{p_token}:{email_norm}"

        r = self._get_redis()
        if r:
            res = r.eval(
                LUA_VERIFY_CODE,
                3,
                challenge_key,
                dev_outbox_key,
                active_challenge_key,
                expected_hash,
                settings.AUTH_CODE_MAX_ATTEMPTS,
                now
            )
            if res == 1:
                return True
            elif res == -1:
                raise ReframeException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    code="AUTH_CODE_INVALID",
                    message="Maximum verification attempts exceeded. Please request a new code."
                )
            else:
                return False

        with self._lock:
            data = self._memory_store.get(challenge_key)
            if not data or now > self._memory_expiries.get(challenge_key, 0):
                self._memory_store.pop(challenge_key, None)
                self._memory_store.pop(dev_outbox_key, None)
                self._memory_store.pop(active_challenge_key, None)
                return False

            attempts = data.get("attempts", 0) + 1
            data["attempts"] = attempts
            max_att = data.get("max_attempts", settings.AUTH_CODE_MAX_ATTEMPTS)

            if attempts > max_att:
                self._memory_store.pop(challenge_key, None)
                self._memory_store.pop(dev_outbox_key, None)
                self._memory_store.pop(active_challenge_key, None)
                raise ReframeException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    code="AUTH_CODE_INVALID",
                    message="Maximum verification attempts exceeded. Please request a new code."
                )

            if hmac.compare_digest(data["code_hash"], expected_hash):
                self._memory_store.pop(challenge_key, None)
                self._memory_store.pop(dev_outbox_key, None)
                self._memory_store.pop(active_challenge_key, None)
                return True
            else:
                if attempts >= max_att:
                    self._memory_store.pop(challenge_key, None)
                    self._memory_store.pop(dev_outbox_key, None)
                    self._memory_store.pop(active_challenge_key, None)
                    raise ReframeException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        code="AUTH_CODE_INVALID",
                        message="Maximum verification attempts exceeded. Please request a new code."
                    )
                return False

    # -------------------------------------------------------------------------
    # Ticket Issuance & Atomic Reservation / Consumption State Machine
    # -------------------------------------------------------------------------
    def issue_verification_ticket(self, email: str) -> str:
        """Issues an opaque, hashed one-time ticket for signup with state AVAILABLE."""
        email_norm = email.strip().lower()
        ticket = f"evt_{secrets.token_urlsafe(32)}"
        ticket_hash = _hash_token(ticket)
        ttl = settings.AUTH_TICKET_TTL_SECONDS
        now = time.time()

        ticket_key = f"auth:ticket:verification:{ticket_hash}"
        active_ticket_key = f"auth:active:ticket:verification:{email_norm}"

        ticket_data = {
            "email_normalized": email_norm,
            "purpose": "SIGNUP",
            "state": "AVAILABLE",
            "operation_id": None,
            "created_at_ts": now,
            "expires_at_ts": now + ttl
        }

        r = self._get_redis()
        if r:
            r.eval(
                LUA_ISSUE_TICKET,
                2,
                ticket_key,
                active_ticket_key,
                json.dumps(ticket_data),
                ttl
            )
            return ticket

        with self._lock:
            old_t = self._memory_store.get(active_ticket_key)
            if old_t and isinstance(old_t, str):
                self._memory_store.pop(old_t, None)
            self._memory_store[ticket_key] = ticket_data
            self._memory_expiries[ticket_key] = now + ttl
            self._memory_store[active_ticket_key] = ticket_key
            self._memory_expiries[active_ticket_key] = now + ttl

        return ticket

    def reserve_verification_ticket(self, ticket: str, email: str, operation_id: str) -> bool:
        """Atomically transitions signup ticket from AVAILABLE -> RESERVED with operation_id."""
        if not ticket or not email or not operation_id:
            return False

        email_norm = email.strip().lower()
        ticket_hash = _hash_token(ticket)
        ticket_key = f"auth:ticket:verification:{ticket_hash}"
        now = time.time()

        r = self._get_redis()
        if r:
            res = r.eval(
                LUA_RESERVE_TICKET,
                1,
                ticket_key,
                email_norm,
                operation_id,
                now,
                "SIGNUP"
            )
            return res == 1

        with self._lock:
            data = self._memory_store.get(ticket_key)
            if not data or now > self._memory_expiries.get(ticket_key, 0):
                self._memory_store.pop(ticket_key, None)
                return False
            if data.get("email_normalized") != email_norm or data.get("purpose") != "SIGNUP":
                return False
            if data.get("state") != "AVAILABLE":
                return False
            data["state"] = "RESERVED"
            data["operation_id"] = operation_id
            data["reserved_at_ts"] = now
            return True

    def confirm_consumed_verification_ticket(self, ticket: str, email: str, operation_id: str) -> bool:
        """Atomically burns the reserved signup ticket after successful DB transaction."""
        ticket_hash = _hash_token(ticket)
        ticket_key = f"auth:ticket:verification:{ticket_hash}"
        active_ticket_key = f"auth:active:ticket:verification:{email.strip().lower()}"

        r = self._get_redis()
        if r:
            res = r.eval(
                LUA_CONSUME_TICKET,
                2,
                ticket_key,
                active_ticket_key,
                email.strip().lower(),
                operation_id
            )
            return res == 1

        with self._lock:
            data = self._memory_store.get(ticket_key)
            if data and data.get("operation_id") == operation_id:
                self._memory_store.pop(ticket_key, None)
                self._memory_store.pop(active_ticket_key, None)
                return True
            return False

    def release_verification_ticket(self, ticket: str, email: str, operation_id: str) -> bool:
        """Rolls back signup ticket reservation safely from RESERVED -> AVAILABLE on DB error."""
        ticket_hash = _hash_token(ticket)
        ticket_key = f"auth:ticket:verification:{ticket_hash}"

        r = self._get_redis()
        if r:
            res = r.eval(
                LUA_RELEASE_TICKET,
                1,
                ticket_key,
                operation_id
            )
            return res == 1

        with self._lock:
            data = self._memory_store.get(ticket_key)
            if data and data.get("operation_id") == operation_id and data.get("state") == "RESERVED":
                data["state"] = "AVAILABLE"
                data["operation_id"] = None
                return True
            return False

    def consume_verification_ticket(self, ticket: str, email: str) -> bool:
        """Atomically reserves and consumes verification ticket (convenience method)."""
        op_id = f"op_direct_{secrets.token_urlsafe(16)}"
        if not self.reserve_verification_ticket(ticket, email, op_id):
            return False
        return self.confirm_consumed_verification_ticket(ticket, email, op_id)


    # -------------------------------------------------------------------------
    # Password Reset Ticket Lifecycle (AVAILABLE -> RESERVED -> CONSUMED)
    # -------------------------------------------------------------------------
    def issue_password_reset_ticket(self, email: str) -> str:
        """Issues an opaque, hashed one-time ticket for password reset with state AVAILABLE."""
        email_norm = email.strip().lower()
        ticket = f"prt_{secrets.token_urlsafe(32)}"
        ticket_hash = _hash_token(ticket)
        ttl = settings.AUTH_TICKET_TTL_SECONDS
        now = time.time()

        ticket_key = f"auth:ticket:password_reset:{ticket_hash}"
        active_ticket_key = f"auth:active:ticket:password_reset:{email_norm}"

        ticket_data = {
            "email_normalized": email_norm,
            "purpose": "PASSWORD_RESET",
            "state": "AVAILABLE",
            "operation_id": None,
            "created_at_ts": now,
            "expires_at_ts": now + ttl
        }

        r = self._get_redis()
        if r:
            r.eval(
                LUA_ISSUE_TICKET,
                2,
                ticket_key,
                active_ticket_key,
                json.dumps(ticket_data),
                ttl
            )
            return ticket

        with self._lock:
            old_t = self._memory_store.get(active_ticket_key)
            if old_t and isinstance(old_t, str):
                self._memory_store.pop(old_t, None)
            self._memory_store[ticket_key] = ticket_data
            self._memory_expiries[ticket_key] = now + ttl
            self._memory_store[active_ticket_key] = ticket_key
            self._memory_expiries[active_ticket_key] = now + ttl

        return ticket

    def reserve_password_reset_ticket(self, ticket: str, email: str, operation_id: str) -> bool:
        """Atomically transitions reset ticket from AVAILABLE -> RESERVED with operation_id."""
        if not ticket or not email or not operation_id:
            return False

        email_norm = email.strip().lower()
        ticket_hash = _hash_token(ticket)
        ticket_key = f"auth:ticket:password_reset:{ticket_hash}"
        now = time.time()

        r = self._get_redis()
        if r:
            res = r.eval(
                LUA_RESERVE_TICKET,
                1,
                ticket_key,
                email_norm,
                operation_id,
                now,
                "PASSWORD_RESET"
            )
            return res == 1

        with self._lock:
            data = self._memory_store.get(ticket_key)
            if not data or now > self._memory_expiries.get(ticket_key, 0):
                self._memory_store.pop(ticket_key, None)
                return False
            if data.get("email_normalized") != email_norm or data.get("purpose") != "PASSWORD_RESET":
                return False
            if data.get("state") != "AVAILABLE":
                return False
            data["state"] = "RESERVED"
            data["operation_id"] = operation_id
            data["reserved_at_ts"] = now
            return True

    def confirm_consumed_password_reset_ticket(self, ticket: str, email: str, operation_id: str) -> bool:
        """Atomically burns the reserved reset ticket after successful DB transaction."""
        ticket_hash = _hash_token(ticket)
        ticket_key = f"auth:ticket:password_reset:{ticket_hash}"
        active_ticket_key = f"auth:active:ticket:password_reset:{email.strip().lower()}"

        r = self._get_redis()
        if r:
            res = r.eval(
                LUA_CONSUME_TICKET,
                2,
                ticket_key,
                active_ticket_key,
                email.strip().lower(),
                operation_id
            )
            return res == 1

        with self._lock:
            data = self._memory_store.get(ticket_key)
            if data and data.get("operation_id") == operation_id:
                self._memory_store.pop(ticket_key, None)
                self._memory_store.pop(active_ticket_key, None)
                return True
            return False

    def release_password_reset_ticket(self, ticket: str, email: str, operation_id: str) -> bool:
        """Rolls back reset ticket reservation safely from RESERVED -> AVAILABLE on DB error."""
        ticket_hash = _hash_token(ticket)
        ticket_key = f"auth:ticket:password_reset:{ticket_hash}"

        r = self._get_redis()
        if r:
            res = r.eval(
                LUA_RELEASE_TICKET,
                1,
                ticket_key,
                operation_id
            )
            return res == 1

        with self._lock:
            data = self._memory_store.get(ticket_key)
            if data and data.get("operation_id") == operation_id and data.get("state") == "RESERVED":
                data["state"] = "AVAILABLE"
                data["operation_id"] = None
                return True
            return False

    def consume_password_reset_ticket(self, ticket: str, email: str) -> bool:
        """Helper for immediate consume (tests/legacy)."""
        op_id = uuid.uuid4().hex
        if self.reserve_password_reset_ticket(ticket, email, op_id):
            return self.confirm_consumed_password_reset_ticket(ticket, email, op_id)
        return False

    # -------------------------------------------------------------------------
    # Dev Outbox Inspector (Dev/Test Loopback Only)
    # -------------------------------------------------------------------------
    def get_dev_outbox_messages(self) -> List[Dict[str, Any]]:
        """Returns active dev outbox entries."""
        if settings.AUTH_EMAIL_DELIVERY_MODE != "DEV_OUTBOX":
            return []

        results = []
        r = self._get_redis()
        if r:
            try:
                keys = r.keys("auth:dev_outbox:*")
                for k in keys:
                    data = r.get(k)
                    if data:
                        results.append(json.loads(data))
                return results
            except Exception:
                pass

        with self._lock:
            now = time.time()
            for k, v in list(self._memory_store.items()):
                if k.startswith("auth:dev_outbox:"):
                    if now <= self._memory_expiries.get(k, 0):
                        results.append(v)
                    else:
                        self._memory_store.pop(k, None)
        return results

    def clear(self) -> None:
        """Clears all keys in the store (for test isolation)."""
        r = self._get_redis()
        if r:
            try:
                keys = r.keys("auth:*")
                if keys:
                    r.delete(*keys)
            except Exception:
                pass
        with self._lock:
            self._memory_store.clear()
            self._memory_expiries.clear()


challenge_store = IdentityChallengeStore()
outbox_service = challenge_store
