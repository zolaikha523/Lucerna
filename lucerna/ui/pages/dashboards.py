"""Dashboards: viewer (AI Auto and custom), Dashboard Studio editor, and Comparative Analysis."""
from __future__ import annotations

import copy
import uuid

import pandas as pd
import streamlit as st

from ...quant import charts, compare as qcompare, dashboards as dash, store
from .. import common, theme, viz
from .quant import pick_dataset

MEASURES = {"count": "Count of records", "pct_condition": "% meeting a condition", "mean": "Mean", "median": "Median", "sum": "Sum", "unique": "Unique values"}


def _filters_bar(df: pd.DataFrame, spec: dict, key: str) -> dict:
    """Filter controls in one row above the charts, plus active cross-filters."""
    flt: dict = {}
    fdefs = [f for f in spec.get("filters", []) if f["column"] in df.columns]
    if fdefs:
        cols = st.columns(min(5, len(fdefs)))
        for i, f in enumerate(fdefs[:5]):
            c = f["column"]
            with cols[i]:
                if f["kind"] == "date_range" and pd.api.types.is_datetime64_any_dtype(df[c]):
                    s = df[c].dropna()
                    if len(s):
                        lo, hi = s.min().date(), s.max().date()
                        val = st.date_input(c, (lo, hi), min_value=lo, max_value=hi, key=f"{key}_f_{c}")
                        if isinstance(val, tuple) and len(val) == 2 and (val[0] != lo or val[1] != hi):
                            flt[c] = {"range": [pd.Timestamp(val[0]), pd.Timestamp(val[1]) + pd.Timedelta(hours=23, minutes=59)]}
                else:
                    opts = sorted(df[c].dropna().astype(str).unique())[:300]
                    sel = st.multiselect(c, opts, key=f"{key}_f_{c}", placeholder="All")
                    if sel:
                        flt[c] = {"values": sel}
    cf = st.session_state.setdefault(f"{key}_cross", {})
    if cf:
        chips = st.columns([6, 1])
        chips[0].markdown("Cross-filter: " + " ".join(theme.pill(f"{c} = {', '.join(v['values'])}", "teal") for c, v in cf.items()), unsafe_allow_html=True)
        if chips[1].button("Clear", key=f"{key}_clear_cf", icon=":material/filter_alt_off:"):
            cf.clear()
            st.rerun()
    for c, v in cf.items():
        flt.setdefault(c, v)
    return flt


def _plan_panel(plan: dict) -> None:
    if not plan:
        return
    with st.expander("Analytical plan behind this dashboard", icon=":material/psychology:"):
        st.markdown(f"**Purpose:** {theme.esc(plan.get('purpose'))}")
        if plan.get("questions"):
            st.markdown("**Questions this dashboard answers**")
            for q in plan["questions"]:
                st.markdown(f"- {theme.esc(q)}")
        feas = plan.get("feasibility", {})
        rows = [{"analysis": k, "possible": "yes" if v.get("possible") else "no", "reason": v.get("reason", "")} for k, v in feas.items() if isinstance(v, dict)]
        if rows:
            st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
        if plan.get("limitations"):
            st.markdown("**Limitations**")
            for lmt in plan["limitations"]:
                st.markdown(f"- {theme.esc(lmt)}")
        st.caption("The plan is produced by deterministic rules from the confirmed data mapping. It does not call an AI model.")


def view() -> None:
    u = common.cu()
    theme.page_header("Dashboards", "Adaptive, multi-page dashboards built from the confirmed data. Click a bar or slice to cross-filter; drill down where a hierarchy exists.", "chart-column")
    p = common.need_project(u)
    if not p:
        return
    pid = p["id"]
    rows = [r for r in dash.list_for_project(u, pid) if not r["is_template"]]
    with st.expander("Generate an AI Auto Dashboard", icon=":material/auto_awesome:", expanded=not rows):
        st.caption("Lucerna reads the confirmed column mapping, decides which analyses the data can support, and builds pages only for those. "
                   "Confirm the mapping first for the best result.")
        if store.list_datasets(u, pid):
            d = pick_dataset(u, pid, key="dataset_id_auto")
            if st.button("Generate dashboard", type="primary", icon=":material/auto_awesome:", disabled=not common.can(u, "dashboard.edit")):
                with common.guard("Dashboard generated"), st.spinner("Planning and building pages…"):
                    st.session_state["dash_id"] = dash.generate_auto(u, d["id"])
                    st.rerun()
    if not rows:
        theme.empty_state("No dashboards yet", "Generate an AI Auto Dashboard or build one in Dashboard Studio.", "chart-column")
        return
    ids = [r["id"] for r in rows]
    cur = st.session_state.get("dash_id")
    did = st.selectbox("Dashboard", ids, index=ids.index(cur) if cur in ids else 0,
                       format_func={r["id"]: f"{r['name']}  ·  {r['mode']}  ·  v{r['version']}" for r in rows}.get)
    st.session_state["dash_id"] = did
    render_dashboard(u, did)


