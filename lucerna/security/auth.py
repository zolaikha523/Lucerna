"""Authentication: accounts, login throttling, sessions with expiry/revocation, MFA lifecycle."""
from __future__ import annotations

import secrets
import time

from .. import db
from ..config import settings
from . import audit, mfa, passwords
from .rbac import CurrentUser


class AuthError(Exception):
    pass


def user_count() -> int:
    return db.query_one("SELECT COUNT(*) n FROM users")["n"]


def create_user(username: str, password: str, *, full_name: str = "", email: str = "",
                system_role: str = "user", must_change: bool = False, created_by: str | None = None) -> int:
    username = (username or "").strip()
    if not username or len(username) > 64 or not all(c.isalnum() or c in "._-@" for c in username):
        raise AuthError("Username must be 1–64 characters: letters, digits, . _ - @")
    problems = passwords.password_problems(password, username)
    if problems:
        raise AuthError(" ".join(problems))
    if db.query_one("SELECT 1 FROM users WHERE lower(username)=lower(?)", (username,)):
        raise AuthError("That username already exists.")
    uid = db.execute(
        "INSERT INTO users(username, password_hash, full_name, email, system_role, password_changed_at, must_change_password)"
        " VALUES(?,?,?,?,?,?,?)",
        (username, passwords.hash_password(password), full_name, email, system_role, time.time(), int(must_change)))
    audit.log(created_by or username, "USER_CREATED", f"user #{uid} role={system_role}", object_type="user", object_id=uid)
    return uid


def get_user(username: str) -> dict | None:
    return db.query_one("SELECT * FROM users WHERE lower(username)=lower(?) AND active=1", ((username or "").strip(),))


def get_user_by_id(uid: int) -> dict | None:
    return db.query_one("SELECT * FROM users WHERE id=?", (uid,))


def to_current(u: dict) -> CurrentUser:
    return CurrentUser(id=u["id"], username=u["username"], system_role=u.get("system_role") or "user",
                       full_name=u.get("full_name"))


def _record_attempt(username: str, success: bool) -> None:
    db.execute("INSERT INTO login_attempts(username, ts, success) VALUES(?,?,?)", (username.lower(), time.time(), int(success)))


