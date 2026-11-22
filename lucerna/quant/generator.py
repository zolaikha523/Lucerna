"""One-click dashboard generation service: dataset → analysis → multi-page dashboard, plus persistence
(rename, theme, branding, refresh when data change, versions) and data loading for the viewer.

Permission checks happen here; the UI only calls these functions.
"""
from __future__ import annotations

import io
import secrets
from pathlib import Path

import pandas as pd

from .. import db
from ..config import settings
from ..security import audit
from ..security.rbac import CurrentUser, require
from . import engine, store, workbook
from .dashboards import _get

THEMES = {
    "corporate": "Corporate Light",
    "executive": "Executive Dark",
    "vibrant": "Modern Vibrant",
    "minimal": "Research & Minimal",
}
LOGO_MAX_BYTES = 1_000_000


class GenerationError(Exception):
    pass


# ---------------------------------------------------------------- dataset overview for the builder

def dataset_choices(user: CurrentUser, project_id: int, include_reference: bool = False) -> list[dict]:
    """Datasets suitable for a dashboard. Codebooks, README, lookups and indicator lists are hidden by default."""
    rows = store.list_datasets(user, project_id)
    if include_reference:
        return rows
    return [r for r in rows if (r.get("sheet_role") or "survey") in workbook.ANALYTICAL_ROLES]


def summary(user: CurrentUser, dataset_id: int) -> dict:
    d = store.get_dataset(user, dataset_id)
    prof = d.get("profile") or {}
    wb = store.workbook_info(user, dataset_id)
    cols = prof.get("columns", [])
    dates = [c for c in cols if c.get("inferred_type") == "date" and c.get("date_range")]
    geo = [c["name"] for c in cols if (c.get("inferred_role") or "").startswith("geo_")]
    return {
        "name": d["name"], "sheet": d.get("source_table"), "rows": d.get("row_count"), "columns": d.get("column_count"),
        "role": d.get("sheet_role") or "survey", "role_label": workbook.ROLE_LABELS.get(d.get("sheet_role") or "survey"),
        "is_primary": bool(d.get("is_primary", 1)), "unit": d.get("unit_of_analysis"), "unit_confirmed": bool(d.get("unit_confirmed")),
        "date_range": [dates[0]["date_range"][0], dates[0]["date_range"][1]] if dates else None, "date_column": dates[0]["name"] if dates else None,
        "geo_columns": geo, "pii_columns": prof.get("pii_columns", []),
        "missing_pct": round(sum(c.get("pct_missing", 0) for c in cols) / max(1, len(cols)), 1),
        "needs_review": len(prof.get("needs_review", [])), "workbook": wb, "version": d.get("version"),
    }


# ---------------------------------------------------------------- generation

def _linked_inputs(user: CurrentUser, dataset_id: int, wb: dict | None) -> list[dict]:
    if not wb:
        return []
    ids = wb.get("dataset_ids", {})
    me = store.get_dataset(user, dataset_id)
    if me.get("source_table") != wb.get("primary"):
        return []  # links are described relative to the primary sheet
    out = []
    for ln in wb.get("linked", []):
        did = ids.get(ln["sheet"])
        if not did:
            continue
        out.append({"df": store.analytic_frame(user, did), "mapping": store.mapping(did), "labels": store.labels(did),
                    "name": ln["sheet"], "dataset_id": did, "reason": f"Linked to the main data through {ln['primary_column']} ↔ {ln['other_column']}. "
                    + ln["decision"][0].upper() + ln["decision"][1:] + "."})
    return out


def build_for(user: CurrentUser, dataset_id: int) -> dict:
    ds = store.get_dataset(user, dataset_id)
    df = store.analytic_frame(user, dataset_id)
    if df.empty:
        raise GenerationError("The dataset has no rows to analyse.")
    mp = store.mapping(dataset_id)
    wb = store.workbook_info(user, dataset_id)
    linked = _linked_inputs(user, dataset_id, wb)
    res = engine.build(df, mp, labels=store.labels(dataset_id), unit=ds.get("unit_of_analysis") or "unknown",
                       unit_confirmed=bool(ds.get("unit_confirmed")), dataset_name=ds["name"], sheet=ds.get("source_table") or ds["name"],
                       sheet_names=[s["name"] for s in (wb or {}).get("sheets", [])], workbook={k: wb[k] for k in ("sheets", "primary", "explanation", "linked", "relationships")} if wb else {},
                       linked=linked, mapping_confirmed=all(m.get("confirmed") for m in mp.values()))
    res["linked_ids"] = [x["dataset_id"] for x in linked]
    res["version"] = ds.get("version")
    return res


