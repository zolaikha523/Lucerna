"""Simplified navigation: each hub groups related tools behind one menu entry.

Only one section runs per page load (segmented control, not tabs), so hubs stay fast. The underlying pages and
services are unchanged; nothing was deleted.
"""
from __future__ import annotations

from typing import Callable

import streamlit as st

from .. import common, theme


def _hub(title: str, subtitle: str, icon: str, sections: list[tuple[str, str, Callable[[], None], bool]], key: str) -> None:
    theme.page_header(title, subtitle, icon)
    visible = [(k, label, fn) for k, label, fn, allowed in sections if allowed]
    if not visible:
        st.info("You do not have access to any section here.")
        return
    labels = {k: label for k, label, _ in visible}
    want = st.query_params.get("section")
    if want in labels and st.session_state.get(f"hub_{key}") != want and not st.session_state.get(f"_hub_seen_{key}_{want}"):
        st.session_state[f"hub_{key}"] = want
        st.session_state[f"_hub_seen_{key}_{want}"] = True
    if st.session_state.get(f"hub_{key}") not in labels:
        st.session_state[f"hub_{key}"] = visible[0][0]
    sel = st.segmented_control(title, list(labels), format_func=labels.get, key=f"hub_{key}", label_visibility="collapsed", required=True)
    fn = dict((k, f) for k, _, f in visible)[sel]
    with theme.embedded():
        fn()


def _analyst(u) -> bool:
    pid = common.project_id()
    return u.is_system_admin or (pid is not None and common.can(u, "analysis.run", pid))


def data_intelligence() -> None:
    from . import dashboards, quant
    u = common.cu()
    a = _analyst(u)
    _hub("Data Intelligence", "Understand, clean and analyse datasets. Every number is computed deterministically and shows its base.", "brain",
         [("understanding", "Understanding & Mapping", quant.understanding, True),
          ("quality", "Quality & Cleaning", quant.quality, True),
          ("statistics", "Statistical Analysis", quant.analysis, a),
          ("indicators", "Indicators", quant.indicators_page, True),
          ("compare", "Comparisons", dashboards.compare, True)], "di")


def qualitative() -> None:
    from . import qual
    _hub("Qualitative Intelligence", "Transcripts, coding, themes and verified quotations — evidence you can trace back to the source.", "file-text",
         [("documents", "Documents", qual.documents, True), ("coding", "Coding & Codebook", qual.coding, True),
          ("themes", "Themes & Findings", qual.themes, True), ("quotations", "Quotations & Evidence", qual.quotations, True),
          ("qa", "Evidence Q&A", qual.evidence_qa, True)], "qi")


def settings() -> None:
    from . import account, admin
    u = common.cu()
    from ...security import rbac
    is_org_admin = u.is_system_admin or bool(rbac.admin_org_ids(u))
    _hub("Settings", "Your account, AI models, privacy and — for administrators — system administration.", "settings",
         [("account", "My Account", account.page, True),
          ("projects", "Projects", admin.projects, True),
          ("ai", "AI & Models", admin.ai_settings, u.is_system_admin),
          ("privacy", "Privacy & System", admin.system, u.is_system_admin),
          ("organisations", "Organisations", admin.organizations, is_org_admin),
          ("users", "Users & Permissions", admin.users, is_org_admin),
          ("audit", "Audit Log", admin.audit_page, is_org_admin)], "set")