def check_password_login(username: str, password: str) -> dict:
    """Step 1 of login. Returns the user row. Raises AuthError (generic message) on failure.
    Accounts lock for LUCERNA_LOGIN_LOCK_MINUTES after LUCERNA_LOGIN_MAX_FAILURES consecutive failures."""
    s = settings()
    u = get_user(username)
    if u and (u.get("locked_until") or 0) > time.time():
        mins = int(((u["locked_until"] - time.time()) // 60) + 1)
        audit.log(username, "LOGIN_BLOCKED_LOCKED", "account temporarily locked", "WARNING")
        raise AuthError(f"Too many failed attempts. Try again in about {mins} minute(s) or ask an administrator.")
    if not u or not passwords.verify_password(password, u["password_hash"]):
        _record_attempt(username or "", False)
        if u:
            fails = (u.get("failed_logins") or 0) + 1
            locked = time.time() + s.login_lock_minutes * 60 if fails >= s.login_max_failures else 0
            db.execute("UPDATE users SET failed_logins=?, locked_until=? WHERE id=?", (fails if not locked else 0, locked, u["id"]))
            if locked:
                audit.log(u["username"], "ACCOUNT_LOCKED", f"{fails} consecutive failures", "HIGH")
        audit.log(username, "LOGIN_FAILED", "invalid credentials", "WARNING")
        raise AuthError("Invalid username or password.")
    return u


def complete_login(u: dict, *, device_label: str = "Browser session", user_agent: str = "", ip: str = "local") -> str:
    db.execute("UPDATE users SET failed_logins=0, locked_until=0 WHERE id=?", (u["id"],))
    _record_attempt(u["username"], True)
    sid = secrets.token_urlsafe(32)
    now = time.time()
    db.execute("INSERT INTO sessions(id, username, device_label, user_agent, ip, created_at, last_seen, revoked, expires_at, user_id)"
               " VALUES(?,?,?,?,?,?,?,0,?,?)",
               (sid, u["username"], device_label, (user_agent or "")[:300], ip, now, now,
                now + settings().session_hours * 3600, u["id"]))
    audit.log(u["username"], "LOGIN", "successful sign-in")
    return sid


def validate_session(sid: str | None) -> CurrentUser | None:
    """Return the user for a live session; None if missing, revoked, expired, or user disabled."""
    if not sid:
        return None
    s = db.query_one("SELECT * FROM sessions WHERE id=?", (sid,))
    if not s or s["revoked"] or (s.get("expires_at") and s["expires_at"] < time.time()):
        return None
    u = db.query_one("SELECT * FROM users WHERE id=? AND active=1", (s["user_id"],)) if s.get("user_id") else get_user(s["username"])
    if not u:
        return None
    db.execute("UPDATE sessions SET last_seen=? WHERE id=?", (time.time(), sid))
    return to_current(u)


def logout(sid: str, username: str) -> None:
    db.execute("UPDATE sessions SET revoked=1 WHERE id=?", (sid,))
    audit.log(username, "LOGOUT", "signed out")


def list_sessions(user_id: int) -> list[dict]:
    return db.query("SELECT id, device_label, ip, created_at, last_seen, expires_at, revoked FROM sessions WHERE user_id=? ORDER BY last_seen DESC", (user_id,))


def revoke_session(sid: str, user_id: int, actor: str) -> None:
    db.execute("UPDATE sessions SET revoked=1 WHERE id=? AND user_id=?", (sid, user_id))
    audit.log(actor, "SESSION_REVOKED", "session revoked", "WARNING", object_type="session")


def revoke_all_sessions(user_id: int, actor: str, except_sid: str | None = None) -> None:
    db.execute("UPDATE sessions SET revoked=1 WHERE user_id=? AND id<>?", (user_id, except_sid or ""))
    audit.log(actor, "SESSIONS_REVOKED_ALL", f"user #{user_id}", "WARNING")


def change_password(user_id: int, old: str, new: str) -> None:
    u = get_user_by_id(user_id)
    if not u or not passwords.verify_password(old, u["password_hash"]):
        raise AuthError("Current password is incorrect.")
    problems = passwords.password_problems(new, u["username"])
    if problems:
        raise AuthError(" ".join(problems))
    db.execute("UPDATE users SET password_hash=?, password_changed_at=?, must_change_password=0 WHERE id=?",
               (passwords.hash_password(new), time.time(), user_id))
    audit.log(u["username"], "PASSWORD_CHANGED", "password changed")


def admin_reset_password(target_id: int, temp_password: str, actor: str) -> None:
    """Administrator-initiated reset (no email infrastructure is assumed). Forces a change at next sign-in
    and revokes the user's existing sessions."""
    u = get_user_by_id(target_id)
    if not u:
        raise AuthError("User not found.")
    problems = passwords.password_problems(temp_password, u["username"])
    if problems:
        raise AuthError(" ".join(problems))
    db.execute("UPDATE users SET password_hash=?, must_change_password=1, failed_logins=0, locked_until=0 WHERE id=?",
               (passwords.hash_password(temp_password), target_id))
    revoke_all_sessions(target_id, actor)
    audit.log(actor, "PASSWORD_RESET_BY_ADMIN", f"user #{target_id}", "WARNING", object_type="user", object_id=target_id)


def set_active(target_id: int, active: bool, actor: str) -> None:
    db.execute("UPDATE users SET active=? WHERE id=?", (int(active), target_id))
    if not active:
        revoke_all_sessions(target_id, actor)
    audit.log(actor, "USER_ACTIVATED" if active else "USER_DEACTIVATED", f"user #{target_id}", "WARNING")


# ---- MFA lifecycle: the secret is stored only after the user proves they can generate codes ----

def begin_mfa_enrolment() -> tuple[str, list[str]]:
    return mfa.new_secret(), mfa.new_recovery_codes()


def confirm_mfa_enrolment(user_id: int, secret: str, recovery_codes: list[str], code: str) -> None:
    if not mfa.verify_totp(secret, code):
        raise AuthError("That code did not verify. Check your authenticator app's clock and try again.")
    db.execute("UPDATE users SET mfa_secret=?, recovery_codes=? WHERE id=?",
               (secret, db.dumps([mfa.hash_recovery_code(c) for c in recovery_codes]), user_id))
    u = get_user_by_id(user_id)
    audit.log(u["username"], "MFA_ENABLED", "MFA enrolment confirmed")


def disable_mfa(user_id: int, password: str) -> None:
    u = get_user_by_id(user_id)
    if not u or not passwords.verify_password(password, u["password_hash"]):
        raise AuthError("Password is required to disable MFA.")
    db.execute("UPDATE users SET mfa_secret=NULL, recovery_codes=NULL WHERE id=?", (user_id,))
    audit.log(u["username"], "MFA_DISABLED", "MFA disabled by account owner", "HIGH")


def verify_second_factor(u: dict, code: str) -> bool:
    if mfa.verify_totp(u.get("mfa_secret"), code):
        return True
    stored = db.loads(u.get("recovery_codes"), []) or []
    h = mfa.hash_recovery_code(code or "")
    # Legacy EvidenceQDA stored recovery codes in plain text; accept and consume either form once.
    for item in list(stored):
        if item == h or item == (code or "").strip().upper():
            stored.remove(item)
            db.execute("UPDATE users SET recovery_codes=? WHERE id=?", (db.dumps(stored), u["id"]))
            audit.log(u["username"], "MFA_RECOVERY_CODE_USED", f"{len(stored)} remaining", "WARNING")
            return True
    return False
