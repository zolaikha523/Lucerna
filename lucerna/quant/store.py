"""Quantitative service layer (permission-checked persistence for datasets, mappings,
transformations and indicators)."""
from __future__ import annotations

import secrets
from functools import lru_cache
from pathlib import Path

import pandas as pd

from .. import db
from ..config import settings
from ..security import audit
from ..security.rbac import CurrentUser, PermissionDenied, require
from ..services import files
from . import ingest, profile, quality, transform, workbook
from .indicators import IndicatorDef, compute, validate_definition


class DatasetError(Exception):
    pass


def _write_parquet(df: pd.DataFrame, project_id: int, tag: str) -> str:
    folder = settings().analytic_dir / f"project_{int(project_id)}"
    folder.mkdir(parents=True, exist_ok=True)
    p = folder / f"{tag}_{secrets.token_hex(8)}.parquet"
    df.to_parquet(p, index=False)
    return str(p)


@lru_cache(maxsize=32)
def _read_parquet_cached(path: str, mtime: float) -> pd.DataFrame:
    return pd.read_parquet(path)


def _read_parquet(path: str) -> pd.DataFrame:
    p = Path(path)
    if not p.exists():
        raise DatasetError("The stored dataset file is missing from the data directory.")
    return _read_parquet_cached(str(p), p.stat().st_mtime).copy()


def import_file(user: CurrentUser, project_id: int, filename: str, data: bytes, *, round_label: str = "", period_label: str = "") -> list[int]:
    """Store the original upload, parse all tables, profile each, create one dataset per table."""
    require(user, "data.upload", project_id)
    f = files.store_upload(user, project_id, filename, data, "quantitative")
    tables = ingest.read_tables(data, filename)
    wb = workbook.analyse({t.name: t.frame for t in tables}) if len(tables) > 1 else None
    if wb:
        db.execute("UPDATE data_files SET workbook_json=? WHERE id=?", (db.dumps(wb), f["id"]))
    roles = {s_["name"]: s_ for s_ in (wb or {}).get("sheets", [])}
    ids = []
    for t in tables:
        raw = t.frame.astype(object).where(t.frame.notna(), None)
        raw = raw.map(lambda v: None if v is None else str(v))
        prof = profile.profile_dataframe(raw)
        prof["ingest_notes"] = t.notes
        original_path = _write_parquet(raw, project_id, "original")
        name = Path(filename).stem + ("" if len(tables) == 1 else f" — {t.name}")
        sector = prof["sector_candidates"][0][0] if prof["sector_candidates"] else None
        with db.transaction() as con:
            cur = con.execute(
                "INSERT INTO datasets(project_id, data_file_id, name, source_table, original_path, row_count, column_count,"
                " unit_of_analysis, sector_guess, round_label, period_label, profile_json, status, created_by, created_at, updated_at)"
                " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (project_id, f["id"], name, t.name, original_path, len(raw), raw.shape[1], prof["unit_of_analysis"]["value"],
                 sector, round_label or None, period_label or None, db.dumps(prof), "uploaded", user.id, db.now(), db.now()))
            did = cur.lastrowid
            for c in prof["columns"]:
                con.execute("INSERT INTO dataset_columns(dataset_id, name, position, inferred_type, inferred_role, confidence, final_type, final_role, confirmed, notes)"
                            " VALUES(?,?,?,?,?,?,?,?,0,?)",
                            (did, c["name"], c["position"], c["inferred_type"], c["inferred_role"], c["confidence"],
                             c["inferred_type"], c["inferred_role"], "; ".join(c["reasons"])))
        r = roles.get(t.name)
        if r:
            db.execute("UPDATE datasets SET sheet_role=?, sheet_role_json=?, is_primary=? WHERE id=?",
                       (r["role"], db.dumps({k: r[k] for k in ("confidence", "reasons", "score", "role_label")}), int(r["is_primary"]), did))
        else:
            db.execute("UPDATE datasets SET sheet_role='survey', is_primary=1 WHERE id=?", (did,))
        rebuild_analytic(user, did)
        audit.log(user.username, "DATASET_CREATED", f"dataset #{did}: {len(raw)} rows × {raw.shape[1]} columns", project_id=project_id,
                  object_type="dataset", object_id=did)
        ids.append(did)
    if wb:
        _apply_codebook_labels(wb, tables, dict(zip([t.name for t in tables], ids)))
        audit.log(user.username, "WORKBOOK_ANALYSED", f"primary sheet: {wb.get('primary')}; {len(tables)} sheets", project_id=project_id,
                  object_type="data_file", object_id=f["id"])
    # the primary sheet's dataset comes first so callers that take ids[0] get the analytical data, not a README or codebook
    if wb and wb.get("primary"):
        prim = dict(zip([t.name for t in tables], ids)).get(wb["primary"])
        ids = [prim] + [i for i in ids if i != prim]
    return ids


