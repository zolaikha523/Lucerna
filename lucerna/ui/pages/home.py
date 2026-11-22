"""Overview: project status across both pillars, recent work and next steps."""
from __future__ import annotations

import streamlit as st

from ...qual import store as qstore
from ...quant import dashboards as dash, store
from ...reports import service as reports
from ...services import jobs
from .. import common, theme


def page() -> None:
    u = common.cu()
    p = common.project(u)
    name = (u.full_name or u.username).split(" ")[0]
    theme.hero(f"Welcome, {name}" if not p else p["name"],
               "Turn humanitarian data into evidence decision-makers can trust: numbers that are calculated, quotes that are verified, conclusions that people approve."
               if not p else (p.get("description") or f"{p.get('org_name') or ''} · {p.get('sector') or 'Sector not set'} · {p.get('geography') or 'Geography not set'}"))
    if not p:
        theme.empty_state("No project selected", "Create a project under Settings › Projects, or ask an administrator to add you to one.", "folder-open")
        return
    pid = p["id"]
    ds = store.list_datasets(u, pid)
    qs = qstore.project_summary(u, pid)
    reps = reports.list_for_project(u, pid)
    inds = store.list_indicators(u, pid)
    theme.kpi_row([("Datasets", len(ds), f"{sum(d['row_count'] for d in ds):,} records", "database"),
                   ("Indicators", len(inds), f"{sum(1 for i in inds if i['status'] == 'verified')} verified", "target"),
                   ("Transcripts", qs["documents"], f"{qs['segments']:,} segments", "file-text"),
                   ("Verified quotes", qs["quotes_verified"], f"{qs['quotes_approved']} approved", "quote"),
                   ("Reports", len(reps), f"{sum(1 for r in reps if r['status'] == 'approved')} approved", "file-check")])
    st.write("")
    from ...quant import generator
    recent = generator.list_for_project(u, pid)[:4]
    with st.container(border=True):
        hc = st.columns([4, 1.4], vertical_alignment="center")
        with hc[0]:
            theme.chart_title("Dashboards", "layout-dashboard")
        if common.can(u, "dashboard.edit", pid) and hc[1].button("Generate a dashboard", type="primary", icon=":material/auto_awesome:", width="stretch", key="home_gen"):
            st.session_state["studio_tab"] = "generate"
            common.goto("studio")
        if not recent:
            st.caption("No dashboards yet. In Dashboard Studio, choose a dataset and a theme and Lucerna builds a complete multi-page dashboard.")
        for r in recent:
            rc = st.columns([6, 1], vertical_alignment="center")
            rc[0].markdown(f"**{theme.esc(r['name'])}** <span class='lc-muted'>· {theme.esc(r.get('dataset_name') or '')} · updated {common.fmt_time(r['updated_at'])}"
                           + (" · data changed since generation" if r["stale"] else "") + "</span>", unsafe_allow_html=True)
            if rc[1].button("Open", key=f"home_open_{r['id']}", width="stretch"):
                st.session_state["view_dashboard"] = r["id"]
                common.goto("viewer", id=str(r["id"]))
    c1, c2 = st.columns([3, 2])
    with c1:
        with st.container(border=True):
            theme.chart_title("Next steps", "list-checks")
            todo = []
            unconfirmed = [d for d in ds if d["status"] == "uploaded"]
            if not ds and not qs["documents"]:
                todo.append(("Upload a dataset or transcripts to begin.", "quant_data"))
            for d in unconfirmed[:3]:
                todo.append((f"Confirm the column mapping for “{d['name']}”.", None))
            if ds and not dash.list_for_project(u, pid):
                todo.append(("Generate a dashboard in Dashboard Studio: choose a dataset and a theme, then click Generate.", None))
            if qs["documents"] and not qs["codes"]:
                todo.append(("Run AI-assisted coding or start coding manually.", None))
            if qs["codes"] and qs["codes_approved"] < qs["codes"]:
                todo.append((f"Review {qs['codes'] - qs['codes_approved']} suggested code(s).", None))
            if qs["quotes_manual"]:
                todo.append((f"Resolve {qs['quotes_manual']} quotation(s) waiting for manual review.", None))
            if qs["quotes_verified"] > qs["quotes_approved"]:
                todo.append((f"Approve or exclude {qs['quotes_verified'] - qs['quotes_approved']} verified quotation(s).", None))
            for r in reps:
                if r["status"] in ("draft", "in_review"):
                    todo.append((f"Complete review steps for “{r['title']}”.", None))
            if not todo:
                st.caption("Nothing pending. Generate or update a report when new data arrives.")
            for t, _ in todo[:8]:
                st.markdown(f"{theme.icon('circle-dot', 14, '#18B6A4')} {theme.esc(t)}", unsafe_allow_html=True)
    with c2:
        with st.container(border=True):
            theme.chart_title("Recent background jobs", "activity")
            js = jobs.list_for_project(pid, 6)
            if not js:
                st.caption("No background jobs yet.")
            for j in js:
                st.markdown(f"{theme.status_pill(j['status'])} **{theme.esc(j['kind'].replace('_', ' '))}** "
                            f"<span class='lc-muted'>{common.fmt_time(j['created_at'])} · {theme.esc(j.get('stage') or '')}</span>", unsafe_allow_html=True)
    with st.container(border=True):
        theme.chart_title("Data in this project", "database")
        if ds:
            common.table(ds, {"name": "Dataset", "row_count": "Rows", "unit_of_analysis": "Unit", "sector_guess": "Sector (detected)", "status": "Status", "round_label": "Round"})
        else:
            st.caption("No datasets yet.")
