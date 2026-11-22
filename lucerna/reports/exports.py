"""Data and chart exports with Humanitarian Data Protection options (pseudonymisation, PII column
removal, geographic precision)."""
from __future__ import annotations

import hashlib
import hmac
import io

import pandas as pd

from ..security import audit
from ..security.rbac import CurrentUser, require
from ..services.bootstrap import get_setting


def _project_salt(project_id: int) -> bytes:
    key = f"pseudonym_salt_{project_id}"
    v = get_setting(key)
    if not v:
        import secrets
        v = secrets.token_hex(16)
        from ..services.bootstrap import set_setting
        set_setting(key, v, "system")
    return bytes.fromhex(v)


def protect(df: pd.DataFrame, mapping: dict, project_id: int, *, pseudonymize: bool | None = None, drop_pii: bool = True,
            geo_precision: str | None = None) -> tuple[pd.DataFrame, list[str]]:
    notes = []
    out = df.copy()
    pseudonymize = (get_setting("privacy.pseudonymize_exports", "0") == "1") if pseudonymize is None else pseudonymize
    geo_precision = geo_precision or get_setting("privacy.geo_precision", "admin2")
    if drop_pii:
        pii_cols = [c for c, m in mapping.items() if m.get("role") in ("personal_name", "phone") and c in out]
        if pii_cols:
            out = out.drop(columns=pii_cols)
            notes.append(f"Removed personal-identifier columns: {', '.join(pii_cols)}")
    if pseudonymize:
        salt = _project_salt(project_id)
        for c, m in mapping.items():
            if m.get("role") == "identifier" and c in out:
                out[c] = out[c].map(lambda v: None if pd.isna(v) else "P-" + hmac.new(salt, str(v).encode(), hashlib.sha256).hexdigest()[:12])
                notes.append(f"Pseudonymised identifier '{c}' (keyed hash; consistent within this project)")
    lat = [c for c, m in mapping.items() if m.get("role") in ("latitude", "longitude") and c in out]
    if lat:
        if geo_precision == "exact":
            pass
        elif geo_precision == "approx_1km":
            for c in lat:
                out[c] = out[c].round(2)
            notes.append("Coordinates rounded to 2 decimals (~1 km)")
        else:
            out = out.drop(columns=lat)
            notes.append("GPS coordinates removed (geographic precision limited to administrative areas)")
        if geo_precision == "admin1":
            for c, m in mapping.items():
                if m.get("role") in ("geo_admin2", "geo_admin3") and c in out:
                    out = out.drop(columns=c)
            notes.append("Sub-province location columns removed (admin1 precision)")
    return out, notes


def dataset_export(user: CurrentUser, dataset_id: int, fmt: str, **protect_kw) -> tuple[bytes, list[str]]:
    from ..quant import store
    d = store.get_dataset(user, dataset_id)
    require(user, "export", d["project_id"])
    df, notes = protect(store.analytic_frame(user, dataset_id), store.mapping(dataset_id), d["project_id"], **protect_kw)
    buf = io.BytesIO()
    if fmt == "csv":
        buf.write(df.to_csv(index=False).encode("utf-8-sig"))
    else:
        with pd.ExcelWriter(buf, engine="openpyxl") as xw:
            df.to_excel(xw, sheet_name="data", index=False)
            pd.DataFrame({"export_notes": notes or ["No protection transformations applied"]}).to_excel(xw, sheet_name="export_notes", index=False)
    audit.log(user.username, "DATASET_EXPORTED", f"#{dataset_id} {fmt}; {len(df)} rows; {'; '.join(notes)}", "WARNING", project_id=d["project_id"], object_type="dataset", object_id=dataset_id)
    return buf.getvalue(), notes


def report_workbook(user: CurrentUser, report: dict, content: dict, path: str) -> str:
    with pd.ExcelWriter(path, engine="openpyxl") as xw:
        n = 0
        for s in content["sections"]:
            if not s.get("included", True):
                continue
            for b in s["blocks"]:
                if b["kind"] == "table" and b["rows"]:
                    n += 1
                    name = f"{n:02d} {s['title']}"[:31].replace("/", "-").replace(":", "")
                    pd.DataFrame(b["rows"], columns=[str(c) for c in b["columns"]]).to_excel(xw, sheet_name=name, index=False)
        if report["kind"] in ("qualitative", "mixed"):
            from ..qual import store as qstore
            reg = qstore.verified_register(user, report["project_id"], approved_only=True)
            pd.DataFrame([{"quotation": q["verified_text"], "document": q["document_code"], "segment": q["segment_code"], "speaker": q.get("speaker"),
                           "doc_type": q.get("doc_type"), "location": q.get("location"), "method": q["verification_method"], "translation": q.get("translation_text")}
                          for q in reg] or [{"quotation": "No approved verified quotations"}]).to_excel(xw, sheet_name="Verified quotations", index=False)
        if n == 0 and report["kind"] == "quantitative":
            pd.DataFrame({"note": ["No tables in this report"]}).to_excel(xw, sheet_name="Info", index=False)
    return path


def chart_export(df, visual: dict, fmt: str = "png") -> bytes:
    import tempfile, os
    from ..quant import charts
    from . import static_charts
    data = charts.compute(df, visual)
    with tempfile.TemporaryDirectory() as td:
        p = os.path.join(td, f"chart.{fmt}")
        if not static_charts.render(visual, data, p, fmt):
            raise charts.Unsupported("This visual type has no static export; export its data table instead.")
        return open(p, "rb").read()
