"""RFC 6238 TOTP (no external dependency) and recovery codes."""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time


def totp(secret: str, for_time: float | None = None, digits: int = 6, period: int = 30) -> str:
    t = int(time.time() if for_time is None else for_time) // period
    key = base64.b32decode(secret.upper() + "=" * ((8 - len(secret) % 8) % 8), casefold=True)
    digest = hmac.new(key, t.to_bytes(8, "big"), hashlib.sha1).digest()
    off = digest[-1] & 15
    code = (int.from_bytes(digest[off:off + 4], "big") & 0x7FFFFFFF) % (10 ** digits)
    return str(code).zfill(digits)


def verify_totp(secret: str | None, code: str) -> bool:
    if not secret or not code:
        return False
    code = str(code).strip()
    return any(hmac.compare_digest(totp(secret, time.time() + i * 30), code) for i in (-1, 0, 1))


def new_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def new_recovery_codes(n: int = 8) -> list[str]:
    return [secrets.token_hex(4).upper() for _ in range(n)]


def hash_recovery_code(code: str) -> str:
    return hashlib.sha256(code.strip().upper().encode()).hexdigest()


def provisioning_uri(secret: str, username: str, issuer: str = "Lucerna") -> str:
    return f"otpauth://totp/{issuer}:{username}?secret={secret}&issuer={issuer}"
