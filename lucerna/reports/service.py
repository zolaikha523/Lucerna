"""Report Centre service: report records, versions, editing overrides, review workflow, approval, export."""
from __future__ import annotations

import difflib
import secrets
from pathlib import Path

from .. import db
from ..config import settings
from ..security import audit
from ..security.rbac import CurrentUser, PermissionDenied, require
from . import exports, qual_report, quant_report, render_docx, render_pdf

REVIEW_STEPS = {
    "qualitative": ["evidence", "themes", "quotations", "findings", "recommendations", "edit"],
    "quantitative": ["data_quality", "indicators", "findings", "recommendations", "edit"],
    "mixed": ["evidence", "data_quality", "findings", "recommendations", "edit"],
}
STEP_LABELS = {"evidence": "Evidence verification reviewed", "themes": "Themes reviewed", "quotations": "Quotations reviewed",
               "findings": "Findings reviewed", "recommendations": "Recommendations reviewed", "edit": "Report text edited / checked",
               "data_quality": "Data quality reviewed", "indicators": "Indicator definitions and values reviewed"}


class ReportError(Exception):
    pass


def _get(report_id: int) -> dict:
    r = db.query_one("SELECT * FROM reports WHERE id=?", (report_id,))
    if not r:
        raise ReportError("Report not found.")
    r["metadata"] = db.loads(r.get("metadata_json"), {}) or {}
    return r


def get(user: CurrentUser, report_id: int) -> dict:
    r = _get(report_id)
    require(user, "project.view", r["project_id"])
    return r


def list_for_project(user: CurrentUser, project_id: int) -> list[dict]:
    require(user, "project.view", project_id)
    return db.query("SELECT id, kind, title, template, status, current_version, updated_at, approved_at FROM reports WHERE project_id=? ORDER BY updated_at DESC", (project_id,))


def create(user: CurrentUser, project_id: int, kind: str, title: str, metadata: dict, template: str | None = None) -> int:
    require(user, "report.edit", project_id)
    if kind not in REVIEW_STEPS:
        raise ReportError("Unknown report kind.")
    rid = db.execute("INSERT INTO reports(project_id, kind, title, template, status, metadata_json, current_version, created_by, created_at, updated_at) VALUES(?,?,?,?,?,?,0,?,?,?)",
                     (project_id, kind, title, template, "draft", db.dumps(metadata), user.id, db.now(), db.now()))
    audit.log(user.username, "REPORT_CREATED", f"{kind}: {title[:80]}", project_id=project_id, object_type="report", object_id=rid)
    return rid


def update_metadata(user: CurrentUser, report_id: int, metadata: dict, title: str | None = None) -> None:
    r = get(user, report_id)
    require(user, "report.edit", r["project_id"])
    db.execute("UPDATE reports SET metadata_json=?, title=COALESCE(?, title), status='draft', approved_by=NULL, approved_at=NULL, updated_at=? WHERE id=?",
               (db.dumps(metadata), title, db.now(), report_id))
    if r["status"] != "draft":
        db.execute("DELETE FROM report_reviews WHERE report_id=?", (report_id,))
        audit.log(user.username, "REPORT_RETURNED_TO_DRAFT", "edited after review/approval", "WARNING", project_id=r["project_id"], object_type="report", object_id=report_id)


def _apply_overrides(content: dict, overrides: dict) -> dict:
    for s in content["sections"]:
        o = overrides.get(s["id"]) or {}
        if "included" in o:
            s["included"] = bool(o["included"])
        if o.get("analyst_text"):
            s["blocks"].insert(0, {"kind": "paragraph", "text": o["analyst_text"], "label": "analyst"})
    return content


def build_content(user: CurrentUser, report_id: int, approved: bool = False) -> dict:
    r = get(user, report_id)
    md = {**r["metadata"], "_approved": approved, "title": r["title"]}
    if r["kind"] == "quantitative":
        content = quant_report.build(user, int(md["dataset_id"]), md, template=r.get("template"), dashboard_id=md.get("dashboard_id"),
                                     compare_dataset_id=md.get("compare_dataset_id"), include_ai_narrative=bool(md.get("include_ai_narrative")))
    elif r["kind"] == "qualitative":
        content = qual_report.build(user, r["project_id"], md, include_unreviewed_themes=bool(md.get("include_unreviewed_themes")),
                                    redact_contacts=md.get("redact_contacts", True))
    else:
        from . import mixed_report
        content = mixed_report.build(user, r["project_id"], md)
    return _apply_overrides(content, md.get("section_overrides") or {})


def generate_version(user: CurrentUser, report_id: int, note: str = "", formats: tuple[str, ...] = ("docx", "pdf", "xlsx")) -> dict:
    r = get(user, report_id)
    require(user, "report.edit", r["project_id"])
    approved = r["status"] == "approved"
    content = build_content(user, report_id, approved=approved)
    v = r["current_version"] + 1
    folder = settings().report_dir / f"project_{r['project_id']}" / f"report_{report_id}"
    folder.mkdir(parents=True, exist_ok=True)
    base = folder / f"v{v:03d}_{secrets.token_hex(4)}"
    paths = {}
    if "docx" in formats:
        paths["docx"] = render_docx.render(content, f"{base}.docx")
    if "pdf" in formats:
        paths["pdf"] = render_pdf.render(content, f"{base}.pdf")
    if "xlsx" in formats:
        paths["xlsx"] = exports.report_workbook(user, r, content, f"{base}.xlsx")
    storable = {**content, "sections": [{**s, "blocks": [{k: val for k, val in b.items()} for b in s["blocks"]]} for s in content["sections"]]}
    db.execute("INSERT INTO report_versions(report_id, version, content_json, docx_path, pdf_path, xlsx_path, note, created_by, created_at) VALUES(?,?,?,?,?,?,?,?,?)",
               (report_id, v, db.dumps(storable), paths.get("docx"), paths.get("pdf"), paths.get("xlsx"), note, user.id, db.now()))
    db.execute("UPDATE reports SET current_version=?, updated_at=? WHERE id=?", (v, db.now(), report_id))
    audit.log(user.username, "REPORT_VERSION_GENERATED", f"v{v} formats={','.join(paths)}", project_id=r["project_id"], object_type="report", object_id=report_id)
    return {"version": v, "paths": paths, "content": content}