def _apply_codebook_labels(wb: dict, tables: list, ids_by_sheet: dict[str, int]) -> None:
    """Use codebook sheets to label variables of the analytical sheets (labels only; data unchanged)."""
    frames = {t.name: t.frame for t in tables}
    books = [s_["name"] for s_ in wb["sheets"] if s_["role"] == "codebook"]
    for s_ in wb["sheets"]:
        if s_["role"] not in workbook.ANALYTICAL_ROLES:
            continue
        did = ids_by_sheet[s_["name"]]
        cols = [r["name"] for r in db.query("SELECT name FROM dataset_columns WHERE dataset_id=?", (did,))]
        for b in books:
            for col, lab in workbook.codebook_labels(frames[b], cols, s_["name"]).items():
                db.execute("UPDATE dataset_columns SET label=COALESCE(label, ?) WHERE dataset_id=? AND name=?", (lab, did, col))


def workbook_info(user: CurrentUser, dataset_id: int) -> dict | None:
    d = get_dataset(user, dataset_id)
    if not d.get("data_file_id"):
        return None
    r = db.query_one("SELECT workbook_json FROM data_files WHERE id=?", (d["data_file_id"],))
    wb = db.loads((r or {}).get("workbook_json"), None)
    if not wb:
        return None
    sib = db.query("SELECT id, source_table, sheet_role, is_primary, row_count FROM datasets WHERE data_file_id=?", (d["data_file_id"],))
    wb["dataset_ids"] = {x["source_table"]: x["id"] for x in sib}
    return wb


def labels(dataset_id: int) -> dict[str, str]:
    return {r["name"]: r["label"] for r in db.query("SELECT name, label FROM dataset_columns WHERE dataset_id=? AND label IS NOT NULL AND label<>''", (dataset_id,))}


def get_dataset(user: CurrentUser, dataset_id: int) -> dict:
    d = db.query_one("SELECT * FROM datasets WHERE id=?", (dataset_id,))
    if not d:
        raise DatasetError("Dataset not found.")
    require(user, "project.view", d["project_id"])
    d["profile"] = db.loads(d.get("profile_json"), {})
    d["quality"] = db.loads(d.get("quality_json"), None)
    return d


def list_datasets(user: CurrentUser, project_id: int) -> list[dict]:
    require(user, "project.view", project_id)
    return db.query("SELECT id, name, source_table, row_count, column_count, unit_of_analysis, unit_confirmed, sector_guess, sector_confirmed,"
                    " round_label, period_label, status, version, created_at, data_file_id, sheet_role, is_primary FROM datasets WHERE project_id=?"
                    " ORDER BY COALESCE(data_file_id, 0) DESC, is_primary DESC, id", (project_id,))


def columns(user: CurrentUser, dataset_id: int) -> list[dict]:
    get_dataset(user, dataset_id)
    return db.query("SELECT * FROM dataset_columns WHERE dataset_id=? ORDER BY position", (dataset_id,))


def mapping(dataset_id: int) -> dict[str, dict]:
    return {r["name"]: {"type": r["final_type"], "role": r["final_role"], "confirmed": bool(r["confirmed"]), "label": r["label"]}
            for r in db.query("SELECT * FROM dataset_columns WHERE dataset_id=? ORDER BY position", (dataset_id,))}


