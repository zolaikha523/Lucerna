"""Password hashing (PBKDF2-HMAC-SHA256, per-user salt) — format compatible with EvidenceQDA."""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

ITERATIONS = 240_000
MIN_LENGTH = 10


def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, ITERATIONS)
    return base64.b64encode(salt).decode() + ":" + base64.b64encode(dk).decode()


def verify_password(password: str, stored: str | None) -> bool:
    try:
        a, b = (stored or "").split(":", 1)
        salt, expected = base64.b64decode(a), base64.b64decode(b)
        actual = hashlib.pbkdf2_hmac("sha256", (password or "").encode("utf-8"), salt, ITERATIONS)
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False


def password_problems(password: str, username: str = "") -> list[str]:
    """Return human-readable reasons a password is too weak (empty list = acceptable)."""
    p = password or ""
    issues = []
    if len(p) < MIN_LENGTH:
        issues.append(f"Use at least {MIN_LENGTH} characters.")
    classes = sum([any(c.islower() for c in p), any(c.isupper() for c in p),
                   any(c.isdigit() for c in p), any(not c.isalnum() for c in p)])
    if classes < 3:
        issues.append("Mix at least three of: lowercase, uppercase, digits, symbols.")
    if username and username.lower() in p.lower():
        issues.append("Do not include your username in the password.")
    return issues