def versions(user: CurrentUser, report_id: int) -> list[dict]:
    get(user, report_id)
    return db.query("SELECT id, version, docx_path, pdf_path, xlsx_path, note, created_at FROM report_versions WHERE report_id=? ORDER BY version DESC", (report_id,))


def version_text(user: CurrentUser, version_id: int) -> str:
    v = db.query_one("SELECT * FROM report_versions WHERE id=?", (version_id,))
    get(user, v["report_id"])
    c = db.loads(v["content_json"], {})
    lines = []
    for s in c.get("sections", []):
        if not s.get("included", True):
            continue
        lines.append(f"## {s['title']}")
        for b in s["blocks"]:
            if b["kind"] in ("paragraph", "callout"):
                lines.append(b["text"])
            elif b["kind"] == "bullets":
                lines += [f"- {x}" for x in b["items"]]
            elif b["kind"] == "quote":
                lines.append(f"> {b['text']} — {b['source']}")
            elif b["kind"] in ("table", "kv"):
                rows = b.get("rows", [])
                lines += [" | ".join(str(x) for x in r) for r in rows]
            elif b["kind"] == "chart":
                lines.append(f"[chart] {b.get('caption')}")
    return "\n".join(lines)


def compare_versions(user: CurrentUser, version_a: int, version_b: int) -> str:
    a = version_text(user, version_a).splitlines()
    b = version_text(user, version_b).splitlines()
    return "\n".join(difflib.unified_diff(a, b, "older", "newer", lineterm="", n=1))


def record_review(user: CurrentUser, report_id: int, step: str, decision: str = "completed", note: str = "") -> None:
    r = get(user, report_id)
    require(user, "report.edit", r["project_id"])
    if step not in REVIEW_STEPS[r["kind"]]:
        raise ReportError("Unknown review step for this report.")
    db.execute("INSERT INTO report_reviews(report_id, step, decision, note, reviewer_id, ts) VALUES(?,?,?,?,?,?)", (report_id, step, decision, note, user.id, db.now()))
    db.execute("UPDATE reports SET status=CASE WHEN status='draft' THEN 'in_review' ELSE status END, updated_at=? WHERE id=?", (db.now(), report_id))
    audit.log(user.username, "REPORT_REVIEW_STEP", f"{step}: {decision}", project_id=r["project_id"], object_type="report", object_id=report_id)


def review_status(user: CurrentUser, report_id: int) -> list[dict]:
    r = get(user, report_id)
    out = []
    for step in REVIEW_STEPS[r["kind"]]:
        last = db.query_one("SELECT rr.*, u.username FROM report_reviews rr LEFT JOIN users u ON u.id=rr.reviewer_id WHERE report_id=? AND step=? ORDER BY ts DESC LIMIT 1", (report_id, step))
        out.append({"step": step, "label": STEP_LABELS[step], "done": bool(last and last["decision"] == "completed"), "by": last["username"] if last else None,
                    "note": last["note"] if last else None, "decision": last["decision"] if last else None})
    return out


def approve(user: CurrentUser, report_id: int) -> dict:
    r = get(user, report_id)
    require(user, "report.approve", r["project_id"])
    pending = [s["label"] for s in review_status(user, report_id) if not s["done"]]
    if pending:
        raise ReportError("Cannot approve: these review steps are not complete — " + "; ".join(pending))
    if r["current_version"] == 0:
        raise ReportError("Generate at least one draft version before approval.")
    db.execute("UPDATE reports SET status='approved', approved_by=?, approved_at=?, updated_at=? WHERE id=?", (user.id, db.now(), db.now(), report_id))
    audit.log(user.username, "REPORT_APPROVED", r["title"][:80], "HIGH", project_id=r["project_id"], object_type="report", object_id=report_id)
    return generate_version(user, report_id, note="Final approved version")


def log_download(user: CurrentUser, version_id: int, fmt: str) -> None:
    v = db.query_one("SELECT report_id, version FROM report_versions WHERE id=?", (version_id,))
    r = get(user, v["report_id"])
    audit.log(user.username, "REPORT_DOWNLOADED", f"v{v['version']} {fmt}", project_id=r["project_id"], object_type="report", object_id=r["id"])


def file_for_download(user: CurrentUser, version_id: int, fmt: str, log: bool = True) -> Path:
    v = db.query_one("SELECT * FROM report_versions WHERE id=?", (version_id,))
    if not v:
        raise ReportError("Version not found.")
    r = get(user, v["report_id"])
    require(user, "export", r["project_id"])
    p = v.get(f"{fmt}_path")
    if not p or not Path(p).exists():
        raise ReportError("File not available for this version.")
    root = settings().report_dir.resolve()
    if root not in Path(p).resolve().parents:
        raise PermissionDenied("Invalid file location.")
    if log:
        log_download(user, version_id, fmt)
    return Path(p)