def update_mapping(user: CurrentUser, dataset_id: int, changes: dict[str, dict], *, confirm_all: bool = False,
                   unit_of_analysis: str | None = None, sector: str | None = None) -> None:
    d = get_dataset(user, dataset_id)
    require(user, "data.transform", d["project_id"])
    with db.transaction() as con:
        for name, ch in changes.items():
            con.execute("UPDATE dataset_columns SET final_type=COALESCE(?, final_type), final_role=COALESCE(?, final_role),"
                        " label=COALESCE(?, label), confirmed=1, confirmed_by=?, confirmed_at=? WHERE dataset_id=? AND name=?",
                        (ch.get("type"), ch.get("role"), ch.get("label"), user.id, db.now(), dataset_id, name))
        if confirm_all:
            con.execute("UPDATE dataset_columns SET confirmed=1, confirmed_by=?, confirmed_at=? WHERE dataset_id=? AND confirmed=0",
                        (user.id, db.now(), dataset_id))
        if unit_of_analysis:
            con.execute("UPDATE datasets SET unit_of_analysis=?, unit_confirmed=1 WHERE id=?", (unit_of_analysis, dataset_id))
        if sector:
            con.execute("UPDATE datasets SET sector_confirmed=? WHERE id=?", (sector, dataset_id))
        con.execute("UPDATE datasets SET status=CASE WHEN status='uploaded' THEN 'mapped' ELSE status END, updated_at=? WHERE id=?", (db.now(), dataset_id))
    audit.log(user.username, "MAPPING_UPDATED", f"{len(changes)} column(s); confirm_all={confirm_all}", project_id=d["project_id"],
              object_type="dataset", object_id=dataset_id)
    rebuild_analytic(user, dataset_id)


def original_frame(user: CurrentUser, dataset_id: int) -> pd.DataFrame:
    return _read_parquet(get_dataset(user, dataset_id)["original_path"])


def analytic_frame(user: CurrentUser, dataset_id: int) -> pd.DataFrame:
    d = get_dataset(user, dataset_id)
    if not d.get("analytic_path"):
        rebuild_analytic(user, dataset_id)
        d = get_dataset(user, dataset_id)
    return _read_parquet(d["analytic_path"])


def transformations(dataset_id: int) -> list[dict]:
    rows = db.query("SELECT * FROM transformations WHERE dataset_id=? ORDER BY seq", (dataset_id,))
    for r in rows:
        r["params"] = db.loads(r.get("params_json"), {})
    return rows


def rebuild_analytic(user: CurrentUser, dataset_id: int) -> dict:
    """Recreate the analytical copy from the original + confirmed mapping + approved/applied transformations."""
    d = db.query_one("SELECT * FROM datasets WHERE id=?", (dataset_id,))
    require(user, "project.view", d["project_id"])
    raw = _read_parquet(d["original_path"])
    typed = transform.apply_types(raw, mapping(dataset_id))
    ops = [{"id": t["id"], "operation": t["operation"], "params": t["params"]} for t in transformations(dataset_id) if t["status"] in ("approved", "applied")]
    df, stats = transform.apply_operations(typed, ops)
    path = _write_parquet(df, d["project_id"], "analytic")
    old = d.get("analytic_path")
    with db.transaction() as con:
        con.execute("UPDATE datasets SET analytic_path=?, version=version+1, updated_at=?, row_count=? WHERE id=?", (path, db.now(), len(df), dataset_id))
        for s in stats:
            con.execute("UPDATE transformations SET status='applied', rows_affected=?, cells_affected=?, applied_at=? WHERE id=?",
                        (s["rows_affected"], s["cells_affected"], db.now(), s["id"]))
    if old and old != path and Path(old).exists():
        Path(old).unlink()
    return {"rows": len(df), "applied": stats}


def run_quality(user: CurrentUser, dataset_id: int) -> dict:
    d = get_dataset(user, dataset_id)
    df = analytic_frame(user, dataset_id)
    mp = mapping(dataset_id)
    ids = [c for c, m in mp.items() if m["role"] == "identifier" and c in df.columns]
    q = quality.assess(df, mp, ids)
    q["computed_on_version"] = d["version"]
    db.execute("UPDATE datasets SET quality_json=? WHERE id=?", (db.dumps(q), dataset_id))
    return q