def render_dashboard(u, did: int, *, key: str = "dv") -> None:
    d = dash.get(u, did)
    spec = d["spec"]
    full = store.analytic_frame(u, d["dataset_id"])
    key = f"{key}{did}"
    pages = spec.get("pages", [])
    if not pages:
        st.info("This dashboard has no pages yet. Add some in Dashboard Studio.")
        return
    bms = dash.bookmarks(u, did)
    top = st.columns([4, 2])
    titles = [pg["title"] for pg in pages]
    pidx_key = f"{key}_page"
    if st.session_state.get(pidx_key, 0) >= len(titles):
        st.session_state[pidx_key] = 0
    with top[0]:
        sel = st.segmented_control("Page", titles, default=titles[st.session_state.get(pidx_key, 0)], key=f"{key}_seg", label_visibility="collapsed")
    if sel:
        st.session_state[pidx_key] = titles.index(sel)
    pi = st.session_state.get(pidx_key, 0)
    with top[1]:
        with st.popover("Bookmarks", icon=":material/bookmark:", width="stretch"):
            for b in bms:
                if st.button(f"{b['name']} (page {b['page_index'] + 1})", key=f"bm_{b['id']}", width="stretch"):
                    st.session_state[pidx_key] = b["page_index"]
                    st.session_state[f"{key}_cross"] = b["filters"]
                    st.rerun()
            name = st.text_input("Save current view as", key=f"{key}_bmname")
            if st.button("Save bookmark", key=f"{key}_bmsave") and name:
                with common.guard("Bookmark saved"):
                    dash.save_bookmark(u, did, name, pi, st.session_state.get(f"{key}_cross", {}))
    page = pages[pi]
    if page.get("purpose"):
        st.caption(page["purpose"])
    flt = _filters_bar(full, spec, key)
    df = charts.apply_filters(full, flt)
    if flt:
        st.caption(f"Showing {len(df):,} of {len(full):,} records after filters.")
    viz.grid(df, page.get("visuals", []), full=full, plan=d.get("plan"), key=f"{key}_{pi}", cross_filter_key=f"{key}_cross")
    _plan_panel(d.get("plan"))


# ---------------------------------------------------------------- Studio