def generate(user: CurrentUser, dataset_id: int, *, theme: str = "corporate", branding: dict | None = None, name: str | None = None) -> int:
    ds = store.get_dataset(user, dataset_id)
    require(user, "dashboard.edit", ds["project_id"])
    if theme not in THEMES:
        raise GenerationError(f"Unknown theme '{theme}'.")
    res = build_for(user, dataset_id)
    res["spec"]["theme"] = theme
    title = (branding or {}).get("title") or name or f"{ds['name']} — Analytical Dashboard"
    branding = {"title": title, "subtitle": "", "show_org": True, "logo": "org", **(branding or {})}
    now = db.now()
    did = db.execute("INSERT INTO dashboards(project_id, dataset_id, name, mode, spec_json, plan_json, version, created_by, created_at, updated_at,"
                     " theme, branding_json, linked_json, source_version, generated_at) VALUES(?,?,?,?,?,?,1,?,?,?,?,?,?,?,?)",
                     (ds["project_id"], dataset_id, name or title, "auto", db.dumps(res["spec"]), db.dumps(res["plan"]), user.id, now, now,
                      theme, db.dumps(branding), db.dumps(res["linked_ids"]), res["version"], now))
    db.execute("INSERT INTO dashboard_versions(dashboard_id, version, spec_json, note, created_by, created_at) VALUES(?,?,?,?,?,?)",
               (did, 1, db.dumps(res["spec"]), "Generated automatically (universal adaptive engine)", user.id, now))
    audit.log(user.username, "DASHBOARD_GENERATED", f"{len(res['spec']['pages'])} pages; domain={res['plan']['domain']['key']}",
              project_id=ds["project_id"], object_type="dashboard", object_id=did)
    return did


def get(user: CurrentUser, dashboard_id: int) -> dict:
    d = _get(dashboard_id)
    require(user, "project.view", d["project_id"])
    d["branding"] = db.loads(d.get("branding_json"), {}) or {"title": d["name"]}
    d["linked_ids"] = db.loads(d.get("linked_json"), []) or []
    d["theme"] = d.get("theme") or d["spec"].get("theme") or "corporate"
    if d["theme"] not in THEMES:
        d["theme"] = "executive" if d["theme"] == "dark" else "corporate"
    ds = db.query_one("SELECT version, name FROM datasets WHERE id=?", (d["dataset_id"],)) if d.get("dataset_id") else None
    d["dataset_name"] = ds["name"] if ds else None
    d["stale"] = bool(ds and d.get("source_version") and ds["version"] != d["source_version"])
    return d


def frames(user: CurrentUser, d: dict) -> dict[int | None, pd.DataFrame]:
    out = {None: store.analytic_frame(user, d["dataset_id"])}
    for i in d.get("linked_ids", []):
        try:
            out[i] = store.analytic_frame(user, i)
        except Exception:  # noqa: BLE001 — a deleted linked sheet only removes its page content
            continue
    return out


def update_meta(user: CurrentUser, dashboard_id: int, *, name: str | None = None, theme: str | None = None, branding: dict | None = None) -> None:
    d = _get(dashboard_id)
    require(user, "dashboard.edit", d["project_id"])
    if theme and theme not in THEMES:
        raise GenerationError(f"Unknown theme '{theme}'.")
    cur = db.loads(d.get("branding_json"), {}) or {}
    if branding is not None:
        cur.update(branding)
    if name:
        cur["title"] = cur.get("title") or name
    db.execute("UPDATE dashboards SET name=COALESCE(?, name), theme=COALESCE(?, theme), branding_json=?, updated_at=? WHERE id=?",
               (name, theme, db.dumps(cur), db.now(), dashboard_id))
    audit.log(user.username, "DASHBOARD_UPDATED", ", ".join(k for k, v in (("name", name), ("theme", theme), ("branding", branding)) if v),
              project_id=d["project_id"], object_type="dashboard", object_id=dashboard_id)


def refresh(user: CurrentUser, dashboard_id: int) -> int:
    """Re-run the analysis on the current data. The previous specification stays available as a version."""
    d = _get(dashboard_id)
    require(user, "dashboard.edit", d["project_id"])
    if not d.get("dataset_id"):
        raise GenerationError("The dataset behind this dashboard no longer exists.")
    res = build_for(user, d["dataset_id"])
    res["spec"]["theme"] = d.get("theme") or "corporate"
    version = d["version"] + 1
    db.execute("UPDATE dashboards SET spec_json=?, plan_json=?, version=?, linked_json=?, source_version=?, generated_at=?, updated_at=? WHERE id=?",
               (db.dumps(res["spec"]), db.dumps(res["plan"]), version, db.dumps(res["linked_ids"]), res["version"], db.now(), db.now(), dashboard_id))
    db.execute("INSERT INTO dashboard_versions(dashboard_id, version, spec_json, note, created_by, created_at) VALUES(?,?,?,?,?,?)",
               (dashboard_id, version, db.dumps(res["spec"]), "Regenerated from the current data", user.id, db.now()))
    audit.log(user.username, "DASHBOARD_REFRESHED", f"v{version}", project_id=d["project_id"], object_type="dashboard", object_id=dashboard_id)
    return version