def propose_transformation(user: CurrentUser, dataset_id: int, operation: str, params: dict, description: str = "") -> int:
    d = get_dataset(user, dataset_id)
    require(user, "data.transform", d["project_id"])
    if operation not in transform.OPERATIONS:
        raise DatasetError(f"Unknown operation {operation}")
    seq = (db.query_one("SELECT COALESCE(MAX(seq),0) m FROM transformations WHERE dataset_id=?", (dataset_id,))["m"]) + 1
    tid = db.execute("INSERT INTO transformations(dataset_id, seq, operation, params_json, description, status, created_by, created_at)"
                     " VALUES(?,?,?,?,?,'proposed',?,?)",
                     (dataset_id, seq, operation, db.dumps(params), description or transform.OPERATIONS[operation][1], user.id, db.now()))
    audit.log(user.username, "TRANSFORMATION_PROPOSED", f"{operation}", project_id=d["project_id"], object_type="transformation", object_id=tid)
    return tid


def preview_transformation(user: CurrentUser, dataset_id: int, operation: str, params: dict) -> dict:
    df = analytic_frame(user, dataset_id)
    after, stats = transform.apply_operations(df, [{"operation": operation, "params": params}])
    return {"rows_before": len(df), "rows_after": len(after), **stats[0]}


def decide_transformation(user: CurrentUser, transformation_id: int, approve: bool) -> None:
    t = db.query_one("SELECT t.*, d.project_id FROM transformations t JOIN datasets d ON d.id=t.dataset_id WHERE t.id=?", (transformation_id,))
    if not t:
        raise DatasetError("Transformation not found.")
    require(user, "data.transform", t["project_id"])
    if approve:
        db.execute("UPDATE transformations SET status='approved', approved_by=?, approved_at=? WHERE id=?", (user.id, db.now(), transformation_id))
    else:
        db.execute("UPDATE transformations SET status=CASE WHEN status IN ('applied','approved') THEN 'reverted' ELSE 'rejected' END WHERE id=?", (transformation_id,))
    audit.log(user.username, "TRANSFORMATION_APPROVED" if approve else "TRANSFORMATION_REJECTED_OR_REVERTED", t["operation"],
              project_id=t["project_id"], object_type="transformation", object_id=transformation_id)
    rebuild_analytic(user, t["dataset_id"])
    db.execute("UPDATE datasets SET status='cleaned' WHERE id=? AND status IN ('uploaded','mapped')", (t["dataset_id"],))


def delete_dataset(user: CurrentUser, dataset_id: int) -> None:
    d = get_dataset(user, dataset_id)
    require(user, "data.delete", d["project_id"])
    for p in (d.get("original_path"), d.get("analytic_path")):
        if p:
            files.secure_delete(Path(p))
    db.execute("DELETE FROM datasets WHERE id=?", (dataset_id,))
    audit.log(user.username, "DATASET_DELETED", f"dataset #{dataset_id}", "WARNING", project_id=d["project_id"])


# ----------------------------------------------------------- indicators

def _row_to_def(r: dict) -> IndicatorDef:
    return IndicatorDef(name=r["name"], indicator_type=r["indicator_type"], numerator=db.loads(r.get("numerator_json")),
                        denominator=db.loads(r.get("denominator_json")), value_column=r.get("value_column"),
                        ratio_denominator_column=(db.loads(r.get("numerator_json"), {}) or {}).get("ratio_denominator_column") if r["indicator_type"] == "ratio" else None,
                        disaggregations=db.loads(r.get("disaggregations"), []) or [], unit=r.get("unit"),
                        target=r.get("target"), baseline=r.get("baseline"))


