"""First-run defaults. Never creates users or fake data."""
from __future__ import annotations

from .. import db
from ..config import settings


def seed_defaults() -> None:
    s = settings()
    if not db.query_one("SELECT 1 FROM ai_providers"):
        db.execute(
            "INSERT INTO ai_providers(name, kind, base_url, model, is_external, enabled, is_default, created_at, options_json)"
            " VALUES(?,?,?,?,0,1,1,?,?)",
            ("Local Ollama", "ollama", s.ollama_url, s.ollama_model, db.now(),
             db.dumps({"num_gpu": s.ollama_num_gpu or None})))
    defaults = {
        "privacy.external_ai_allowed": "0",
        "privacy.pii_scan_on_upload": "1",
        "privacy.geo_precision": "admin2",
        "privacy.pseudonymize_exports": "0",
        "ui.theme": "light",
    }
    for k, v in defaults.items():
        db.execute("INSERT OR IGNORE INTO app_settings(key, value, updated_at, updated_by) VALUES(?,?,?,?)",
                   (k, v, db.now(), "system"))


def get_setting(key: str, default: str | None = None) -> str | None:
    r = db.query_one("SELECT value FROM app_settings WHERE key=?", (key,))
    return r["value"] if r else default


def set_setting(key: str, value: str, actor: str) -> None:
    db.execute("INSERT INTO app_settings(key, value, updated_at, updated_by) VALUES(?,?,?,?)"
               " ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at, updated_by=excluded.updated_by",
               (key, str(value), db.now(), actor))
