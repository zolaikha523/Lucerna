"""Report Centre: create, edit metadata and sections, generate versions, review steps, approval, compare, download."""
from __future__ import annotations

import streamlit as st

from ...quant import dashboards as dash, store as qstore
from ...reports import quant_report, service
from .. import common, theme

FIELDS = {
    "quantitative": [("background", "Background / programme context"), ("objectives", "Objectives of the analysis"),
                     ("sampling", "Sampling approach"), ("sample_size", "Sample size rationale"), ("weighting", "Weighting"),
                     ("data_collection", "Data collection method"), ("period", "Data collection period"), ("geography", "Geographic coverage"),
                     ("ethics", "Ethics and consent"), ("executive_summary", "Executive summary (written by the team)"), ("interpretation", "Interpretation"),
                     ("conclusions", "Conclusions"), ("limitations", "Additional limitations")],
    "qualitative": [("background", "Background"), ("programme_context", "Programme context"), ("rationale", "Rationale"),
                    ("objectives", "Objectives"), ("research_questions", "Research questions"), ("approach", "Research approach"),
                    ("design", "Study design"), ("sampling", "Sampling"), ("fgd_method", "FGD methodology"), ("kii_method", "KII methodology"),
                    ("data_collection", "Data collection process"), ("ethics", "Ethics, consent and safeguarding"), ("period", "Data collection period"),
                    ("geography", "Geographic coverage"), ("executive_summary", "Executive summary (written by the team)"),
                    ("conclusions", "Conclusions"), ("limitations", "Additional limitations")],
    "mixed": [("purpose", "Purpose"), ("period", "Period"), ("geography", "Geographic coverage"), ("executive_summary", "Executive summary"),
              ("conclusions", "Conclusions")],
}
KINDS = {"quantitative": "Quantitative report", "qualitative": "Qualitative report (FGD/KII)", "mixed": "Mixed-methods brief"}


