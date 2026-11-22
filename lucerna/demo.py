"""Optional public-demo mode (e.g. Streamlit Community Cloud).

Set LUCERNA_DEMO_MODE=1 (an environment variable, or a top-level entry in Streamlit secrets). On the first start
with an empty database, Lucerna builds a demo workspace from the SYNTHETIC datasets in tests/ and shows the demo
sign-in on the login page. Never enable this on an installation that holds real data: the demo credentials are public.
"""
from __future__ import annotations

import os

DEMO_USER = ("admin", "Lucerna-Demo-2026!")


def enabled() -> bool:
    return os.environ.get("LUCERNA_DEMO_MODE", "").strip().lower() in ("1", "true", "yes", "on")


def ensure_demo() -> None:
    """Seed the synthetic demo once, only when the database has no users yet."""
    from . import config, db
    from .security import auth
    db.init()
    if auth.user_count() > 0:
        return
    lock = config.settings().data_dir / ".demo_seeding"
    lock.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL)
    except FileExistsError:   # another session is already seeding
        return
    try:
        from tests.seed_demo import seed
        seed(verbose=False)
    finally:
        os.close(fd)
        lock.unlink(missing_ok=True)
