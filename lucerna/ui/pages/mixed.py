"""Mixed-methods integration: link quantitative results to qualitative themes and write integrated findings."""
from __future__ import annotations

import streamlit as st

from ...qual import store as qstore
from ...quant import store
from ...services import mixed
from .. import common, theme


def page() -> None:
    u = common.cu()
    theme.page_header("Mixed Methods", "Connect what the numbers show with what people said. Each link states the relationship, and the integrated finding is written and approved by people.", "git-merge")
    p = common.need_project(u)
    if not p:
        return
    pid = p["id"]
    ths = qstore.list_themes(u, pid)
    inds = store.list_indicators(u, pid)
    links = mixed.list_links(u, pid)
    theme.kpi_row([("Evidence links", len(links), f"{sum(1 for x in links if x['status'] == 'approved')} approved", "git-merge"),
                   ("Themes", len(ths), "qualitative", "network"), ("Indicators", len(inds), "quantitative", "target"),
                   ("Contradictions", sum(1 for x in links if x["relationship"] == "contradicts"), "need explanation", "triangle-alert", "#B7791F")])
    st.write("")
    if not ths:
        theme.empty_state("Themes needed", "Create qualitative themes first; links connect a quantitative result to a theme.", "network")
        return
    with st.expander("New evidence link", icon=":material/add_link:", expanded=not links):
        if not common.can(u, "qual.code"):
            st.info("Your role cannot create links.")
        else:
            iid = st.selectbox("Indicator (optional)", [None] + [i["id"] for i in inds], format_func=lambda i: "— free-text result —" if i is None else next(x["name"] for x in inds if x["id"] == i))
            stmt = st.text_area("Quantitative result (as computed, with its base)", placeholder="e.g. 61.2% of households (n=412) reported receiving the full transfer amount.")
            if iid and st.button("Fill from the latest calculation"):
                with common.guard():
                    res = store.compute_indicator(u, iid)
                    unit = "%" if res["type"] == "percentage" else ""
                    st.session_state["mx_stmt"] = f"{res['indicator']}: {res['value']:.1f}{unit} (n = {res.get('denominator') or res.get('n_valid')})."
            if st.session_state.get("mx_stmt"):
                st.caption(f"Latest calculation: {st.session_state['mx_stmt']}")
                stmt = stmt or st.session_state["mx_stmt"]
            tid = st.selectbox("Theme", [t["id"] for t in ths], format_func={t["id"]: t["name"] for t in ths}.get)
            rel = st.selectbox("Relationship", list(mixed.RELATIONSHIPS), format_func=lambda k: f"{k} — {mixed.RELATIONSHIPS[k]}")
            note = st.text_area("Analyst note")
            fin = st.text_area("Integrated finding (can be written later)")
            if st.button("Add link", type="primary"):
                with common.guard("Link added"):
                    mixed.add_link(u, pid, indicator_id=iid, theme_id=tid, relationship=rel, quant_statement=stmt, analyst_note=note, integrated_finding=fin)
                    st.session_state.pop("mx_stmt", None)
                    st.rerun()
    for link in links:
        with st.container(border=True):
            tone = {"supports": "good", "explains": "info", "contradicts": "warning", "complements": "teal", "unclear": "neutral"}[link["relationship"]]
            st.markdown(f"{theme.pill(link['relationship'], tone)} {theme.status_pill(link['status'])}", unsafe_allow_html=True)
            c1, c2 = st.columns(2)
            c1.markdown(f"**Quantitative** {('· ' + theme.esc(link['indicator_name'])) if link.get('indicator_name') else ''}  \n{theme.esc(link['quant_statement'])}", unsafe_allow_html=True)
            c2.markdown(f"**Qualitative theme** · {theme.esc(link['theme_name'])}", unsafe_allow_html=True)
            for q in qstore.quotes_for_theme(u, link["theme_id"])[:2]:
                c2.markdown(theme.quote_html(q["verified_text"][:300], q.get("segment_code") or ""), unsafe_allow_html=True)
            if link.get("analyst_note"):
                st.caption(f"Analyst note: {link['analyst_note']}")
            fin = st.text_area("Integrated finding", link.get("integrated_finding") or "", key=f"mxf_{link['id']}")
            b1, b2, b3 = st.columns([1, 1, 4])
            if b1.button("Approve", key=f"mxa_{link['id']}", disabled=not common.can(u, "report.approve")):
                with common.guard("Approved"):
                    mixed.review_link(u, link["id"], True, fin)
                    st.rerun()
            if b2.button("Delete", key=f"mxd_{link['id']}", disabled=not common.can(u, "qual.code")):
                with common.guard("Deleted"):
                    mixed.delete_link(u, link["id"])
                    st.rerun()