def _visual_form(df: pd.DataFrame, v: dict | None, key: str) -> dict | None:
    v = copy.deepcopy(v or {})
    cols = list(df.columns)
    num = [c for c in cols if pd.api.types.is_numeric_dtype(df[c]) and not pd.api.types.is_bool_dtype(df[c])]
    dates = [c for c in cols if pd.api.types.is_datetime64_any_dtype(df[c])]
    types = list(charts.VISUAL_TYPES)
    t = st.selectbox("Visual type", types, index=types.index(v["type"]) if v.get("type") in types else 1, format_func=charts.VISUAL_TYPES.get, key=f"{key}_t")
    v["type"] = t
    v["title"] = st.text_input("Title", v.get("title") or "", key=f"{key}_title")
    widths = {3: "Quarter", 4: "Third", 6: "Half", 8: "Two thirds", 12: "Full width"}
    w = int(v.get("width") or (3 if t == "kpi" else 6))
    v["width"] = st.select_slider("Width", list(widths), value=w if w in widths else 6, format_func=widths.get, key=f"{key}_w")

    def pick(label, field, options, optional=False):
        opts = ([None] if optional else []) + options
        if not opts:
            st.caption(f"No suitable columns for {label.lower()}.")
            return
        cur = v.get(field)
        v[field] = st.selectbox(label, opts, index=opts.index(cur) if cur in opts else 0, format_func=lambda x: x or "—", key=f"{key}_{field}")

    def measure():
        ms = list(MEASURES)
        v["measure"] = st.selectbox("Measure", ms, index=ms.index(v.get("measure", "count")) if v.get("measure", "count") in ms else 0, format_func=MEASURES.get, key=f"{key}_m")
        if v["measure"] in ("mean", "median", "sum", "unique"):
            pick("Value column", "value", num if v["measure"] != "unique" else cols)
        if v["measure"] == "pct_condition":
            from .quant import condition_editor
            v["condition"] = condition_editor(cols, f"{key}_cond", v.get("condition"))

    if t == "kpi":
        kinds = {"count_rows": "Record count", "unique": "Unique values", "pct": "% meeting a condition", "mean": "Mean", "median": "Median",
                 "sum": "Sum", "date_span": "Date span", "n_categories": "Number of categories", "completeness": "Data completeness"}
        ks = list(kinds)
        v["kpi"] = st.selectbox("KPI", ks, index=ks.index(v.get("kpi", "count_rows")) if v.get("kpi") in ks else 0, format_func=kinds.get, key=f"{key}_k")
        if v["kpi"] in ("unique", "n_categories"):
            pick("Column", "value", cols)
        elif v["kpi"] in ("mean", "median", "sum"):
            pick("Column", "value", num)
        elif v["kpi"] == "date_span":
            pick("Date column", "value", dates)
        elif v["kpi"] == "pct":
            from .quant import condition_editor
            v["condition"] = condition_editor(cols, f"{key}_kc", v.get("condition"))
        v["icon"] = st.selectbox("Icon", ["users", "hash", "calendar", "map-pin", "percent", "wallet", "droplet", "utensils", "badge-check", "activity", "target"],
                                 key=f"{key}_icon")
    elif t in ("bar", "stacked100", "donut", "treemap"):
        pick("Category (x)", "x", cols)
        pick("Colour / series (optional)", "color", cols, optional=True)
        measure()
        if t == "bar":
            v["as_pct"] = st.checkbox("Show as % of records", value=bool(v.get("as_pct")), key=f"{key}_pct")
            v["stacked"] = st.checkbox("Stack series", value=bool(v.get("stacked")), key=f"{key}_stk")
            drill = st.multiselect("Drill-down hierarchy (optional, top to bottom)", cols, default=[c for c in v.get("drill") or [] if c in cols], key=f"{key}_drill")
            v["drill"] = drill or None
            if drill:
                v["x"] = drill[0]
        if t == "treemap":
            v["path"] = st.multiselect("Hierarchy", cols, default=[c for c in v.get("path") or [] if c in cols], key=f"{key}_path")
    elif t == "likert":
        pick("Likert question", "x", cols)
        pick("Group by (optional)", "by", cols, optional=True)
    elif t == "multiselect":
        pick("Multiple-response question", "x", cols)
        v["sep"] = st.text_input("Separator", v.get("sep", " "), key=f"{key}_sep")
    elif t in ("histogram",):
        pick("Numeric column", "value", num)
    elif t == "box":
        pick("Numeric column", "value", num)
        pick("Group by (optional)", "by", cols, optional=True)
    elif t in ("line", "area_stacked", "forecast"):
        pick("Date", "date", dates)
        v["freq"] = st.selectbox("Frequency", ["month", "week", "day", "quarter"], key=f"{key}_freq")
        if t != "forecast":
            pick("Series (optional)", "color", cols, optional=True)
        else:
            v["horizon"] = st.slider("Horizon (periods)", 1, 6, int(v.get("horizon") or 3), key=f"{key}_hz")
        measure()
    elif t == "heatmap":
        pick("Rows", "x", cols)
        pick("Columns", "color", cols)
        measure()
    elif t == "pyramid":
        pick("Sex", "sex", cols)
        pick("Age (numeric)", "age", num, optional=True)
        pick("Age group (optional)", "age_group", cols, optional=True)
    elif t == "scatter":
        pick("X", "x", num)
        pick("Y", "y", num)
        pick("Colour (optional)", "color", cols, optional=True)
    elif t == "sankey":
        pick("Source", "source", cols)
        pick("Via (optional)", "via", cols, optional=True)
        pick("Target", "target", cols)
    elif t == "map_points":
        st.caption("Point maps use only verified latitude/longitude columns. Values outside valid ranges are excluded.")
        pick("Latitude", "lat", num)
        pick("Longitude", "lon", num)
        pick("Colour (optional)", "color", cols, optional=True)
    elif t == "choropleth":
        st.info("Choropleth maps need an administrative boundary file (GeoJSON) uploaded for this project and a matched area column. "
                "Without a verified boundary file Lucerna will not draw a choropleth.")
        pick("Area column", "x", cols)
        measure()
    elif t in ("table",):
        pick("Group by (optional)", "by", cols, optional=True)
        v["columns"] = st.multiselect("Columns", cols, default=[c for c in v.get("columns") or [] if c in cols], key=f"{key}_cols")
    elif t in ("correlation", "stat_summary"):
        v["columns"] = st.multiselect("Numeric columns", num, default=[c for c in v.get("columns") or [] if c in num] or num[:6], key=f"{key}_cols")
    elif t == "text":
        v["insights"] = st.checkbox("Show computed insights (deterministic)", value=bool(v.get("insights")), key=f"{key}_ins")
        if not v["insights"]:
            v["markdown"] = st.text_area("Text (Markdown)", v.get("markdown") or "", key=f"{key}_md")
    v.setdefault("id", uuid.uuid4().hex[:8])
    return v


