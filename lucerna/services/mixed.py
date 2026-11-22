"""Mixed-methods evidence mapping. Links a computed quantitative result (indicator) to a qualitative
theme with an explicit relationship. Integrated findings exist only where BOTH evidence streams are
linked and an analyst has approved the integration. No assumption that survey respondents and FGD
participants are the same people."""
from __future__ import annotations

from .. import db
from ..security import audit
from ..security.rbac import CurrentUser, PermissionDenied, require

RELATIONSHIPS = {"supports": "Qualitative evidence supports the quantitative result", "explains": "Qualitative evidence helps explain the result",
                 "contradicts": "The evidence streams point in different directions", "complements": "Adds a different dimension",
                 "unclear": "Relationship unclear — needs further enquiry"}


def add_link(user: CurrentUser, project_id: int, *, indicator_id: int | None, theme_id: int, relationship: str, quant_statement: str,
             analyst_note: str = "", integrated_finding: str = "", dataset_id: int | None = None) -> int:
    require(user, "qual.code", project_id)
    if relationship not in RELATIONSHIPS:
        raise ValueError("Unknown relationship")
    t = db.query_one("SELECT project_id FROM themes WHERE id=?", (theme_id,))
    if not t or t["project_id"] != project_id:
        raise PermissionDenied("Theme not in this project.")
    if indicator_id:
        i = db.query_one("SELECT project_id FROM indicators WHERE id=?", (indicator_id,))
        if not i or i["project_id"] != project_id:
            raise PermissionDenied("Indicator not in this project.")
    if not (quant_statement or "").strip():
        raise ValueError("A quantitative result statement is required.")
    lid = db.execute("INSERT INTO evidence_links(project_id, indicator_id, quant_statement, dataset_id, theme_id, relationship, analyst_note, integrated_finding, status, created_by, created_at)"
                     " VALUES(?,?,?,?,?,?,?,?, 'draft', ?, ?)",
                     (project_id, indicator_id, quant_statement.strip(), dataset_id, theme_id, relationship, analyst_note, integrated_finding, user.id, db.now()))
    audit.log(user.username, "MIXED_LINK_ADDED", relationship, project_id=project_id, object_type="evidence_link", object_id=lid)
    return lid


def list_links(user: CurrentUser, project_id: int, approved_only: bool = False) -> list[dict]:
    require(user, "project.view", project_id)
    rows = db.query("SELECT l.*, t.name AS theme_name, i.name AS indicator_name FROM evidence_links l LEFT JOIN themes t ON t.id=l.theme_id"
                    " LEFT JOIN indicators i ON i.id=l.indicator_id WHERE l.project_id=? ORDER BY l.id", (project_id,))
    return [r for r in rows if not approved_only or r["status"] == "approved"]


def review_link(user: CurrentUser, link_id: int, approve: bool, integrated_finding: str | None = None) -> None:
    l = db.query_one("SELECT * FROM evidence_links WHERE id=?", (link_id,))
    require(user, "report.approve" if approve else "qual.code", l["project_id"])
    if approve and not (integrated_finding or l.get("integrated_finding") or "").strip():
        raise ValueError("Write the integrated finding before approving.")
    db.execute("UPDATE evidence_links SET status=?, integrated_finding=COALESCE(?, integrated_finding), reviewed_by=?, reviewed_at=? WHERE id=?",
               ("approved" if approve else "draft", integrated_finding, user.id, db.now(), link_id))
    audit.log(user.username, "MIXED_LINK_APPROVED" if approve else "MIXED_LINK_REOPENED", f"#{link_id}", project_id=l["project_id"])


def delete_link(user: CurrentUser, link_id: int) -> None:
    l = db.query_one("SELECT * FROM evidence_links WHERE id=?", (link_id,))
    require(user, "qual.code", l["project_id"])
    db.execute("DELETE FROM evidence_links WHERE id=?", (link_id,))
