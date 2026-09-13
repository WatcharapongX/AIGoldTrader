import re

_MASKED = "***MASKED***"
_SENSITIVE_KEY_PARTS = (
    "password",
    "secret",
    "token",
    "api_key",
    "apikey",
    "credentials",
    "authorization",
    "cookie",
    "private_key",
)

_BEARER_PATTERN = re.compile(r"(?i)(bearer\s+)([A-Za-z0-9_\-\.]+)")
_AUTH_HEADER_PATTERN = re.compile(r"(?i)(authorization\s*[:=]\s*(?:bearer\s+)?)([^\s,;'\"]+)")
_API_KEY_PATTERN = re.compile(
    r"(?i)((?:api[-_]?key|apikey|secret[-_]?key|access[-_]?token|auth[-_]?token|token)\s*[:=]\s*)([^\s,;'\"]+)"
)
_GENERIC_KEY_PATTERN = re.compile(r"(?i)(sk-[A-Za-z0-9_\-]{8,}|AIza[A-Za-z0-9_\-]{10,})")


def _is_sensitive(key: str) -> bool:
    lowered = key.lower()
    return any(part in lowered for part in _SENSITIVE_KEY_PARTS)


def mask_payload(payload: dict | None) -> dict | None:
    """คืน dict ใหม่โดยแทนค่าของทุก key ที่ sensitive ด้วย ***MASKED*** (recursive)."""
    if payload is None:
        return None
    masked: dict = {}
    for key, value in payload.items():
        if _is_sensitive(str(key)):
            masked[key] = _MASKED
        elif isinstance(value, dict):
            masked[key] = mask_payload(value)
        elif isinstance(value, list):
            masked[key] = [mask_payload(v) if isinstance(v, dict) else v for v in value]
        else:
            masked[key] = value
    return masked


def mask_secret_text(
    text: str, extra_secrets: list[str] | set[str] | tuple[str, ...] | None = None
) -> str:
    """Mask credentials, tokens, bearer headers, and known secrets from strings/exceptions."""
    if not text:
        return text
    masked = text
    if extra_secrets:
        for secret in extra_secrets:
            if secret and len(secret) >= 4:
                masked = masked.replace(secret, _MASKED)
    masked = _AUTH_HEADER_PATTERN.sub(rf"\g<1>{_MASKED}", masked)
    masked = _BEARER_PATTERN.sub(rf"\g<1>{_MASKED}", masked)
    masked = _API_KEY_PATTERN.sub(rf"\g<1>{_MASKED}", masked)
    masked = _GENERIC_KEY_PATTERN.sub(_MASKED, masked)
    return masked

