"""Error model มาตรฐาน (docs/05 §1) — ทุก error response ใช้รูปแบบเดียวกัน."""

from app.core.correlation import get_correlation_id


class AppError(Exception):
    status_code = 400
    code = "INTERNAL"

    def __init__(self, message: str, *, details: dict | None = None, code: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}
        if code:
            self.code = code

    def to_payload(self) -> dict:
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "details": self.details,
                "correlation_id": get_correlation_id(),
            }
        }


class AuthError(AppError):
    status_code = 401
    code = "AUTH_FAILED"


class ForbiddenError(AppError):
    status_code = 403
    code = "FORBIDDEN"


class NotFoundError(AppError):
    status_code = 404
    code = "NOT_FOUND"


class ValidationError(AppError):
    status_code = 422
    code = "VALIDATION_ERROR"


class RateLimitedError(AppError):
    status_code = 429
    code = "RATE_LIMITED"