def page() -> None:
    u = common.cu()
    theme.page_header("Report Centre", "Draft, review and approve donor-ready reports. Every version is kept; reports stay marked DRAFT until all review steps are complete and a manager approves.", "file-text")
    p = common.need_project(u)
    if not p:
        return
    pid = p["id"]
    reps = service.list_for_project(u, pid)
    with st.expander("New report", icon=":material/note_add:", expanded=not reps):
        if not common.can(u, "report.edit"):
            st.info("Your role cannot create reports.")
        else:
            kind = st.selectbox("Report type", list(KINDS), format_func=KINDS.get)
            title = st.text_input("Title", placeholder="Leave empty for a standard title")
            md: dict = {}
            template = None
            if kind == "quantitative":
                ds = qstore.list_datasets(u, pid)
                if not ds:
                    st.warning("Upload a dataset first.")
                    return
                md["dataset_id"] = st.selectbox("Dataset", [d["id"] for d in ds], format_func={d["id"]: d["name"] for d in ds}.get)
                dbs = [x for x in dash.list_for_project(u, pid) if x["dataset_id"] == md["dataset_id"] and not x["is_template"]]
                md["dashboard_id"] = st.selectbox("Charts from dashboard (optional)", [None] + [x["id"] for x in dbs],
                                                  format_func=lambda i: "Automatic analytical plan" if i is None else next(x["name"] for x in dbs if x["id"] == i))
                others = [d for d in ds if d["id"] != md["dataset_id"]]
                md["compare_dataset_id"] = st.selectbox("Compare with (optional)", [None] + [d["id"] for d in others],
                                                        format_func=lambda i: "—" if i is None else next(d["name"] for d in others if d["id"] == i))
                template = st.selectbox("Template", [None] + list(quant_report.TEMPLATES), format_func=lambda t: "Detect from sector" if t is None else quant_report.TEMPLATES[t])
                md["include_ai_narrative"] = st.checkbox("Add AI-drafted narrative (local model; paragraphs containing numbers not in the computed results are discarded)", value=False)
            elif kind == "qualitative":
                md["include_unreviewed_themes"] = st.checkbox("Include themes not yet approved (marked as provisional)", value=False)
                md["redact_contacts"] = st.checkbox("Redact phone numbers, e-mails and ID numbers in quotations", value=True)
            if st.button("Create report", type="primary"):
                with common.guard("Report created"):
                    st.session_state["report_id"] = service.create(u, pid, kind, title.strip() or KINDS[kind], md, template)
                    st.rerun()
    if not reps:
        theme.empty_state("No reports yet", "Create a quantitative, qualitative or mixed-methods report.", "file-text")
        return
    reps = service.list_for_project(u, pid)
    ids = [r["id"] for r in reps]
    cur = st.session_state.get("report_id")
    rid = st.selectbox("Report", ids, index=ids.index(cur) if cur in ids else 0,
                       format_func={r["id"]: f"{r['title']} · {r['kind']} · {r['status']} · v{r['current_version']}" for r in reps}.get)
    st.session_state["report_id"] = rid
    r = service.get(u, rid)
    st.markdown(f"{theme.status_pill(r['status'])} {theme.pill(KINDS[r['kind']], 'info')} "
                f"<span class='lc-muted'>Current version {r['current_version']}</span>", unsafe_allow_html=True)
    tabs = st.tabs(["Content & metadata", "Sections", "Generate", "Review & approval", "Versions"])
    can_e = common.can(u, "report.edit")
    md = dict(r["metadata"])
    with tabs[0]:
        st.caption("Fields left empty appear as 'Not provided' in the report. Lucerna does not invent methodology, sample sizes or recommendations. "
                   "Editing returns an approved report to draft.")
        with st.form("rep_meta"):
            title = st.text_input("Title", r["title"])
            subtitle = st.text_input("Subtitle", md.get("subtitle") or "")
            authors = st.text_input("Prepared by", md.get("authors") or "")
            classification = st.selectbox("Confidentiality", ["Restricted", "Confidential", "Internal", "Public"],
                                          index=["Restricted", "Confidential", "Internal", "Public"].index(md.get("classification") or p.get("classification") or "Restricted"))
            vals = {}
            for k, label in FIELDS[r["kind"]]:
                vals[k] = st.text_area(label, md.get(k) or "", height=90)
            if r["kind"] == "quantitative":
                st.markdown("**Recommendations** (entered by the team; one per line as: priority | action | supporting finding | responsible | follow-up)")
                recs_txt = st.text_area("Recommendations", "\n".join(" | ".join([x.get("priority", ""), x.get("action", ""), x.get("finding", ""), x.get("stakeholder", ""), x.get("follow_up", "")])
                                                                        for x in md.get("recommendations") or []), height=110, label_visibility="collapsed")
            if st.form_submit_button("Save", type="primary", disabled=not can_e):
                md.update({k: v.strip() or None for k, v in vals.items()})
                md.update({"subtitle": subtitle or None, "authors": authors or None, "classification": classification})
                if r["kind"] == "quantitative":
                    recs = []
                    for line in recs_txt.splitlines():
                        parts = [x.strip() for x in line.split("|")] + [""] * 5
                        if parts[1]:
                            recs.append({"priority": parts[0], "action": parts[1], "finding": parts[2], "stakeholder": parts[3], "follow_up": parts[4]})
                    md["recommendations"] = recs
                with common.guard("Saved"):
                    service.update_metadata(u, rid, md, title)
                    st.rerun()
        if r["kind"] == "qualitative":
            st.caption("Qualitative findings, conclusions and recommendations come from approved theme notes in Themes & Findings, and quotations only from the approved verified register.")
    with tabs[1]:
        try:
            content = service.build_content(u, rid)
        except Exception as e:  # noqa: BLE001
            st.error(f"The report content could not be built: {e}")
            content = None
        if content:
            ov = dict(md.get("section_overrides") or {})
            st.caption("Include or exclude sections and add analyst text at the top of any section. Computed tables, charts and verified quotations cannot be edited here — they always come from the data.")
            for s in content["sections"]:
                o = ov.get(s["id"], {})
                with st.expander(s["title"] + ("" if o.get("included", s.get("included", True)) else " (excluded)")):
                    inc = st.checkbox("Include this section", value=o.get("included", s.get("included", True)), key=f"inc_{rid}_{s['id']}")
                    txt = st.text_area("Analyst text (optional)", o.get("analyst_text") or "", key=f"ovt_{rid}_{s['id']}")
                    ov[s["id"]] = {"included": inc, "analyst_text": txt.strip() or None}
                    for b in s["blocks"][:8]:
                        if b["kind"] in ("paragraph", "callout"):
                            st.caption(f"[{b.get('label') or b.get('tone') or b['kind']}] {b['text'][:400]}")
                        elif b["kind"] == "quote":
                            st.markdown(theme.quote_html(b["text"], b["source"]), unsafe_allow_html=True)
                        elif b["kind"] == "chart":
                            st.caption(f"[chart] {b.get('caption')}")
                        elif b["kind"] in ("table", "kv"):
                            st.caption(f"[table] {len(b.get('rows', []))} rows")
            if st.button("Save section choices", disabled=not can_e):
                md["section_overrides"] = ov
                with common.guard("Saved"):
                    service.update_metadata(u, rid, md)
                    st.rerun()
    with tabs[2]:
        note = st.text_input("Version note", placeholder="e.g. Draft for MEAL review")
        fmts = st.multiselect("Formats", ["docx", "pdf", "xlsx"], default=["docx", "pdf", "xlsx"], format_func={"docx": "Word", "pdf": "PDF", "xlsx": "Excel tables"}.get)
        if st.button("Generate new version", type="primary", disabled=not (can_e and fmts), icon=":material/build:"):
            with common.guard(), st.spinner("Building report…"):
                res = service.generate_version(u, rid, note, tuple(fmts))
                st.success(f"Version {res['version']} generated.")
        _downloads(u, rid)
    with tabs[3]:
        steps = service.review_status(u, rid)
        theme.steps([(s["label"], s["done"]) for s in steps])
        for s in steps:
            c1, c2, c3 = st.columns([4, 3, 1])
            c1.markdown(f"**{theme.esc(s['label'])}**" + (f"  \n<span class='lc-muted'>by {theme.esc(s['by'])}: {theme.esc(s['note'] or '')}</span>" if s["by"] else ""), unsafe_allow_html=True)
            nt = c2.text_input("Note", key=f"rvn_{rid}_{s['step']}", label_visibility="collapsed", placeholder="Reviewer note")
            if c3.button("Done" if not s["done"] else "Redo", key=f"rv_{rid}_{s['step']}", disabled=not can_e):
                with common.guard("Recorded"):
                    service.record_review(u, rid, s["step"], "completed", nt)
                    st.rerun()
        st.divider()
        if common.can(u, "report.approve"):
            if st.button("Approve report", type="primary", icon=":material/verified:", disabled=r["status"] == "approved"):
                with common.guard("Approved — final version generated"), st.spinner("Approving and generating the final version…"):
                    service.approve(u, rid)
                    st.rerun()
        else:
            st.caption("Approval requires a Project Manager or MEAL Manager.")
    with tabs[4]:
        vs = service.versions(u, rid)
        common.table(vs, {"version": "Version", "note": "Note", "created_at": "Generated"})
        if len(vs) >= 2:
            c1, c2 = st.columns(2)
            a = c1.selectbox("Older", [v["id"] for v in vs][1:], format_func={v["id"]: f"v{v['version']}" for v in vs}.get)
            b = c2.selectbox("Newer", [v["id"] for v in vs], format_func={v["id"]: f"v{v['version']}" for v in vs}.get)
            if st.button("Compare versions"):
                diff = service.compare_versions(u, a, b)
                st.code(diff or "No text differences.", language="diff")


def _downloads(u, rid: int) -> None:
    vs = service.versions(u, rid)
    if not vs:
        return
    v = vs[0]
    st.markdown(f"**Latest: version {v['version']}** <span class='lc-muted'>{common.fmt_time(v['created_at'])} · {theme.esc(v.get('note') or '')}</span>", unsafe_allow_html=True)
    if not common.can(u, "export"):
        st.caption("Your role cannot download reports.")
        return
    cols = st.columns(3)
    for col, fmt, mime, label in ((cols[0], "docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "Word"),
                                  (cols[1], "pdf", "application/pdf", "PDF"),
                                  (cols[2], "xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "Excel")):
        if v.get(f"{fmt}_path"):
            try:
                path = service.file_for_download(u, v["id"], fmt, log=False)
                col.download_button(f"Download {label}", path.read_bytes(), f"report_{rid}_v{v['version']}.{fmt}", mime, key=f"dl_{rid}_{v['id']}_{fmt}", width="stretch",
                                    on_click=service.log_download, args=(u, v["id"], fmt))
            except Exception as e:  # noqa: BLE001
                col.caption(str(e))
