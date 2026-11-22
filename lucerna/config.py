"""Central configuration. All paths and switches come from environment variables
(optionally loaded from `.env`). No machine-specific paths are hard-coded here."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

try:  # optional dependency; config still works without it
    from dotenv import load_dotenv
except Exception:  # pragma: no cover
    load_dotenv = None

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if load_dotenv:
    load_dotenv(PROJECT_ROOT / ".env", override=False)


def _env(name: str, default: str) -> str:
    v = os.getenv(name)
    return v if v not in (None, "") else default


def _bool(name: str, default: bool) -> bool:
    return _env(name, "1" if default else "0").strip().lower() in {"1", "true", "yes", "on"}


def _resolve(p: str) -> Path:
    path = Path(p).expanduser()
    return path if path.is_absolute() else (PROJECT_ROOT / path)


def _default_db() -> str:
    """Upgrade path: an existing EvidenceQDA database is used (and migrated in place) when no Lucerna
    database exists yet, so earlier users, audit history and chats are preserved."""
    new, legacy = PROJECT_ROOT / "data" / "lucerna.sqlite3", PROJECT_ROOT / "data" / "evidenceqda.sqlite3"
    return "data/evidenceqda.sqlite3" if legacy.exists() and not new.exists() else "data/lucerna.sqlite3"


@dataclass
class Settings:
    data_dir: Path = field(default_factory=lambda: _resolve(_env("LUCERNA_DATA_DIR", _env("EVIDENCEQDA_DATA_DIR", "data"))))
    db_path: Path = field(default_factory=lambda: _resolve(_env("LUCERNA_DB", _env("EVIDENCEQDA_DB", _default_db()))))
    upload_dir: Path = field(default_factory=lambda: _resolve(_env("LUCERNA_UPLOAD_DIR", "data/uploads")))
    analytic_dir: Path = field(default_factory=lambda: _resolve(_env("LUCERNA_ANALYTIC_DIR", "data/analytic")))
    report_dir: Path = field(default_factory=lambda: _resolve(_env("LUCERNA_REPORT_DIR", "data/outputs")))
    log_dir: Path = field(default_factory=lambda: _resolve(_env("LUCERNA_LOG_DIR", "data/logs")))
    temp_dir: Path = field(default_factory=lambda: _resolve(_env("LUCERNA_TEMP_DIR", "data/tmp")))
    backup_dir: Path = field(default_factory=lambda: _resolve(_env("LUCERNA_BACKUP_DIR", "data/backups")))

    max_upload_mb: int = field(default_factory=lambda: int(_env("LUCERNA_MAX_UPLOAD_MB", "200")))
    session_hours: float = field(default_factory=lambda: float(_env("LUCERNA_SESSION_HOURS", "8")))
    login_max_failures: int = field(default_factory=lambda: int(_env("LUCERNA_LOGIN_MAX_FAILURES", "5")))
    login_lock_minutes: int = field(default_factory=lambda: int(_env("LUCERNA_LOGIN_LOCK_MINUTES", "15")))
    job_workers: int = field(default_factory=lambda: int(_env("LUCERNA_JOB_WORKERS", "2")))

    # AI — local first. External providers are disabled unless explicitly enabled AND approved in-app.
    ai_provider: str = field(default_factory=lambda: _env("LUCERNA_AI_PROVIDER", "ollama"))
    ollama_url: str = field(default_factory=lambda: _env("OLLAMA_URL", "http://localhost:11434/api/chat"))
    ollama_model: str = field(default_factory=lambda: _env("OLLAMA_MODEL", "gemma3:4b"))
    ollama_num_gpu: str = field(default_factory=lambda: _env("OLLAMA_NUM_GPU", ""))  # "" = let Ollama decide; "0" = CPU only
    llm_timeout: int = field(default_factory=lambda: int(_env("OLLAMA_TIMEOUT_SECONDS", "180")))
    llm_retries: int = field(default_factory=lambda: int(_env("LLM_JSON_RETRIES", "2")))
    llm_batch: int = field(default_factory=lambda: int(_env("MAX_SEGMENTS_PER_LLM_BATCH", "1")))
    llm_num_predict: int = field(default_factory=lambda: int(_env("LLM_NUM_PREDICT", "2048")))
    external_ai_enabled: bool = field(default_factory=lambda: _bool("LUCERNA_EXTERNAL_AI_ENABLED", False))

    def ensure_dirs(self) -> None:
        for p in (self.data_dir, self.upload_dir, self.analytic_dir, self.report_dir,
                  self.log_dir, self.temp_dir, self.backup_dir, self.db_path.parent):
            p.mkdir(parents=True, exist_ok=True)


_settings: Settings | None = None


def settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
        _settings.ensure_dirs()
    return _settings


def reload_settings() -> Settings:
    """Re-read environment (used by tests that point Lucerna at a temp directory)."""
    global _settings
    _settings = None
    return settings()
