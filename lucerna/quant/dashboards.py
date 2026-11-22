"""Dashboard persistence: auto generation, custom editing, versions, templates, bookmarks."""
from __future__ import annotations

import copy
import uuid

from .. import db
from ..security import audit
from ..security.rbac import CurrentUser, PermissionDenied, require
from . import store


def _get(dashboard_id: int) -> dict:
    d = db.query_one("SELECT * FROM dashboards WHERE id=?", (dashboard_id,))
    if not d:
        raise PermissionDenied("Dashboard not found.")
    d["spec"] = db.loads(d["spec_json"], {})
    d["plan"] = db.loads(d.get("plan_json"), {})
    return d


def get(user: CurrentUser, dashboard_id: int) -> dict:
    d = _get(dashboard_id)
    require(user, "project.view", d["project_id"])
    return d


def list_for_project(user: CurrentUser, project_id: int) -> list[dict]:
    require(user, "project.view", project_id)
    return db.query("SELECT id, name, mode, dataset_id, compare_dataset_id, version, is_template, updated_at FROM dashboards WHERE project_id=? ORDER BY updated_at DESC", (project_id,))


def generate_auto(user: CurrentUser, dataset_id: int, name: str | None = None, theme: str = "corporate") -> int:
    """Generate a dashboard with the universal adaptive engine (see quant/engine.py)."""
    from . import generator
    return generator.generate(user, dataset_id, theme=theme, name=name)


def create_blank(user: CurrentUser, project_id: int, dataset_id: int, name: str, mode: str = "custom", compare_dataset_id: int | None = None) -> int:
    require(user, "dashboard.edit", project_id)
    spec = {"pages": [{"key": "page1", "title": "Page 1", "icon": "layout-dashboard", "purpose": "", "visuals": []}], "filters": [], "theme": "light"}
    did = db.execute("INSERT INTO dashboards(project_id, dataset_id, compare_dataset_id, name, mode, spec_json, version, created_by, created_at, updated_at) VALUES(?,?,?,?,?,?,1,?,?,?)",
                     (project_id, dataset_id, compare_dataset_id, name, mode, db.dumps(spec), user.id, db.now(), db.now()))
    audit.log(user.username, "DASHBOARD_CREATED", name, project_id=project_id, object_type="dashboard", object_id=did)
    return did


def save_spec(user: CurrentUser, dashboard_id: int, spec: dict, note: str = "", new_version: bool = False) -> int:
    d = _get(dashboard_id)
    require(user, "dashboard.edit", d["project_id"])
    version = d["version"] + 1 if new_version else d["version"]
    db.execute("UPDATE dashboards SET spec_json=?, version=?, updated_at=?, mode=CASE WHEN mode='auto' THEN 'custom' ELSE mode END WHERE id=?",
               (db.dumps(spec), version, db.now(), dashboard_id))
    if new_version:
        db.execute("INSERT INTO dashboard_versions(dashboard_id, version, spec_json, note, created_by, created_at) VALUES(?,?,?,?,?,?)",
                   (dashboard_id, version, db.dumps(spec), note or "Saved version", user.id, db.now()))
        audit.log(user.username, "DASHBOARD_VERSION_SAVED", f"v{version}", project_id=d["project_id"], object_type="dashboard", object_id=dashboard_id)
    return version


def versions(user: CurrentUser, dashboard_id: int) -> list[dict]:
    get(user, dashboard_id)
    return db.query("SELECT id, version, note, created_at FROM dashboard_versions WHERE dashboard_id=? ORDER BY version DESC", (dashboard_id,))


def restore_version(user: CurrentUser, dashboard_id: int, version_id: int) -> None:
    v = db.query_one("SELECT * FROM dashboard_versions WHERE id=? AND dashboard_id=?", (version_id, dashboard_id))
    if not v:
        raise PermissionDenied("Version not found.")
    save_spec(user, dashboard_id, db.loads(v["spec_json"]), note=f"Restored from v{v['version']}", new_version=True)


