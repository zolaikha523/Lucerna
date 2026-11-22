"""Dashboard Studio — the builder environment.

Generate: choose data → see its summary → choose a theme (and optional branding) → Generate. Nothing else is
required; charts, methods, pages and indicators are chosen by the engine. Advanced options are hidden.
My dashboards: open, rename, duplicate, refresh, change theme, versions, delete.
Custom editor: the manual page/visual editor for analysts who want to adjust a dashboard.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from ...quant import dashboards as dash, generator, store, workbook
from ...services.files import QUANT_EXT
from .. import brand_panel, common, dash_theme, theme


def workbook_panel(u, dataset_id: int, expanded: bool = False) -> None:
    wb = store.workbook_info(u, dataset_id)
    if not wb:
        return
    with st.expander(f"How Lucerna read this workbook — main sheet: {wb.get('primary') or 'none'}", icon=":material/table_view:", expanded=expanded):
        rows = [{"Sheet": s["name"], "Type": s["role_label"], "Rows": s["rows"], "Columns": s["cols"], "Main": "✓" if s["is_primary"] else "",
                 "Confidence": f"{s['confidence']:.0%}", "Why": "; ".join(s["reasons"][:2])} for s in wb["sheets"]]
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
        for line in wb.get("explanation", []):
            st.markdown(f"- {theme.esc(line)}")
        st.caption("Sheet types are decided by deterministic rules from structure and content (size, column types, dictionary-like columns, "
                   "values that name other sheets' columns), not by sheet names alone.")


def _summary_card(s: dict) -> None:
    facts = [("Rows", f"{s['rows']:,}"), ("Columns", f"{s['columns']:,}"), ("Sheet type", s["role_label"]),
             ("Period", f"{s['date_range'][0]} → {s['date_range'][1]}" if s["date_range"] else "No dates"),
             ("Locations", f"{len(s['geo_columns'])} column{'s' if len(s['geo_columns']) != 1 else ''}" if s["geo_columns"] else "None found"),
             ("Missing cells", f"{s['missing_pct']}% on average")]
    cols = st.columns(len(facts))
    for c, (k, v) in zip(cols, facts):
        c.markdown(theme.kpi(k, v, "", {"Rows": "rows-3", "Columns": "columns-3", "Sheet type": "table", "Period": "calendar", "Locations": "map-pin",
                                        "Missing cells": "circle-dashed"}[k], small=len(v) > 12), unsafe_allow_html=True)
    notes = []
    if s["geo_columns"]:
        notes.append("Location columns: " + ", ".join(s["geo_columns"]) + ".")
    if s["pii_columns"]:
        notes.append(f"{len(s['pii_columns'])} column(s) look like personal data and will be excluded from every chart.")
    if not s["unit_confirmed"]:
        notes.append("What one row represents has not been confirmed yet; counts will be labelled as records. You can confirm it later in Data Intelligence.")
    if s["needs_review"]:
        notes.append(f"{s['needs_review']} column type(s) were detected with lower confidence; the dashboard notes this in its methodology.")
    for n in notes:
        st.caption(n)


def generate_tab(u, pid: int) -> None:
    can_edit = common.can(u, "dashboard.edit", pid)
    if not can_edit:
        st.info("Your role can view dashboards but not create them. Open one under My dashboards.")
        return
    st.markdown('<div class="lc-steps"><span class="lc-step">1 · Data</span><span class="lc-step">2 · Theme</span>'
                '<span class="lc-step">3 · Brand (optional)</span><span class="lc-step">4 · Generate</span></div>', unsafe_allow_html=True)
    with st.expander("Add a new data file", icon=":material/upload:", expanded=not store.list_datasets(u, pid)):
        f = st.file_uploader("Excel, CSV, JSON, Word or PDF table", type=[e.strip(".") for e in QUANT_EXT], key="gen_upload")
        if f is not None and st.button("Read file", type="primary", key="gen_read"):
            with common.guard(), st.spinner("Reading every sheet, finding the main data and profiling columns…"):
                ids = store.import_file(u, pid, f.name, f.getvalue())
                st.session_state["gen_dataset"] = ids[0]
                st.session_state["gen_ds_sel"] = ids[0]   # the selector keeps its own state; point it at the new main sheet
                st.rerun()
    adv = st.session_state.get("gen_show_ref", False)
    rows = generator.dataset_choices(u, pid, include_reference=adv)
    if not rows:
        theme.empty_state("No data yet", "Upload a file above to begin.", "file-spreadsheet")
        return
    ids = [r["id"] for r in rows]
    cur = st.session_state.get("gen_dataset")
    label = {r["id"]: f"{r['name']}  ·  {r['row_count']:,} rows" + ("  ·  main sheet" if r.get("is_primary") and r.get("sheet_role") else "") for r in rows}
    st.markdown("##### 1 · Data")
    did = st.selectbox("Dataset", ids, index=ids.index(cur) if cur in ids else 0, format_func=label.get, key="gen_ds_sel")
    st.session_state["gen_dataset"] = did
    s = generator.summary(u, did)
    _summary_card(s)
    if s["workbook"]:
        workbook_panel(u, did)
        if not s["is_primary"] and s["role"] in workbook.ANALYTICAL_ROLES:
            st.info(f"This is not the main sheet of its workbook (the main sheet is '{s['workbook'].get('primary')}'). Related sheets are only "
                    "added automatically when you generate from the main sheet.", icon=":material/info:")

    st.markdown("##### 2 · Theme")
    keys = list(dash_theme.THEMES)
    tcols = st.columns(4)
    for c, k in zip(tcols, keys):
        c.markdown(dash_theme.swatch_html(k), unsafe_allow_html=True)
        c.caption(dash_theme.THEMES[k]["desc"])
    tkey = st.radio("Theme", keys, format_func=lambda k: dash_theme.THEMES[k]["label"], horizontal=True, key="gen_theme", label_visibility="collapsed")

    st.markdown("##### 3 · Organisation branding")
    st.caption("Optional. Upload the organisation's logo and Lucerna reads its colours (no AI, nothing is guessed from the name) to build an "
               "accessible colour system for this dashboard only. Each dashboard keeps its own brand.")
    with st.container(key="gen_brand_box"):
        choice = brand_panel.panel(u, pid, "gen", tkey, default_title=f"{s['name']} — Analytical Dashboard")
    with st.expander("Advanced options", icon=":material/tune:"):
        st.toggle("Also list codebooks, README and reference sheets as datasets", key="gen_show_ref")
        st.caption("Not needed normally: reference sheets are used for labels and documentation and never analysed as data.")

    st.markdown("##### 4 · Generate")
    if st.button("Generate Professional Dashboard", type="primary", icon=":material/auto_awesome:", key="gen_go"):
        with st.status("Building your dashboard…", expanded=True) as status, common.guard():
            st.write("Profiling variables and checking data quality…")
            branding = brand_panel.to_branding(u, pid, choice)
            st.write("Choosing analyses, pages, charts and indicators that the data can support…")
            new_id = generator.generate(u, did, theme=tkey, branding={k: v for k, v in branding.items() if v is not None})
            st.write("Computing every figure and writing the insights…")
            status.update(label="Dashboard ready", state="complete")
            st.session_state["view_dashboard"] = new_id
            common.goto("viewer", id=str(new_id))


def my_dashboards_tab(u, pid: int) -> None:
    rows = generator.list_for_project(u, pid)
    if not rows:
        theme.empty_state("No dashboards yet", "Generate one from the Generate tab.", "layout-dashboard")
        return
    can_edit = common.can(u, "dashboard.edit", pid)
    for r in rows:
        with st.container(border=True):
            c = st.columns([5, 1.6, 1.6, 1.6, 1.1], vertical_alignment="center")
            stale = ' <span class="lc-pill" style="background:rgba(250,178,25,.18);color:#8a5a00">data changed — refresh available</span>' if r["stale"] else ""
            c[0].markdown(f"**{theme.esc(r['name'])}**{stale}<br/><span class='lc-muted'>{theme.esc(r.get('dataset_name') or 'dataset removed')} · "
                          f"{dash_theme.THEMES.get(r.get('theme') or 'corporate', dash_theme.THEMES['corporate'])['label']} · v{r['version']} · "
                          f"updated {common.fmt_time(r['updated_at'])}</span>", unsafe_allow_html=True)
            if c[1].button("Open", key=f"open_{r['id']}", icon=":material/open_in_full:", type="primary", width="stretch"):
                st.session_state["view_dashboard"] = r["id"]
                common.goto("viewer", id=str(r["id"]))
            if can_edit:
                if c[2].button("Refresh", key=f"refresh_{r['id']}", icon=":material/refresh:", width="stretch",
                               help="Re-run the analysis on the current data; the previous version is kept."):
                    with common.guard("Dashboard regenerated from the current data."), st.spinner("Re-running the analysis…"):
                        generator.refresh(u, r["id"])
                if c[3].button("Branding", key=f"brand_{r['id']}", icon=":material/palette:", width="stretch",
                               help="Logo, organisation name, tagline, colours and background of this dashboard"):
                    _brand_dialog(u, r["id"])
                with c[4].popover("", icon=":material/more_horiz:"):
                    nn = st.text_input("Name", value=r["name"], key=f"rn_{r['id']}")
                    if st.button("Rename", key=f"rnb_{r['id']}") and nn.strip():
                        with common.guard():
                            generator.update_meta(u, r["id"], name=nn.strip(), branding={"title": nn.strip()})
                            st.rerun()
                    if st.button("Duplicate", key=f"dup_{r['id']}", icon=":material/content_copy:"):
                        with common.guard():
                            nid = dash.duplicate(u, r["id"])
                            src = generator.get(u, r["id"])
                            generator.update_meta(u, nid, theme=src["theme"], branding={**src["branding"], "title": f"{src['branding'].get('title') or src['name']} (copy)"})
                            from ... import db
                            db.execute("UPDATE dashboards SET linked_json=?, source_version=? WHERE id=?", (db.dumps(src["linked_ids"]), src.get("source_version"), nid))
                            st.rerun()
                    vers = dash.versions(u, r["id"])
                    if len(vers) > 1:
                        vsel = st.selectbox("Restore a version", [v["id"] for v in vers],
                                            format_func=lambda i: next(f"v{v['version']} · {v['note']} · {common.fmt_time(v['created_at'])}" for v in vers if v["id"] == i),
                                            key=f"vs_{r['id']}")
                        if st.button("Restore", key=f"vr_{r['id']}"):
                            with common.guard("Version restored as a new version."):
                                dash.restore_version(u, r["id"], vsel)
                    st.divider()
                    conf = st.checkbox("Confirm delete", key=f"delc_{r['id']}")
                    if st.button("Delete", key=f"del_{r['id']}", disabled=not conf, icon=":material/delete:"):
                        with common.guard():
                            dash.delete(u, r["id"])
                            st.rerun()


@st.dialog("Dashboard branding", width="large")
def _brand_dialog(u, dashboard_id: int) -> None:
    brand_panel.editor_dialog_body(u, generator.get(u, dashboard_id))


def page() -> None:
    from . import dashboards as legacy
    u = common.cu()
    theme.page_header("Dashboard Studio", "Choose data and a theme; Lucerna analyses the data and builds a complete interactive dashboard.", "layout-dashboard")
    p = common.need_project(u)
    if not p:
        return
    opts = {"generate": "Generate", "mine": "My dashboards", "editor": "Custom editor"}
    if not common.can(u, "dashboard.edit", p["id"]):
        opts = {"mine": "My dashboards"}
    if st.session_state.get("studio_tab") not in opts:
        st.session_state["studio_tab"] = "mine" if generator.list_for_project(u, p["id"]) and "generate" not in opts else list(opts)[0]
    sel = st.segmented_control("Studio", list(opts), format_func=opts.get, key="studio_tab", label_visibility="collapsed", required=True)
    if sel == "generate":
        generate_tab(u, p["id"])
    elif sel == "mine":
        my_dashboards_tab(u, p["id"])
    else:
        st.caption("Manual editing for analysts: add, remove and reorder visuals, set widths and filters, save versions and templates. "
                   "Edits are saved as new versions of the dashboard.")
        with theme.embedded():
            legacy.studio()
