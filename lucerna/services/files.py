"""Secure storage of uploaded files.

* Original uploads are written once, under a server-generated name, inside the project's upload
  folder; user-supplied filenames are never used as paths (prevents path traversal / overwrite).
* Extension allow-list + size limit + content sniffing for obviously wrong/malicious content.
"""
from __future__ import annotations

import hashlib
import re
import secrets
from pathlib import Path

from .. import db
from ..config import settings
from ..security import audit
from ..security.rbac import CurrentUser, require

QUANT_EXT = {".xlsx", ".xls", ".csv", ".tsv", ".txt", ".json", ".jsonl", ".docx", ".pdf"}
QUAL_EXT = {".txt", ".docx", ".pdf", ".md"}

_SIGNATURES = {
    ".xlsx": [b"PK\x03\x04"], ".docx": [b"PK\x03\x04"],
    ".xls": [b"\xd0\xcf\x11\xe0"], ".pdf": [b"%PDF"],
}
_DANGEROUS = [b"MZ", b"\x7fELF", b"#!/", b"<script", b"<?php"]


class UploadRejected(Exception):
    pass


def safe_display_name(name: str) -> str:
    base = Path(name or "file").name
    base = re.sub(r"[^\w.\- ()؀-ۿ]", "_", base)[:150]
    return base or "file"


def validate_upload(name: str, data: bytes, allowed: set[str]) -> str:
    ext = Path(name or "").suffix.lower()
    if ext not in allowed:
        raise UploadRejected(f"File type '{ext or 'none'}' is not supported here. Allowed: {', '.join(sorted(allowed))}")
    max_bytes = settings().max_upload_mb * 1024 * 1024
    if len(data) == 0:
        raise UploadRejected("The file is empty.")
    if len(data) > max_bytes:
        raise UploadRejected(f"File exceeds the {settings().max_upload_mb} MB limit (LUCERNA_MAX_UPLOAD_MB).")
    head = data[:8]
    if ext in _SIGNATURES and not any(head.startswith(sig) for sig in _SIGNATURES[ext]):
        raise UploadRejected(f"The content of '{safe_display_name(name)}' does not match a real {ext} file.")
    if ext not in _SIGNATURES:
        low = data[:512].lower()
        if any(low.startswith(sig.lower()) for sig in _DANGEROUS):
            raise UploadRejected("The file looks like an executable or script and was rejected.")
    return ext


def store_upload(user: CurrentUser, project_id: int, name: str, data: bytes, purpose: str) -> dict:
    require(user, "data.upload", project_id)
    allowed = QUANT_EXT if purpose == "quantitative" else QUAL_EXT
    ext = validate_upload(name, data, allowed)
    folder = settings().upload_dir / f"project_{int(project_id)}"
    folder.mkdir(parents=True, exist_ok=True)
    stored = folder / f"{secrets.token_hex(12)}{ext}"
    stored.write_bytes(data)
    sha = hashlib.sha256(data).hexdigest()
    fid = db.execute("INSERT INTO data_files(project_id, original_name, stored_path, sha256, size_bytes, extension, purpose, uploaded_by, uploaded_at)"
                     " VALUES(?,?,?,?,?,?,?,?,?)",
                     (project_id, safe_display_name(name), str(stored), sha, len(data), ext, purpose, user.id, db.now()))
    audit.log(user.username, "FILE_UPLOADED", f"{purpose} file #{fid} ({ext}, {len(data)} bytes)", project_id=project_id,
              object_type="data_file", object_id=fid)
    return db.query_one("SELECT * FROM data_files WHERE id=?", (fid,))


def get_file(user: CurrentUser, file_id: int) -> dict:
    f = db.query_one("SELECT * FROM data_files WHERE id=?", (file_id,))
    if not f:
        raise UploadRejected("File not found.")
    require(user, "project.view", f["project_id"])
    return f


def secure_delete(path: Path) -> None:
    """Best-effort overwrite then unlink. On SSDs and journaled filesystems overwriting is not a
    guarantee; full-disk encryption (e.g. BitLocker) is the recommended control. See docs/SECURITY.md."""
    p = Path(path)
    if not p.exists() or not p.is_file():
        return
    root = settings().data_dir.resolve()
    if root not in p.resolve().parents:
        raise UploadRejected("Refusing to delete a file outside the Lucerna data directory.")
    size = p.stat().st_size
    with open(p, "r+b") as fh:
        fh.write(secrets.token_bytes(min(size, 64 * 1024 * 1024)))
    p.unlink()
