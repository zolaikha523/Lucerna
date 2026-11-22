"""Quantitative pages: data library, understanding/mapping, quality & cleaning, statistics, indicators."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from ...quant import counting, indicators, stats, store, transform
from ...quant.profile import SECTOR_KEYWORDS
from ...reports import exports, powerbi
from ...services.files import QUANT_EXT as QUANT_EXTENSIONS
from .. import common, theme

TYPES = ["categorical", "numeric", "integer", "date", "boolean", "string", "ignore"]
ROLES = ["category", "binary", "multiselect", "measure", "score", "identifier", "personal_name", "phone", "sex", "age", "age_group",
         "household_size", "geo_admin1", "geo_admin2", "geo_admin3", "geo_origin", "geo_destination", "latitude", "longitude",
         "date", "round", "weight", "free_text", "empty"]
UNITS = list(counting.UNIT_LABELS)
OPS = ["in", "not_in", "==", "!=", ">", ">=", "<", "<=", "notnull", "isnull", "contains"]


def pick_dataset(u, pid: int, label: str = "Dataset", key: str = "dataset_id") -> dict | None:
    rows = store.list_datasets(u, pid)
    if not rows:
        theme.empty_state("No datasets yet", "Upload a dataset in the Data Library to begin.", "database")
        return None
    ids = [r["id"] for r in rows]
    cur = st.session_state.get(key)
    names = {r["id"]: f"{r['name']}  ·  {r['row_count']:,} rows" for r in rows}
    sel = st.selectbox(label, ids, index=ids.index(cur) if cur in ids else 0, format_func=names.get, key=f"pick_{key}")
    st.session_state[key] = sel
    return store.get_dataset(u, sel)


def condition_editor(cols: list[str], key: str, default: dict | None = None, label: str = "Condition") -> dict | None:
    default = default or {}
    c1, c2, c3 = st.columns([3, 2, 3])
    col = c1.selectbox(f"{label}: column", cols, index=cols.index(default["column"]) if default.get("column") in cols else 0, key=f"{key}_c")
    op = c2.selectbox("Operator", OPS, index=OPS.index(default.get("op", "in")), key=f"{key}_o")
    raw = c3.text_input("Value(s), comma-separated", value=", ".join(map(str, default.get("value") or [])) if isinstance(default.get("value"), list)
                        else str(default.get("value") or ""), key=f"{key}_v", disabled=op in ("notnull", "isnull"))
    if op in ("in", "not_in"):
        val = [x.strip() for x in raw.split(",") if x.strip()]
    else:
        val = raw.strip()
    return {"column": col, "op": op, "value": val}


# ---------------------------------------------------------------- Data Library

def library() -> None:
    u = common.cu()
    theme.page_header("Data Library", "Upload survey, monitoring and registration data. Originals are kept unchanged; all cleaning happens on an analytical copy.", "database")
    p = common.need_project(u)
    if not p:
        return
    pid = p["id"]
    if common.can(u, "data.upload"):
        with st.expander("Upload data", icon=":material/upload:", expanded=not store.list_datasets(u, pid)):
            st.caption(f"Accepted: {', '.join(sorted(QUANT_EXTENSIONS))}. Workbooks with several sheets, and sheets with several tables separated by blank rows, "
                       "become separate datasets. The file is validated (type, size, content) before it is stored.")
            with st.form("upload_q", clear_on_submit=True):
                f = st.file_uploader("File", type=[e.strip(".") for e in QUANT_EXTENSIONS])
                c1, c2 = st.columns(2)
                rnd = c1.text_input("Round / wave (optional)", placeholder="e.g. Round 1, Baseline")
                per = c2.text_input("Period (optional)", placeholder="e.g. Jan–Mar 2026")
                if st.form_submit_button("Upload and profile", type="primary") and f is not None:
                    with common.guard(), st.spinner("Reading, validating and profiling…"):
                        ids = store.import_file(u, pid, f.name, f.getvalue(), round_label=rnd, period_label=per)
                        st.session_state["dataset_id"] = ids[0]
                        st.success(f"Imported {len(ids)} dataset(s). Next: confirm the data understanding.")
    rows = store.list_datasets(u, pid)
    if not rows:
        theme.empty_state("No datasets yet", "Upload an Excel, CSV, JSON, Word or PDF table to start the quantitative workflow.", "file-spreadsheet")
        return
    df = pd.DataFrame(rows)
    df["unit"] = df.apply(lambda r: (r["unit_of_analysis"] or "unknown") + ("" if r["unit_confirmed"] else " (unconfirmed)"), axis=1)
    df["sector"] = df["sector_confirmed"].fillna(df["sector_guess"])
    from ...quant.workbook import ROLE_LABELS
    df["role"] = df.apply(lambda r: ROLE_LABELS.get(r.get("sheet_role") or "survey", "") + (" · main sheet" if r.get("is_primary") and r.get("sheet_role") else ""), axis=1)
    common.table(df, {"name": "Dataset", "role": "Sheet type", "row_count": "Rows", "column_count": "Columns", "unit": "Unit of analysis", "sector": "Sector",
                      "round_label": "Round", "period_label": "Period", "status": "Status", "version": "Version", "created_at": "Uploaded"})
    d = pick_dataset(u, pid)
    if not d:
        return
    from .studio import workbook_panel
    workbook_panel(u, d["id"])
    tabs = st.tabs(["Preview", "Original vs analytical copy", "Export", "Manage"])
    with tabs[0]:
        st.dataframe(store.analytic_frame(u, d["id"]).head(200), width="stretch", height=360)
        notes = (d["profile"] or {}).get("ingest_notes") or []
        for n in notes:
            st.caption(f"Import note: {n}")
    with tabs[1]:
        c1, c2 = st.columns(2)
        c1.markdown("**Original (read-only)**")
        c1.dataframe(store.original_frame(u, d["id"]).head(50), width="stretch", height=300)
        c2.markdown(f"**Analytical copy (version {d['version']})**")
        c2.dataframe(store.analytic_frame(u, d["id"]).head(50), width="stretch", height=300)
    with tabs[2]:
        if not common.can(u, "export"):
            st.info("Your role does not include exporting data.")
        else:
            st.caption("Exports drop columns mapped as personal names or phone numbers by default. Pseudonymisation of identifiers follows the privacy settings.")
            c1, c2, c3 = st.columns(3)
            fmt = c1.selectbox("Format", ["csv", "xlsx"], key="exp_fmt")
            drop = c2.checkbox("Drop direct identifiers (names, phones)", value=True)
            pseudo = c3.checkbox("Pseudonymise identifier columns", value=False)
            if st.button("Prepare export", icon=":material/download:"):
                with common.guard():
                    data, notes = exports.dataset_export(u, d["id"], fmt, drop_pii=drop, pseudonymize=pseudo)
                    st.session_state["ds_export"] = (data, fmt, notes)
            if st.session_state.get("ds_export"):
                data, fmt_, notes = st.session_state["ds_export"]
                for n in notes:
                    st.caption(n)
                st.download_button(f"Download .{fmt_}", data, f"{d['name']}.{fmt_}", key="dl_ds")
            st.divider()
            st.markdown("**Power BI package**")
            st.caption("A ZIP with a star-schema dataset (CSV), Power Query scripts, DAX measures, relationships, a Lucerna theme and build instructions. "
                       "It is not a .pbix file: open Power BI Desktop and follow the README to assemble the report.")
            if st.button("Build Power BI package", icon=":material/inventory_2:"):
                with common.guard(), st.spinner("Building package…"):
                    st.session_state["pbi"] = powerbi.build_package(u, d["id"])
            if st.session_state.get("pbi"):
                st.download_button("Download Power BI package (.zip)", st.session_state["pbi"], f"{d['name']}_powerbi_package.zip", "application/zip")
    with tabs[3]:
        if common.can(u, "data.delete"):
            st.warning("Deleting removes the original file copy, the analytical copy and its transformation history. Reports already generated are kept.")
            confirm = st.text_input("Type the dataset name to confirm deletion", key="del_confirm")
            if st.button("Delete dataset", type="primary", disabled=confirm != d["name"]):
                with common.guard("Dataset deleted"):
                    store.delete_dataset(u, d["id"])
                    st.session_state.pop("dataset_id", None)
                    st.rerun()
        else:
            st.caption("Only a Project Manager can delete datasets.")


# ---------------------------------------------------------------- Understanding & mapping

def understanding() -> None:
    u = common.cu()
    theme.page_header("Data Understanding", "Lucerna proposes what each column means. Nothing is final until you confirm it.", "scan-search")
    p = common.need_project(u)
    if not p:
        return
    d = pick_dataset(u, p["id"])
    if not d:
        return
    prof = d["profile"] or {}
    cols = store.columns(u, d["id"])
    unconfirmed = sum(1 for c in cols if not c["confirmed"])
    needs = sum(1 for c in prof.get("columns", []) if c.get("needs_review"))
    pii = [c["name"] for c in prof.get("columns", []) if c.get("pii_risk")]
    theme.kpi_row([("Rows", f"{d['row_count']:,}", "records in the file", "rows-3"), ("Columns", d["column_count"], f"{unconfirmed} not yet confirmed", "columns-3"),
                   ("Need review", needs, "low-confidence guesses", "triangle-alert", "#B7791F"), ("Possible personal data", len(pii), ", ".join(pii[:3]), "shield-alert", "#d03b3b")])
    st.write("")
    unit_guess = prof.get("unit_of_analysis", {})
    with st.container(border=True):
        st.markdown("**Dataset context**")
        c1, c2 = st.columns(2)
        cur_unit = d.get("unit_of_analysis") or "unknown"
        unit = c1.selectbox("Unit of analysis (what one row represents)", UNITS, index=UNITS.index(cur_unit) if cur_unit in UNITS else UNITS.index("unknown"),
                            format_func=lambda x: f"{x} — {counting.UNIT_LABELS[x]}",
                            help="Counting rules depend on this. Households, individuals and assistance events are never added together.")
        if unit_guess.get("reasons"):
            c1.caption("Suggested because: " + "; ".join(unit_guess["reasons"][:3]) + ("" if d.get("unit_confirmed") else " · not yet confirmed"))
        sectors = list(SECTOR_KEYWORDS) + ["Other / mixed"]
        cur_sector = d.get("sector_confirmed") or d.get("sector_guess")
        sector = c2.selectbox("Sector / dataset type", sectors, index=sectors.index(cur_sector) if cur_sector in sectors else len(sectors) - 1)
        cand = prof.get("sector_candidates") or []
        if cand:
            c2.caption("Detected keywords suggest: " + ", ".join(f"{s} ({sc})" for s, sc in cand[:3]))
    st.markdown("#### Column mapping")
    st.caption("Edit the type and role where the suggestion is wrong. Rows marked ⚠ had low confidence. Mapping changes rebuild the analytical copy; the original file is never changed.")
    pmap = {c["name"]: c for c in prof.get("columns", [])}
    ed = pd.DataFrame([{
        "column": c["name"], "type": c["final_type"] if c["final_type"] in TYPES else "categorical",
        "role": c["final_role"] if c["final_role"] in ROLES else "category", "label": c.get("label") or "",
        "confidence": round(float(c.get("confidence") or 0), 2), "check": "⚠" if pmap.get(c["name"], {}).get("needs_review") else "",
        "personal data": "yes" if pmap.get(c["name"], {}).get("pii_risk") else "", "why": c.get("notes") or "", "confirmed": bool(c["confirmed"]),
        "examples": ", ".join(map(str, (pmap.get(c["name"], {}).get("sample_values") or [])[:3]))} for c in cols])
    edited = st.data_editor(ed, hide_index=True, width="stretch", height=min(620, 40 + 35 * len(ed)), key=f"map_{d['id']}",
                            column_config={"column": st.column_config.TextColumn(disabled=True),
                                           "type": st.column_config.SelectboxColumn(options=TYPES, required=True),
                                           "role": st.column_config.SelectboxColumn(options=ROLES, required=True),
                                           "confidence": st.column_config.ProgressColumn(min_value=0, max_value=1, format="%.2f"),
                                           "check": st.column_config.TextColumn(disabled=True, width="small"),
                                           "personal data": st.column_config.TextColumn(disabled=True, width="small"),
                                           "why": st.column_config.TextColumn("why suggested", disabled=True),
                                           "examples": st.column_config.TextColumn(disabled=True),
                                           "confirmed": st.column_config.CheckboxColumn(disabled=True)})
    if not common.can(u, "data.transform"):
        st.info("Your role can view the mapping but not change it.")
        return
    c1, c2 = st.columns([1, 3])
    if c1.button("Confirm mapping", type="primary", icon=":material/check:"):
        changes = {}
        for (_, a), (_, b) in zip(ed.iterrows(), edited.iterrows()):
            if a["type"] != b["type"] or a["role"] != b["role"] or a["label"] != b["label"]:
                changes[a["column"]] = {"type": b["type"], "role": b["role"], "label": b["label"] or None}
        with common.guard("Mapping confirmed"), st.spinner("Rebuilding analytical copy…"):
            store.update_mapping(u, d["id"], changes, confirm_all=True, unit_of_analysis=unit, sector=sector if sector != "Other / mixed" else None)
            st.rerun()
    c2.caption("Confirming records you as the person who validated the mapping (audited).")


# ---------------------------------------------------------------- Quality & cleaning

def quality() -> None:
    u = common.cu()
    theme.page_header("Quality & Cleaning", "Checks run on the analytical copy. Every fix is proposed, previewed and approved before it is applied — and can be reverted.", "badge-check")
    p = common.need_project(u)
    if not p:
        return
    d = pick_dataset(u, p["id"])
    if not d:
        return
    q = d.get("quality")
    if not q or q.get("computed_on_version") != d["version"] or st.button("Re-run quality checks", icon=":material/refresh:"):
        with st.spinner("Running quality checks…"):
            q = store.run_quality(u, d["id"])
    sev = pd.Series([f["severity"] for f in q["findings"]]).value_counts() if q["findings"] else pd.Series(dtype=int)
    theme.kpi_row([("Completeness", f"{q['completeness_pct']:.1f}%", "non-missing cells", "badge-check"),
                   ("Duplicate rows", q["duplicate_rows"], "exact duplicates", "copy"),
                   ("Duplicate IDs", q["duplicate_ids"], "repeated identifiers", "fingerprint"),
                   ("Errors", int(sev.get("error", 0)), f"{int(sev.get('warning', 0))} warnings", "triangle-alert", "#d03b3b")])
    st.write("")
    t1, t2, t3, t4 = st.tabs(["Findings", "Proposed fixes", "Add a transformation", "Transformation history"])
    with t1:
        if not q["findings"]:
            st.success("No issues were detected by the automated checks. Still review the data for context-specific problems.")
        for f in q["findings"]:
            tone = {"error": "critical", "warning": "warning", "info": "info"}[f["severity"]]
            st.markdown(f"{theme.pill(f['severity'], tone)} **{theme.esc(f.get('column') or 'dataset')}** — {theme.esc(f['message'])}", unsafe_allow_html=True)
        with st.expander("Column statistics"):
            st.dataframe(pd.DataFrame(q["columns"]), hide_index=True, width="stretch")
    can_t = common.can(u, "data.transform")
    existing = store.transformations(d["id"])
    with t2:
        open_props = [pr for pr in q["proposals"] if not any(t["operation"] == pr["operation"] and t["params"] == pr["params"] and t["status"] in ("proposed", "approved", "applied") for t in existing)]
        if not open_props:
            st.caption("No outstanding automated proposals.")
        for i, pr in enumerate(open_props):
            with st.container(border=True):
                st.markdown(f"**{theme.esc(pr['description'])}**  \n<span class='lc-muted'>{pr['operation']} · {theme.esc(pr['params'])}</span>", unsafe_allow_html=True)
                c1, c2, c3 = st.columns([1, 1, 4])
                if c1.button("Preview", key=f"pv_{i}"):
                    with common.guard():
                        st.session_state[f"pvres_{i}"] = store.preview_transformation(u, d["id"], pr["operation"], pr["params"])
                if c2.button("Approve & apply", key=f"ap_{i}", type="primary", disabled=not can_t):
                    with common.guard("Applied to the analytical copy"):
                        tid = store.propose_transformation(u, d["id"], pr["operation"], pr["params"], pr["description"])
                        store.decide_transformation(u, tid, True)
                        st.rerun()
                if st.session_state.get(f"pvres_{i}"):
                    r = st.session_state[f"pvres_{i}"]
                    c3.caption(f"Rows {r['rows_before']:,} → {r['rows_after']:,}; rows affected {r.get('rows_affected', 0):,}; cells changed {r.get('cells_affected', 0):,}")
    with t3:
        if not can_t:
            st.info("Your role cannot change data.")
        else:
            _transformation_builder(u, d)
    with t4:
        if not existing:
            st.caption("No transformations yet. The analytical copy equals the typed original.")
        for t in existing:
            c1, c2 = st.columns([6, 1])
            c1.markdown(f"**#{t['seq']} {theme.esc(t['description'])}** {theme.status_pill(t['status'])}  \n"
                        f"<span class='lc-muted'>{t['operation']} · {theme.esc(t['params'])} · rows {t.get('rows_affected') or 0} · cells {t.get('cells_affected') or 0} · {common.fmt_time(t['created_at'])}</span>",
                        unsafe_allow_html=True)
            if can_t and t["status"] in ("approved", "applied"):
                if c2.button("Revert", key=f"rv_{t['id']}"):
                    with common.guard("Reverted"):
                        store.decide_transformation(u, t["id"], False)
                        st.rerun()
            elif can_t and t["status"] == "proposed":
                if c2.button("Approve", key=f"apx_{t['id']}"):
                    with common.guard("Applied"):
                        store.decide_transformation(u, t["id"], True)
                        st.rerun()


def _transformation_builder(u, d: dict) -> None:
    df = store.analytic_frame(u, d["id"])
    cols = list(df.columns)
    op = st.selectbox("Operation", list(transform.OPERATIONS), format_func=lambda o: transform.OPERATIONS[o][1])
    params: dict = {}
    if op == "trim_whitespace":
        params["columns"] = st.multiselect("Columns (empty = all text columns)", cols) or None
    elif op == "standardize_categories":
        col = st.selectbox("Column", cols)
        vals = sorted(df[col].dropna().astype(str).unique())[:200]
        st.caption("Map each spelling to a standard value. Leave unchanged values as they are.")
        m = st.data_editor(pd.DataFrame({"from": vals, "to": vals}), hide_index=True, width="stretch", key="std_map",
                           column_config={"from": st.column_config.TextColumn(disabled=True)})
        params = {"column": col, "mapping": {a: b for a, b in zip(m["from"], m["to"]) if a != b}}
    elif op == "set_missing_codes":
        params = {"column": st.selectbox("Column", cols), "codes": [x.strip() for x in st.text_input("Codes, comma-separated", "-99, 999").split(",") if x.strip()]}
    elif op == "drop_duplicates":
        params = {"keys": st.multiselect("Key columns (empty = whole row)", cols) or None}
    elif op == "flag_outliers":
        params = {"column": st.selectbox("Numeric column", cols), "k": st.number_input("IQR multiplier", 1.5, 10.0, 3.0)}
    elif op == "set_range_invalid":
        c1, c2, c3 = st.columns(3)
        params = {"column": c1.selectbox("Column", cols), "min_value": c2.number_input("Minimum", value=0.0), "max_value": c3.number_input("Maximum", value=100.0)}
    elif op == "recode":
        col = st.selectbox("Source column", cols)
        new = st.text_input("New column name", f"{col}_recoded")
        vals = sorted(df[col].dropna().astype(str).unique())[:100]
        m = st.data_editor(pd.DataFrame({"from": vals, "to": vals}), hide_index=True, width="stretch", key="rec_map",
                           column_config={"from": st.column_config.TextColumn(disabled=True)})
        params = {"column": col, "new_column": new, "mapping": dict(zip(m["from"], m["to"]))}
    elif op == "bin_numeric":
        col = st.selectbox("Numeric column", cols)
        edges = st.text_input("Band edges", "0, 5, 18, 60, 120")
        labels = st.text_input("Band labels", "0-4, 5-17, 18-59, 60+")
        params = {"column": col, "new_column": st.text_input("New column", f"{col}_band"),
                  "edges": [float(x) for x in edges.split(",") if x.strip()], "labels": [x.strip() for x in labels.split(",") if x.strip()]}
    elif op == "rename_column":
        params = {"column": st.selectbox("Column", cols), "new_name": st.text_input("New name")}
    elif op == "exclude_rows":
        params = condition_editor(cols, "excl", label="Exclude rows where")
    elif op == "weighted_sum":
        sel = st.multiselect("Columns", cols)
        w = st.data_editor(pd.DataFrame({"column": sel, "weight": [1.0] * len(sel)}), hide_index=True, key="ws_w",
                           column_config={"column": st.column_config.TextColumn(disabled=True)})
        params = {"weights": dict(zip(w["column"], w["weight"])), "new_column": st.text_input("New column", "score")}
    desc = st.text_input("Description (shown in the history)", transform.OPERATIONS[op][1])
    c1, c2 = st.columns(2)
    if c1.button("Preview impact", icon=":material/visibility:"):
        with common.guard():
            r = store.preview_transformation(u, d["id"], op, params)
            st.info(f"Rows {r['rows_before']:,} → {r['rows_after']:,}; rows affected {r.get('rows_affected', 0):,}; cells changed {r.get('cells_affected', 0):,}")
    if c2.button("Approve & apply", type="primary"):
        with common.guard("Applied to the analytical copy"):
            tid = store.propose_transformation(u, d["id"], op, params, desc)
            store.decide_transformation(u, tid, True)
            st.rerun()


# ---------------------------------------------------------------- Statistics

def analysis() -> None:
    u = common.cu()
    theme.page_header("Statistical Analysis", "Deterministic calculations with bases, missing values and test assumptions shown. No result is generated by AI.", "sigma")
    p = common.need_project(u)
    if not p:
        return
    d = pick_dataset(u, p["id"])
    if not d:
        return
    df = store.analytic_frame(u, d["id"])
    mp = store.mapping(d["id"])
    cols = list(df.columns)
    num = [c for c in cols if pd.api.types.is_numeric_dtype(df[c]) and not pd.api.types.is_bool_dtype(df[c])]
    cat = [c for c in cols if c not in num]
    dates = [c for c in cols if pd.api.types.is_datetime64_any_dtype(df[c])]
    tabs = st.tabs(["Counting", "Descriptive", "Frequencies", "Cross-tabulation", "Group comparison", "Correlation", "Trends & forecast", "Regression"])
    with tabs[0]:
        ids = [c for c, m in mp.items() if m["role"] == "identifier"]
        hs = [c for c, m in mp.items() if m["role"] == "household_size"]
        c1, c2, c3 = st.columns(3)
        idc = c1.selectbox("Beneficiary / record ID", [None] + ids + cols, format_func=lambda x: x or "—")
        hh = c2.selectbox("Household ID", [None] + ids + cols, format_func=lambda x: x or "—")
        hsz = c3.selectbox("Household size", [None] + hs + num, format_func=lambda x: x or "—")
        res = counting.count_summary(df, d.get("unit_of_analysis") or "unknown", idc, hh, hsz)
        for k, v in res.items():
            if isinstance(v, dict) and "value" in v:
                st.markdown(f"**{v['value']:,} {theme.esc(v['unit'])}** — <span class='lc-muted'>{theme.esc(v['rule'])}</span>", unsafe_allow_html=True)
        for n in res.get("notes", []):
            st.caption(n)
        if not d.get("unit_confirmed"):
            st.warning("The unit of analysis has not been confirmed in Data Understanding; counts are labelled as records.")
    with tabs[1]:
        sel = st.multiselect("Numeric variables", num, default=num[:6])
        w = st.selectbox("Weight (optional)", [None] + num, format_func=lambda x: x or "Unweighted")
        if sel:
            st.dataframe(pd.DataFrame([{"variable": c, **stats.describe_numeric(df[c], df[w] if w else None)} for c in sel]), hide_index=True, width="stretch")
    with tabs[2]:
        c = st.selectbox("Variable", cat or cols, key="fq")
        ms = st.checkbox("Multiple-response question (space or ; separated)", value=mp.get(c, {}).get("role") == "multiselect")
        sep = st.text_input("Separator", ";" if df[c].astype("string").str.contains(";").any() else " ") if ms else None
        r = stats.frequency(df, c, multiselect_sep=sep)
        st.dataframe(r["table"], hide_index=True, width="stretch")
        st.caption(f"Base n = {r['base_n']:,} · missing {r['n_missing']:,}" + (" · percentages of respondents; options can sum to more than 100%" if r["type"] == "multiple_response" else ""))
    with tabs[3]:
        c1, c2, c3 = st.columns(3)
        row = c1.selectbox("Rows", cat, key="ct_r")
        col = c2.selectbox("Columns", [c for c in cat if c != row], key="ct_c")
        norm = c3.selectbox("Percentages", ["row", "column", "all"])
        if row and col:
            r = stats.crosstab(df, row, col, norm)
            st.dataframe(r["percent"], width="stretch")
            with st.expander("Counts"):
                st.dataframe(r["counts"], width="stretch")
            st.caption(f"n = {r['n']:,} · excluded (missing) {r['n_excluded_missing']:,}")
            _test_line(r.get("test"))
    with tabs[4]:
        c1, c2 = st.columns(2)
        val = c1.selectbox("Numeric outcome", num, key="cg_v")
        grp = c2.selectbox("Group", cat, key="cg_g")
        if val and grp:
            r = stats.compare_groups(df, val, grp)
            st.dataframe(r["summary"], hide_index=True, width="stretch")
            for t in r["tests"]:
                _test_line(t)
            for cv in r["caveats"]:
                st.caption(cv)
    with tabs[5]:
        sel = st.multiselect("Variables", num, default=num[:8], key="corr")
        method = st.radio("Method", ["spearman", "pearson"], horizontal=True)
        if len(sel) >= 2:
            r = stats.correlation(df, sel, method)
            st.dataframe(r["matrix"].round(2), width="stretch")
            st.caption(r["note"])
    with tabs[6]:
        if not dates:
            st.info("No column is typed as a date. Set a date type in Data Understanding to enable trends.")
        else:
            c1, c2, c3 = st.columns(3)
            dc = c1.selectbox("Date", dates)
            freq = c2.selectbox("Frequency", ["month", "week", "day", "quarter"])
            vc = c3.selectbox("Value (empty = count records)", [None] + num, format_func=lambda x: x or "Count of records")
            ts = stats.time_series(df, dc, freq, vc, "sum" if vc else "count")
            st.line_chart(ts.set_index("period")["value"])
            fc = stats.forecast(ts, 3) if freq == "month" else {"available": False, "reason": "Forecasts are offered for monthly series only."}
            if fc.get("available"):
                st.markdown(f"**Forecast** ({fc['method']})")
                st.dataframe(fc["forecast"], hide_index=True)
                st.caption(fc.get("note", ""))
            else:
                st.caption(f"Forecast not shown: {fc.get('reason')}")
            an = stats.anomalies(ts)
            if len(an):
                st.markdown("**Unusual periods (robust z-score)**")
                st.dataframe(an, hide_index=True)
    with tabs[7]:
        y = st.selectbox("Outcome (numeric)", num, key="rg_y")
        xs = st.multiselect("Predictors", [c for c in num if c != y], key="rg_x")
        if y and xs:
            r = stats.regression(df, y, xs)
            if r.get("available"):
                st.dataframe(pd.DataFrame(r["coefficients"]), hide_index=True, width="stretch")
                st.caption(f"n = {r['n']}, R² = {r['r2']:.3f}, adjusted R² = {r['adj_r2']:.3f}. {r.get('note', '')}"
                           + (" Heteroskedasticity suspected (Breusch–Pagan p<0.05): standard errors may be unreliable." if r["diagnostics"]["heteroskedasticity_suspected"] else ""))
            else:
                st.info(r.get("reason"))


def _test_line(t: dict | None) -> None:
    if not t:
        st.caption("No significance test: not enough data or categories.")
        return
    p = t.get("p_value")
    verdict = "—" if p is None else ("p < 0.05" if p < 0.05 else "p ≥ 0.05 (not significant)")
    ok = t.get("valid", t.get("appropriate", True))
    extra = f" · Cramér's V {t['cramers_v']:.2f}" if t.get("cramers_v") is not None else ""
    st.markdown(f"**{theme.esc(t['name'])}** — p = {'—' if p is None else f'{p:.4f}'} ({verdict}){extra}"
                + ("" if ok else " · *assumptions not met; treat as indicative*"))
    for k in ("caveat", "note"):
        if t.get(k):
            st.caption(t[k])


# ---------------------------------------------------------------- Indicators

def indicators_page() -> None:
    u = common.cu()
    theme.page_header("Indicators", "Define how each indicator is calculated. Lucerna never invents targets or baselines; suggested indicators stay provisional until configured and verified.", "target")
    p = common.need_project(u)
    if not p:
        return
    pid = p["id"]
    rows = store.list_indicators(u, pid)
    if rows:
        common.table(rows, {"code": "Code", "name": "Indicator", "indicator_type": "Type", "unit": "Unit", "baseline": "Baseline", "target": "Target", "status": "Status"})
    else:
        theme.empty_state("No indicators yet", "Create an indicator from a dataset, or use the suggestions below.", "target")
    can_m = common.can(u, "indicator.manage")
    tabs = st.tabs(["Calculate", "Create / edit", "Suggestions"])
    with tabs[0]:
        if rows:
            iid = st.selectbox("Indicator", [r["id"] for r in rows], format_func={r["id"]: r["name"] for r in rows}.get)
            r = next(x for x in rows if x["id"] == iid)
            st.markdown(f"{theme.status_pill(r['status'])} {theme.esc(r.get('definition') or 'No definition text recorded.')}", unsafe_allow_html=True)
            c1, c2, c3 = st.columns(3)
            if c1.button("Calculate", type="primary", icon=":material/calculate:"):
                with common.guard():
                    st.session_state["ind_res"] = store.compute_indicator(u, iid)
            if common.can(u, "indicator.verify") and r["status"] == "configured" and c2.button("Verify definition", icon=":material/verified:"):
                with common.guard("Indicator verified"):
                    store.verify_indicator(u, iid)
                    st.rerun()
            if can_m and c3.button("Delete", icon=":material/delete:"):
                with common.guard("Deleted"):
                    store.delete_indicator(u, iid)
                    st.rerun()
            res = st.session_state.get("ind_res")
            if res and res.get("indicator") == r["name"]:
                _show_indicator(res)
    with tabs[1]:
        if not can_m:
            st.info("Your role cannot create indicators.")
        else:
            _indicator_form(u, pid, rows)
    with tabs[2]:
        ds = store.list_datasets(u, pid)
        if ds:
            d = pick_dataset(u, pid, key="dataset_id_sugg")
            df = store.analytic_frame(u, d["id"])
            sug = indicators.suggest_indicators(df, d["profile"])
            st.caption("Provisional suggestions from yes/no and numeric columns. They carry no target or baseline. Review the definition before saving.")
            for i, s in enumerate(sug[:15]):
                c1, c2 = st.columns([6, 1])
                c1.markdown(f"**{theme.esc(s['name'])}** — <span class='lc-muted'>{theme.esc(s.get('reason', ''))}</span>", unsafe_allow_html=True)
                if can_m and c2.button("Save", key=f"sg_{i}"):
                    with common.guard("Saved as provisional indicator"):
                        store.save_indicator(u, pid, {**s, "dataset_id": d["id"], "origin": "suggested", "definition": None})
                        st.rerun()


def _show_indicator(res: dict) -> None:
    unit = "%" if res["type"] == "percentage" else ""
    val = res.get("value")
    sub = f"{res.get('numerator', '—')} / {res.get('denominator', '—')}" if res["type"] == "percentage" else f"n valid = {res.get('n_valid', '—')}"
    items = [("Value", "—" if val is None else f"{val:,.1f}{unit}", sub, "target")]
    if res.get("ci95"):
        lo, hi = res["ci95"]
        items.append(("95% CI", f"{lo:.1f}–{hi:.1f}{unit}", "Wilson interval", "sigma"))
    items.append(("Target", "Not set" if res.get("target") is None else f"{res['target']:,}", "entered by the team", "flag"))
    items.append(("Baseline", "Not set" if res.get("baseline") is None else f"{res['baseline']:,}", "entered by the team", "history"))
    theme.kpi_row(items)
    if res.get("achievement_pct_of_target") is not None:
        st.caption(f"Achievement: {res['achievement_pct_of_target']:.0f}% of target.")
    st.caption(f"Missing / excluded: {res.get('n_missing', 0)} · calculation hash {res['config_hash']} · dataset version {res.get('dataset_version')}")
    for col, rows in (res.get("disaggregations") or {}).items():
        st.markdown(f"**By {theme.esc(col)}**")
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")


def _indicator_form(u, pid: int, rows: list[dict]) -> None:
    ds = store.list_datasets(u, pid)
    if not ds:
        st.info("Upload a dataset first.")
        return
    edit_id = st.selectbox("Edit existing (or create new)", [None] + [r["id"] for r in rows], format_func=lambda i: "New indicator" if i is None else next(r["name"] for r in rows if r["id"] == i))
    cur = next((r for r in rows if r["id"] == edit_id), {})
    ds_ids = [x["id"] for x in ds]
    dsid = st.selectbox("Dataset", ds_ids, index=ds_ids.index(cur["dataset_id"]) if cur.get("dataset_id") in ds_ids else 0, format_func={x["id"]: x["name"] for x in ds}.get, key="ind_ds")
    df = store.analytic_frame(u, dsid)
    cols = list(df.columns)
    c1, c2, c3 = st.columns([1, 3, 2])
    code = c1.text_input("Code", cur.get("code") or "")
    name = c2.text_input("Name", cur.get("name") or "")
    types = list(indicators.TYPES)
    itype = c3.selectbox("Type", types, index=types.index(cur["indicator_type"]) if cur.get("indicator_type") in types else 0, format_func=lambda t: f"{t} — {indicators.TYPES[t][:40]}")
    definition = st.text_area("Definition (what is measured and why)", cur.get("definition") or "")
    data = {"code": code, "name": name, "definition": definition, "indicator_type": itype, "dataset_id": dsid}
    if itype in ("percentage", "count"):
        data["numerator"] = condition_editor(cols, "num", cur.get("numerator"), "Numerator")
        if itype == "percentage" and st.checkbox("Restrict the denominator", value=bool(cur.get("denominator"))):
            data["denominator"] = condition_editor(cols, "den", cur.get("denominator"), "Denominator")
    elif itype == "ratio":
        c1, c2 = st.columns(2)
        data["value_column"] = c1.selectbox("Numerator column (summed)", cols)
        data["ratio_denominator_column"] = c2.selectbox("Denominator column (summed)", cols)
    else:
        data["value_column"] = st.selectbox("Column", cols, index=cols.index(cur["value_column"]) if cur.get("value_column") in cols else 0)
    data["disaggregations"] = st.multiselect("Disaggregate by", cols, default=[c for c in cur.get("disaggregation_list") or [] if c in cols])
    c1, c2, c3, c4 = st.columns(4)
    data["unit"] = c1.text_input("Unit", cur.get("unit") or ("%" if itype == "percentage" else ""))
    b = c2.text_input("Baseline (optional)", "" if cur.get("baseline") is None else str(cur["baseline"]))
    t = c3.text_input("Target (optional)", "" if cur.get("target") is None else str(cur["target"]))
    data["reporting_period"] = c4.text_input("Reporting period", cur.get("reporting_period") or "")
    c1, c2 = st.columns(2)
    data["baseline_source"] = c1.text_input("Baseline source", cur.get("baseline_source") or "")
    data["target_source"] = c2.text_input("Target source", cur.get("target_source") or "")
    data["data_source"] = st.text_input("Data source / means of verification", cur.get("data_source") or "")
    data["responsible"] = st.text_input("Responsible", cur.get("responsible") or "")
    data["calculation_notes"] = st.text_area("Calculation notes", cur.get("calculation_notes") or "")
    if st.button("Save indicator", type="primary"):
        with common.guard("Indicator saved"):
            data["baseline"] = float(b) if b.strip() else None
            data["target"] = float(t) if t.strip() else None
            store.save_indicator(u, pid, data, edit_id)
            st.rerun()