def studio() -> None:
    u = common.cu()
    theme.page_header("Dashboard Studio", "Build and edit dashboards: pages, visuals, layout, filters, versions and templates.", "layout-dashboard")
    p = common.need_project(u)
    if not p:
        return
    pid = p["id"]
    if not common.can(u, "dashboard.edit"):
        st.info("Your role can view dashboards but not edit them.")
        return
    allrows = dash.list_for_project(u, pid)
    with st.expander("New dashboard", icon=":material/add:", expanded=not allrows):
        if store.list_datasets(u, pid):
            c1, c2 = st.columns(2)
            with c1:
                d = pick_dataset(u, pid, key="dataset_id_new")
            name = c2.text_input("Name", "Custom dashboard")
            c1, c2 = st.columns(2)
            if c1.button("Create blank dashboard", type="primary"):
                with common.guard("Created"):
                    st.session_state["studio_id"] = dash.create_blank(u, pid, d["id"], name)
                    st.rerun()
            tpls = dash.templates(u, pid)
            if tpls:
                tid = c2.selectbox("…or start from a template", [t["id"] for t in tpls], format_func={t["id"]: t["name"] for t in tpls}.get)
                if c2.button("Apply template to this dataset"):
                    with common.guard():
                        nid, missing = dash.apply_template(u, tid, d["id"])
                        st.session_state["studio_id"] = nid
                        if missing:
                            st.warning("Some visuals reference columns this dataset does not have: " + "; ".join(missing))
        else:
            st.caption("Upload a dataset first.")
    if not allrows:
        return
    ids = [r["id"] for r in allrows]
    cur = st.session_state.get("studio_id")
    did = st.selectbox("Dashboard to edit", ids, index=ids.index(cur) if cur in ids else 0,
                       format_func={r["id"]: f"{r['name']} · {'template · ' if r['is_template'] else ''}v{r['version']}" for r in allrows}.get)
    st.session_state["studio_id"] = did
    d = dash.get(u, did)
    wkey = f"studio_spec_{did}_{d['version']}"
    if wkey not in st.session_state:
        st.session_state[wkey] = copy.deepcopy(d["spec"])
    spec = st.session_state[wkey]
    df = store.analytic_frame(u, d["dataset_id"])

    edit_tab, preview_tab, manage_tab = st.tabs(["Edit", "Preview", "Versions & sharing"])
    with edit_tab:
        pages = spec.setdefault("pages", [])
        c1, c2 = st.columns([3, 1])
        if not pages:
            pages.append({"key": "page1", "title": "Page 1", "icon": "layout-dashboard", "purpose": "", "visuals": []})
        pi = c1.selectbox("Page", range(len(pages)), format_func=lambda i: f"{i + 1}. {pages[i]['title']}", key=f"st_pg_{did}")
        if c2.button("Add page", icon=":material/note_add:", width="stretch"):
            pages.append({"key": uuid.uuid4().hex[:6], "title": f"Page {len(pages) + 1}", "icon": "layout-dashboard", "purpose": "", "visuals": []})
            st.rerun()
        page = pages[pi]
        c1, c2, c3, c4 = st.columns([3, 4, 1, 1])
        page["title"] = c1.text_input("Page title", page["title"], key=f"pt_{did}_{pi}")
        page["purpose"] = c2.text_input("Purpose", page.get("purpose", ""), key=f"pp_{did}_{pi}")
        if c3.button("↑", key=f"pu_{pi}", help="Move page earlier", disabled=pi == 0):
            pages[pi - 1], pages[pi] = pages[pi], pages[pi - 1]
            st.rerun()
        if c4.button("✕", key=f"pdel_{pi}", help="Delete page", disabled=len(pages) == 1):
            pages.pop(pi)
            st.rerun()
        st.markdown("**Visuals on this page**")
        st.caption("Streamlit does not support drag-and-drop on a canvas; use the arrows to reorder and the width setting to lay visuals out on a 12-column grid.")
        for vi, v in enumerate(page["visuals"]):
            with st.container(border=True):
                c = st.columns([5, 1, 1, 1, 1])
                c[0].markdown(f"**{theme.esc(v.get('title') or charts.VISUAL_TYPES.get(v['type']))}** "
                              f"<span class='lc-muted'>· {charts.VISUAL_TYPES.get(v['type'], v['type'])} · width {v.get('width', 6)}/12</span>", unsafe_allow_html=True)
                if c[1].button("↑", key=f"vu_{pi}_{vi}", disabled=vi == 0):
                    page["visuals"][vi - 1], page["visuals"][vi] = page["visuals"][vi], page["visuals"][vi - 1]
                    st.rerun()
                if c[2].button("↓", key=f"vd_{pi}_{vi}", disabled=vi == len(page["visuals"]) - 1):
                    page["visuals"][vi + 1], page["visuals"][vi] = page["visuals"][vi], page["visuals"][vi + 1]
                    st.rerun()
                if c[3].button("Edit", key=f"ve_{pi}_{vi}"):
                    st.session_state["st_edit"] = (did, pi, vi)
                if c[4].button("✕", key=f"vx_{pi}_{vi}"):
                    page["visuals"].pop(vi)
                    st.rerun()
                if st.session_state.get("st_edit") == (did, pi, vi):
                    nv = _visual_form(df, v, f"ed_{did}_{pi}_{vi}")
                    if st.button("Apply changes", key=f"va_{pi}_{vi}", type="primary"):
                        page["visuals"][vi] = nv
                        st.session_state.pop("st_edit", None)
                        st.rerun()
        with st.expander("Add a visual", icon=":material/add_chart:"):
            nv = _visual_form(df, None, f"new_{did}_{pi}")
            with st.container(border=True):
                st.caption("Live preview")
                viz.render(df, nv, full=df, plan=d.get("plan"), key=f"newprev_{did}_{pi}", exportable=False)
            if st.button("Add to page", type="primary", key=f"add_{did}_{pi}"):
                page["visuals"].append(nv)
                st.rerun()
        st.markdown("**Dashboard filters** (shown in one row above the charts)")
        fcols = st.multiselect("Filter columns", list(df.columns), default=[f["column"] for f in spec.get("filters", []) if f["column"] in df.columns], key=f"flt_{did}")
        spec["filters"] = [{"column": c, "kind": "date_range" if pd.api.types.is_datetime64_any_dtype(df[c]) else "values"} for c in fcols]
        c1, c2, c3 = st.columns([2, 3, 2])
        note = c2.text_input("Version note", placeholder="What changed?", key=f"vn_{did}")
        if c1.button("Save as new version", type="primary", icon=":material/save:"):
            with common.guard("Saved"):
                dash.save_spec(u, did, spec, note=note, new_version=True)
                st.session_state.pop(wkey, None)
                st.rerun()
        if c3.button("Discard unsaved changes"):
            st.session_state.pop(wkey, None)
            st.rerun()
    with preview_tab:
        pages = spec.get("pages", [])
        if pages:
            pi2 = st.selectbox("Preview page", range(len(pages)), format_func=lambda i: pages[i]["title"], key=f"pv_pg_{did}")
            viz.grid(df, pages[pi2].get("visuals", []), full=df, plan=d.get("plan"), key=f"spv_{did}_{pi2}")
    with manage_tab:
        vs = dash.versions(u, did)
        common.table(vs, {"version": "Version", "note": "Note", "created_at": "Saved"})
        if vs:
            vid = st.selectbox("Restore version", [v["id"] for v in vs], format_func={v["id"]: f"v{v['version']} — {v['note']}" for v in vs}.get)
            if st.button("Restore (creates a new version)"):
                with common.guard("Restored"):
                    dash.restore_version(u, did, vid)
                    st.rerun()
        st.divider()
        c1, c2, c3 = st.columns(3)
        if c1.button("Duplicate", icon=":material/content_copy:"):
            with common.guard("Duplicated"):
                st.session_state["studio_id"] = dash.duplicate(u, did)
                st.rerun()
        if c2.button("Save as organisation template", icon=":material/bookmark_add:"):
            with common.guard("Template saved"):
                dash.duplicate(u, did, name=f"Template — {d['name']}", as_template=True)
        if c3.button("Delete dashboard", icon=":material/delete:"):
            with common.guard("Deleted"):
                dash.delete(u, did)
                st.session_state.pop("studio_id", None)
                st.rerun()