def save_indicator(user: CurrentUser, project_id: int, data: dict, indicator_id: int | None = None) -> int:
    require(user, "indicator.manage", project_id)
    if not (data.get("name") or "").strip():
        raise DatasetError("Indicator name is required.")
    status = "provisional"
    if data.get("dataset_id"):
        df = analytic_frame(user, int(data["dataset_id"]))
        d = IndicatorDef(name=data["name"], indicator_type=data["indicator_type"], numerator=data.get("numerator"),
                         denominator=data.get("denominator"), value_column=data.get("value_column"),
                         ratio_denominator_column=data.get("ratio_denominator_column"), disaggregations=data.get("disaggregations") or [])
        status = "configured" if not validate_definition(d, df) and data.get("definition") else "provisional"
    num = data.get("numerator")
    if data.get("indicator_type") == "ratio":
        num = {"ratio_denominator_column": data.get("ratio_denominator_column")}
    vals = (data.get("dataset_id"), data.get("code"), data["name"].strip(), data.get("definition"), data["indicator_type"], data.get("unit"),
            db.dumps(num) if num else None, db.dumps(data.get("denominator")) if data.get("denominator") else None,
            data.get("value_column"), db.dumps(data.get("disaggregations") or []),
            data.get("baseline"), data.get("baseline_source"), data.get("target"), data.get("target_source"),
            data.get("reporting_period"), data.get("data_source"), data.get("responsible"), data.get("calculation_notes"), status)
    if indicator_id:
        old = db.query_one("SELECT project_id FROM indicators WHERE id=?", (indicator_id,))
        if not old or old["project_id"] != project_id:
            raise PermissionDenied("Indicator does not belong to this project.")
        db.execute("UPDATE indicators SET dataset_id=?, code=?, name=?, definition=?, indicator_type=?, unit=?, numerator_json=?, denominator_json=?,"
                   " value_column=?, disaggregations=?, baseline=?, baseline_source=?, target=?, target_source=?, reporting_period=?, data_source=?,"
                   " responsible=?, calculation_notes=?, status=?, verified_by=NULL, verified_at=NULL, updated_at=? WHERE id=?",
                   (*vals, db.now(), indicator_id))
        iid = indicator_id
    else:
        iid = db.execute("INSERT INTO indicators(dataset_id, code, name, definition, indicator_type, unit, numerator_json, denominator_json, value_column,"
                         " disaggregations, baseline, baseline_source, target, target_source, reporting_period, data_source, responsible, calculation_notes,"
                         " status, origin, project_id, created_by, created_at, updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                         (*vals, data.get("origin", "manual"), project_id, user.id, db.now(), db.now()))
    audit.log(user.username, "INDICATOR_SAVED", data["name"][:80], project_id=project_id, object_type="indicator", object_id=iid)
    return iid


def list_indicators(user: CurrentUser, project_id: int) -> list[dict]:
    require(user, "project.view", project_id)
    rows = db.query("SELECT * FROM indicators WHERE project_id=? ORDER BY code, name", (project_id,))
    for r in rows:
        r["numerator"] = db.loads(r.get("numerator_json"))
        r["denominator"] = db.loads(r.get("denominator_json"))
        r["disaggregation_list"] = db.loads(r.get("disaggregations"), [])
    return rows


def verify_indicator(user: CurrentUser, indicator_id: int) -> None:
    r = db.query_one("SELECT * FROM indicators WHERE id=?", (indicator_id,))
    require(user, "indicator.verify", r["project_id"])
    if r["status"] == "provisional":
        raise DatasetError("A provisional indicator cannot be verified: complete its definition and data mapping first.")
    db.execute("UPDATE indicators SET status='verified', verified_by=?, verified_at=? WHERE id=?", (user.id, db.now(), indicator_id))
    audit.log(user.username, "INDICATOR_VERIFIED", r["name"][:80], project_id=r["project_id"], object_type="indicator", object_id=indicator_id)


def compute_indicator(user: CurrentUser, indicator_id: int) -> dict:
    r = db.query_one("SELECT * FROM indicators WHERE id=?", (indicator_id,))
    if not r:
        raise DatasetError("Indicator not found.")
    require(user, "project.view", r["project_id"])
    if not r.get("dataset_id"):
        raise DatasetError("This indicator is not linked to a dataset.")
    d = get_dataset(user, r["dataset_id"])
    res = compute(_row_to_def(r), analytic_frame(user, r["dataset_id"]))
    res["status"] = r["status"]
    res["dataset_version"] = d["version"]
    db.execute("INSERT INTO indicator_results(indicator_id, dataset_id, dataset_version, computed_at, value, numerator, denominator, n_valid, n_missing, disaggregation_json, config_hash)"
               " VALUES(?,?,?,?,?,?,?,?,?,?,?)",
               (indicator_id, r["dataset_id"], d["version"], db.now(), res.get("value"), res.get("numerator"), res.get("denominator"),
                res.get("n_valid"), res.get("n_missing"), db.dumps(res.get("disaggregations")), res["config_hash"]))
    return res


def delete_indicator(user: CurrentUser, indicator_id: int) -> None:
    r = db.query_one("SELECT * FROM indicators WHERE id=?", (indicator_id,))
    require(user, "indicator.manage", r["project_id"])
    db.execute("DELETE FROM indicators WHERE id=?", (indicator_id,))
    audit.log(user.username, "INDICATOR_DELETED", r["name"][:80], project_id=r["project_id"])
