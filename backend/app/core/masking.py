"""Sensitive data masking สำหรับ log/audit (FR-SE-02) — ห้าม secret รั่วลง log."""

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