# ---------------------------------------------------------------- Comparative

def compare() -> None:
    u = common.cu()
    theme.page_header("Comparative Analysis", "Compare rounds, baseline/endline, or two datasets. Lucerna checks compatibility before it compares anything.", "git-compare")
    p = common.need_project(u)
    if not p:
        return
    pid = p["id"]
    ds = store.list_datasets(u, pid)
    if len(ds) < 2:
        theme.empty_state("Two datasets needed", "Upload a second round, endline, or comparison dataset to this project.", "git-compare")
        return
    c1, c2 = st.columns(2)
    with c1:
        a = pick_dataset(u, pid, "Dataset A (earlier / reference)", key="cmp_a")
    with c2:
        b = pick_dataset(u, pid, "Dataset B (later / comparison)", key="cmp_b")
    if a["id"] == b["id"]:
        st.warning("Choose two different datasets.")
        return
    la, lb = a.get("round_label") or "A", b.get("round_label") or "B"
    if la == lb:
        la, lb = f"{la} (A)", f"{lb} (B)"
    dfa, dfb = store.analytic_frame(u, a["id"]), store.analytic_frame(u, b["id"])
    ma, mb = store.mapping(a["id"]), store.mapping(b["id"])
    comp = qcompare.compatibility(dfa, dfb, ma, mb, a, b)
    for i in comp["issues"]:
        st.error(i)
    for w in comp["warnings"]:
        st.warning(w)
    if not comp["comparable_columns"]:
        return
    st.success(f"{len(comp['comparable_columns'])} comparable variables.") if comp["valid"] else None
    binaries = [c for c in comp["comparable_columns"] if ma[c]["type"] == "boolean"]
    nums = [c for c in comp["comparable_columns"] if ma[c]["type"] in ("numeric", "integer")]
    cats = [c for c in comp["comparable_columns"] if ma[c]["type"] == "categorical"]
    t1, t2 = st.tabs(["Yes/no indicators", "Numeric measures"])
    with t1:
        if not binaries:
            st.caption("No comparable yes/no variables.")
        else:
            sel = st.multiselect("Variables", binaries, default=binaries[:5])
            by = st.selectbox("Disaggregate by (optional)", [None] + cats, format_func=lambda x: x or "—")
            if sel:
                res = pd.concat([qcompare.compare_binary(dfa, dfb, c, la, lb, by) for c in sel], ignore_index=True)
                st.dataframe(res, hide_index=True, width="stretch")
                import plotly.graph_objects as go
                from ...quant.palette import CATEGORICAL, INK
                m = theme.mode()
                allr = res[res["group"] == "All"] if not by else res
                labels = allr["indicator"] + ("" if not by else " · " + allr["group"].astype(str))
                fig = go.Figure()
                fig.add_bar(y=labels, x=allr[f"{la} %"], name=la, orientation="h", marker=dict(color=CATEGORICAL[m][1], cornerradius=4))
                fig.add_bar(y=labels, x=allr[f"{lb} %"], name=lb, orientation="h", marker=dict(color=CATEGORICAL[m][0], cornerradius=4))
                fig.update_layout(barmode="group", height=max(260, 60 * len(allr) + 80), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                                  font=dict(color=INK[m]["secondary"]), legend=dict(orientation="h", y=1.08), margin=dict(l=10, r=10, t=30, b=10),
                                  xaxis=dict(title="% of valid responses", gridcolor=INK[m]["grid"]))
                from .. import viz_style
                st.plotly_chart(viz_style.restyle(fig, {"type": "bar"}, viz.app_design()), config=viz.PLOTLY_CONFIG, theme=None)
                st.caption("Two-proportion z-test per row; independent samples assumed. A change is described as significant only when p < 0.05 and the test is valid.")
    with t2:
        if not nums:
            st.caption("No comparable numeric variables.")
        else:
            sel = st.multiselect("Measures", nums, default=nums[:5], key="cmp_num")
            if sel:
                st.dataframe(pd.DataFrame([qcompare.compare_numeric(dfa, dfb, c, la, lb) for c in sel]), hide_index=True, width="stretch")