def list_for_project(user: CurrentUser, project_id: int) -> list[dict]:
    require(user, "project.view", project_id)
    rows = db.query("SELECT d.id, d.name, d.mode, d.theme, d.version, d.updated_at, d.generated_at, d.source_version, d.dataset_id,"
                    " s.name AS dataset_name, s.version AS dataset_version FROM dashboards d LEFT JOIN datasets s ON s.id=d.dataset_id"
                    " WHERE d.project_id=? AND d.is_template=0 ORDER BY d.updated_at DESC", (project_id,))
    for r in rows:
        r["stale"] = bool(r.get("source_version") and r.get("dataset_version") and r["source_version"] != r["dataset_version"])
    return rows


# ---------------------------------------------------------------- logos

def _sniff_image(data: bytes) -> str:
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    if data[:3] == b"\xff\xd8\xff":
        return ".jpg"
    raise GenerationError("The logo must be a PNG or JPEG image.")


def save_logo(user: CurrentUser, *, org_id: int | None = None, project_id: int | None = None, data: bytes) -> str:
    """Store a logo supplied by the user (organisation or dashboard level). Lucerna never supplies logos itself."""
    if org_id:
        require(user, "org.manage", org_id=org_id)
    elif project_id:
        require(user, "dashboard.edit", project_id)
    else:
        raise GenerationError("A logo belongs to an organisation or a project.")
    if not data or len(data) > LOGO_MAX_BYTES:
        raise GenerationError("The logo must be smaller than 1 MB.")
    ext = _sniff_image(data)
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(data))
        img.verify()
    except Exception as exc:  # noqa: BLE001
        raise GenerationError("The logo file could not be read as an image.") from exc
    folder = settings().data_dir / "branding"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{'org' if org_id else 'project'}_{org_id or project_id}_{secrets.token_hex(6)}{ext}"
    path.write_bytes(data)
    if org_id:
        db.execute("UPDATE organizations SET logo_path=?, updated_at=? WHERE id=?", (str(path), db.now(), org_id))
    audit.log(user.username, "LOGO_UPLOADED", path.name, org_id=org_id, project_id=project_id)
    return str(path)


def logo_bytes(d: dict) -> bytes | None:
    b = d.get("branding") or {}
    path = None
    if b.get("logo") == "custom" and b.get("logo_path"):
        path = b["logo_path"]
    elif b.get("logo", "org") == "org":
        r = db.query_one("SELECT o.logo_path FROM organizations o JOIN projects p ON p.org_id=o.id WHERE p.id=?", (d["project_id"],))
        path = (r or {}).get("logo_path")
    if path and Path(path).exists() and Path(path).resolve().is_relative_to(settings().data_dir.resolve()):
        return Path(path).read_bytes()
    return None


def org_identity(project_id: int) -> dict:
    r = db.query_one("SELECT o.name, o.short_name, p.name AS project FROM organizations o JOIN projects p ON p.org_id=o.id WHERE p.id=?", (project_id,))
    return r or {}


def compute_visual(d: dict, v: dict, frames: dict, flt: dict | None = None, drill: list | None = None) -> tuple:
    """Compute one visual exactly as the viewer shows it: (VisualData | None, explanation | None, error | None, effective visual).

    Filters apply only to columns present in the visual's source table; drill-down narrows the data and moves the x
    variable one level down the visual's hierarchy. One broken visual never breaks the page.
    """
    from . import charts, explain
    flt, drill = flt or {}, drill or []
    full = frames.get(v.get("ds"), frames[None]) if v.get("ds") else frames[None]
    df = charts.apply_filters(full, {c: f for c, f in flt.items() if c in full.columns})
    vv = dict(v)
    for col, val in drill:
        df = df[df[col].astype("string") == val]
    if drill and v.get("drill"):
        vv["x"] = v["drill"][min(len(drill), len(v["drill"]) - 1)]
    try:
        data = charts.compute(df, vv, full)
        ex = explain.explain(vv, data, d["plan"], df, flt) if v["type"] not in ("text", "methodology") else None
        return data, ex, None, vv
    except charts.Unsupported as e:
        return None, None, str(e), vv
    except Exception as e:  # noqa: BLE001
        return None, None, f"This visual could not be computed: {e}", vv
