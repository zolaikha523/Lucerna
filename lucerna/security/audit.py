"""Audit trail. Records who did what to which object; avoids storing personal data in `detail`."""
from __future__ import annotations

from .. import db


def log(username: str | None, action: str, detail: str = "", severity: str = "INFO", *,
        org_id: int | None = None, project_id: int | None = None,
        object_type: str | None = None, object_id: str | int | None = None) -> None:
    db.execute(
        "INSERT INTO audit(ts, username, action, detail, severity, org_id, project_id, object_type, object_id)"
        " VALUES(?,?,?,?,?,?,?,?,?)",
        (db.now(), username or "system", action, (detail or "")[:2000], severity, org_id, project_id,
         object_type, None if object_id is None else str(object_id)),
    )


def recent(limit: int = 500, project_id: int | None = None, org_ids: list[int] | None = None) -> list[dict]:
    if project_id is not None:
        return db.query("SELECT * FROM audit WHERE project_id=? ORDER BY id DESC LIMIT ?", (project_id, limit))
    if org_ids is not None:
        if not org_ids:
            return []
        marks = ",".join("?" * len(org_ids))
        return db.query(f"SELECT * FROM audit WHERE org_id IN ({marks}) OR project_id IN "
                        f"(SELECT id FROM projects WHERE org_id IN ({marks})) ORDER BY id DESC LIMIT ?",
                        (*org_ids, *org_ids, limit))
    return db.query("SELECT * FROM audit ORDER BY id DESC LIMIT ?", (limit,))
