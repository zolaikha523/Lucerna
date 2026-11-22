"""Backups: a consistent SQLite snapshot plus the stored files, written as one ZIP to the backup folder.

Restoring is a deliberate manual step (stop Lucerna, unpack, start) and is documented in
docs/BACKUP_AND_RECOVERY.md. Lucerna never deletes or overwrites existing backups.
"""
from __future__ import annotations

import sqlite3
import tempfile
import time
import zipfile
from pathlib import Path

from ..config import settings
from ..security import audit


def _dirs() -> dict[str, Path]:
    s = settings()
    return {"uploads": s.upload_dir, "analytic": s.analytic_dir, "outputs": s.report_dir}


def create_backup(actor: str = "system", include_files: bool = True) -> Path:
    s = settings()
    s.backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    target = s.backup_dir / f"lucerna_backup_{stamp}.zip"
    n = 1
    while target.exists():
        target = s.backup_dir / f"lucerna_backup_{stamp}_{n}.zip"
        n += 1
    with tempfile.TemporaryDirectory(dir=s.temp_dir) as td:
        snap = Path(td) / "lucerna.sqlite3"
        src = sqlite3.connect(str(s.db_path))
        dst = sqlite3.connect(str(snap))
        with dst:
            src.backup(dst)   # consistent online snapshot, safe while the app is running
        src.close()
        dst.close()
        with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as z:
            z.write(snap, "database/lucerna.sqlite3")
            if include_files:
                for name, d in _dirs().items():
                    if d.exists():
                        for f in d.rglob("*"):
                            if f.is_file():
                                z.write(f, f"{name}/{f.relative_to(d).as_posix()}")
            z.writestr("README.txt", "Lucerna backup.\n\nTo restore: stop Lucerna; copy database/lucerna.sqlite3 to the LUCERNA_DB path;\n"
                                     "copy uploads/, analytic/ and outputs/ into the matching LUCERNA_*_DIR folders; start Lucerna.\n"
                                     "See docs/BACKUP_AND_RECOVERY.md.\n")
    audit.log(actor, "BACKUP_CREATED", f"{target.name} ({target.stat().st_size // 1024} KB)", "INFO")
    return target


def list_backups() -> list[dict]:
    d = settings().backup_dir
    if not d.exists():
        return []
    return [{"name": p.name, "size_mb": round(p.stat().st_size / 1e6, 2), "created": time.strftime("%Y-%m-%d %H:%M", time.localtime(p.stat().st_mtime))}
            for p in sorted(d.glob("lucerna_backup_*.zip"), reverse=True)]


def storage_report() -> list[dict]:
    s = settings()
    rows = []
    for label, p in [("Database", s.db_path), ("Uploads (originals)", s.upload_dir), ("Analytical copies", s.analytic_dir), ("Reports", s.report_dir),
                     ("Logs", s.log_dir), ("Temporary", s.temp_dir), ("Backups", s.backup_dir)]:
        size = p.stat().st_size if p.is_file() else sum(f.stat().st_size for f in p.rglob("*") if f.is_file()) if p.exists() else 0
        rows.append({"location": label, "path": str(p), "exists": p.exists(), "size_mb": round(size / 1e6, 2)})
    return rows


if __name__ == "__main__":  # python -m lucerna.services.backup
    from .. import db
    db.init()
    print(create_backup("backup-script"))
