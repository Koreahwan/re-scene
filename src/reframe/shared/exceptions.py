"""
Reframe V7 Standard Error Codes & Application Exceptions
"""
from typing import Any, Dict, Optional
from fastapi import HTTPException, status


class ReframeErrorCodes:
    AUTH_REQUIRED = "AUTH_REQUIRED"
    FORBIDDEN = "FORBIDDEN"
    NOT_FOUND = "NOT_FOUND"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    IDEMPOTENCY_CONFLICT = "IDEMPOTENCY_CONFLICT"
    VERSION_CONFLICT = "VERSION_CONFLICT"
    SPOILER_LOCKED = "SPOILER_LOCKED"
    SPOILER_SCOPE_INVALID = "SPOILER_SCOPE_INVALID"
    RUN_NOT_READY = "RUN_NOT_READY"
    MCP_UNAVAILABLE = "MCP_UNAVAILABLE"
    GEMINI_UNAVAILABLE = "GEMINI_UNAVAILABLE"
    BUDGET_EXCEEDED = "BUDGET_EXCEEDED"
    RATE_LIMITED = "RATE_LIMITED"
    DATASET_NOT_READY = "DATASET_NOT_READY"
    EVIDENCE_SUPERSEDED = "EVIDENCE_SUPERSEDED"
    PROOF_INVALID = "PROOF_INVALID"
    CONTENT_REMOVED = "CONTENT_REMOVED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class ReframeException(HTTPException):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None
    ):
        super().__init__(
            status_code=status_code,
            detail={
                "code": code,
                "message": message,
                "details": details or {}
            },
            headers=headers
        )
        self.code = code
        self.message = message
        self.details = details or {}


class SpoilerLockedException(ReframeException):
    def __init__(self, message: str = "Content is spoiler-locked for current viewer context", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            code=ReframeErrorCodes.SPOILER_LOCKED,
            message=message,
            details=details
        )


class IdempotencyConflictException(ReframeException):
    def __init__(self, message: str = "Idempotency key provided with different request payload", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            code=ReframeErrorCodes.IDEMPOTENCY_CONFLICT,
            message=message,
            details=details
        )


class BudgetExceededException(ReframeException):
    def __init__(self, message: str = "Cost or token budget limit exceeded", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            code=ReframeErrorCodes.BUDGET_EXCEEDED,
            message=message,
            details=details
        )