def duplicate(user: CurrentUser, dashboard_id: int, name: str | None = None, as_template: bool = False) -> int:
    d = get(user, dashboard_id)
    require(user, "dashboard.edit", d["project_id"])
    nid = db.execute("INSERT INTO dashboards(project_id, dataset_id, compare_dataset_id, name, mode, spec_json, plan_json, version, is_template, created_by, created_at, updated_at,"
                     " theme, branding_json, linked_json, source_version, generated_at) VALUES(?,?,?,?,?,?,?,1,?,?,?,?,?,?,?,?,?)",
                     (d["project_id"], d["dataset_id"], d["compare_dataset_id"], name or f"{d['name']} (copy)", d["mode"],
                      d["spec_json"], d.get("plan_json"), int(as_template), user.id, db.now(), db.now(),
                      d.get("theme"), d.get("branding_json"), d.get("linked_json"), d.get("source_version"), d.get("generated_at")))
    db.execute("INSERT INTO dashboard_versions(dashboard_id, version, spec_json, note, created_by, created_at) VALUES(?,?,?,?,?,?)",
               (nid, 1, d["spec_json"], f"Duplicated from #{dashboard_id}", user.id, db.now()))
    audit.log(user.username, "DASHBOARD_DUPLICATED", f"from #{dashboard_id}", project_id=d["project_id"], object_type="dashboard", object_id=nid)
    return nid


def apply_template(user: CurrentUser, template_id: int, dataset_id: int) -> tuple[int, list[str]]:
    """Copy a template to another dataset; visuals whose columns do not exist are kept but reported."""
    t = get(user, template_id)
    ds = store.get_dataset(user, dataset_id)
    require(user, "dashboard.edit", ds["project_id"])
    cols = set(store.analytic_frame(user, dataset_id).columns)
    spec = copy.deepcopy(t["spec"])
    missing = []
    for p in spec["pages"]:
        for v in p["visuals"]:
            v["id"] = uuid.uuid4().hex[:8]
            used = [v.get(k) for k in ("x", "value", "color", "by", "date", "lat", "lon", "source", "target", "sex", "age") if v.get(k)]
            used += [(v.get("condition") or {}).get("column")] if v.get("condition") else []
            miss = [c for c in used if c not in cols]
            if miss:
                missing.append(f"{v.get('title')}: {', '.join(miss)}")
    nid = db.execute("INSERT INTO dashboards(project_id, dataset_id, name, mode, spec_json, version, created_by, created_at, updated_at) VALUES(?,?,?,?,?,1,?,?,?)",
                     (ds["project_id"], dataset_id, f"{t['name']} — {ds['name']}", "custom", db.dumps(spec), user.id, db.now(), db.now()))
    return nid, missing


def delete(user: CurrentUser, dashboard_id: int) -> None:
    d = get(user, dashboard_id)
    require(user, "dashboard.edit", d["project_id"])
    db.execute("DELETE FROM dashboards WHERE id=?", (dashboard_id,))
    audit.log(user.username, "DASHBOARD_DELETED", d["name"], project_id=d["project_id"])


def save_bookmark(user: CurrentUser, dashboard_id: int, name: str, page_index: int, filters: dict) -> int:
    d = get(user, dashboard_id)
    return db.execute("INSERT INTO dashboard_bookmarks(dashboard_id, name, page_index, filters_json, created_by, created_at) VALUES(?,?,?,?,?,?)",
                      (dashboard_id, name, page_index, db.dumps(filters), user.id, db.now()))


def bookmarks(user: CurrentUser, dashboard_id: int) -> list[dict]:
    get(user, dashboard_id)
    rows = db.query("SELECT * FROM dashboard_bookmarks WHERE dashboard_id=? ORDER BY created_at DESC", (dashboard_id,))
    for r in rows:
        r["filters"] = db.loads(r["filters_json"], {})
    return rows


def templates(user: CurrentUser, project_id: int) -> list[dict]:
    require(user, "project.view", project_id)
    return db.query("SELECT id, name, updated_at FROM dashboards WHERE is_template=1 AND project_id IN "
                    "(SELECT id FROM projects WHERE org_id=(SELECT org_id FROM projects WHERE id=?)) ORDER BY name", (project_id,))
