"""Lucerna Streamlit application: authentication gate, workspace sidebar and navigation."""
from __future__ import annotations

from pathlib import Path

import streamlit as st

from .. import __version__, db
from ..security import auth, rbac
from ..services import jobs, orgs
from . import common, theme

BRAND = Path(__file__).resolve().parents[2] / "assets" / "brand"


@st.cache_resource
def _startup() -> bool:
    db.init()
    jobs.mark_orphans_failed()
    from ..qual import pipeline  # noqa: F401 — registers background job kinds
    return True


# ---------------------------------------------------------------- authentication

def _auth_shell(title: str, subtitle: str):
    """Sign-in layout: the Lucerna identity above a single glass card (no sidebar)."""
    st.markdown("<style>section[data-testid='stSidebar']{display:none} .block-container{padding-top:2rem}</style>", unsafe_allow_html=True)
    _, mid, _ = st.columns([1, 1.2, 1])
    with mid:
        logo = "lucerna-logo-stacked-dark.svg" if theme.mode() == "dark" else "lucerna-logo-stacked-light.svg"
        uri = _svg_uri(BRAND / logo)
        st.markdown(f'<div class="lc-auth-wrap"><div class="lc-auth-brand"><img alt="Lucerna — From Data to Decisions" src="{uri}"/>'
                    f'<h3>{theme.esc(title)}</h3><p>{theme.esc(subtitle)}</p></div></div>', unsafe_allow_html=True)
        return st.container(key="lc_auth_box")


@st.cache_data(show_spinner=False)
def _svg_uri(path: Path) -> str:
    import base64
    return "data:image/svg+xml;base64," + base64.b64encode(path.read_bytes()).decode()


def first_run() -> None:
    box = _auth_shell("Set up Lucerna", "Create the first system administrator. This account manages organisations, users and AI settings.")
    with box, st.form("first_admin"):
        full = st.text_input("Full name")
        username = st.text_input("Username")
        pw = st.text_input("Password", type="password", help="At least 10 characters with three of: lower case, upper case, digits, symbols.")
        pw2 = st.text_input("Repeat password", type="password")
        org = st.text_input("Organisation name", placeholder="e.g. Your INGO country office")
        if st.form_submit_button("Create administrator", type="primary", width="stretch"):
            if pw != pw2:
                st.error("Passwords do not match.")
                return
            with common.guard():
                uid = auth.create_user(username, pw, full_name=full, system_role="system_admin")
                u = auth.to_current(auth.get_user_by_id(uid))
                if org.strip():
                    oid = orgs.create_organization(u, org.strip())
                    orgs.add_org_member(u, oid, uid, "org_admin")
                st.session_state["sid"] = auth.complete_login(auth.get_user_by_id(uid), device_label="First-run setup")
                st.rerun()


def login() -> None:
    pending = st.session_state.get("mfa_pending")
    if pending:
        box = _auth_shell("Two-step verification", "Enter the 6-digit code from your authenticator app, or a recovery code.")
        with box, st.form("mfa"):
            code = st.text_input("Code", max_chars=12)
            c1, c2 = st.columns(2)
            ok = c1.form_submit_button("Verify", type="primary", width="stretch")
            back = c2.form_submit_button("Back", width="stretch")
        if back:
            st.session_state.pop("mfa_pending", None)
            st.rerun()
        if ok:
            u = auth.get_user_by_id(pending)
            if u and auth.verify_second_factor(u, code.strip()):
                st.session_state.pop("mfa_pending", None)
                st.session_state["sid"] = auth.complete_login(u)
                st.rerun()
            else:
                from ..security import audit
                audit.log(u["username"] if u else "?", "MFA_FAILED", "invalid second factor", "WARNING")
                st.error("That code did not verify.")
        return
    box = _auth_shell("Sign in to your workspace", "Evidence you can trust, from data to decisions.")
    from .. import demo
    if demo.enabled():
        box.info(f"Public demo with SYNTHETIC data only. Sign in as **{demo.DEMO_USER[0]}** / **{demo.DEMO_USER[1]}**. "
                 "Do not upload real or personal data.", icon=":material/science:")
    with box, st.form("login"):
        username = st.text_input("Username", autocomplete="username")
        pw = st.text_input("Password", type="password", autocomplete="current-password")
        if st.form_submit_button("Sign in", type="primary", width="stretch"):
            try:
                u = auth.check_password_login(username, pw)
            except auth.AuthError as e:
                st.error(str(e))
                return
            if u.get("mfa_secret"):
                st.session_state["mfa_pending"] = u["id"]
            else:
                st.session_state["sid"] = auth.complete_login(u)
            st.rerun()
    with mid_caption():
        st.markdown('<div class="lc-auth-foot">Forgotten password? Ask your Lucerna administrator to issue a temporary password (Users &amp; Permissions).<br/>'
                    f'Lucerna {theme.esc(__version__)} · local-first · your data stays on this machine unless you choose otherwise</div>', unsafe_allow_html=True)


def must_change(u) -> None:
    box = _auth_shell("Choose a new password", "Your administrator issued a temporary password. Choose your own before continuing.")
    with box, st.form("must_change"):
        old = st.text_input("Temporary password", type="password")
        new = st.text_input("New password", type="password")
        new2 = st.text_input("Repeat new password", type="password")
        if st.form_submit_button("Save password", type="primary", width="stretch"):
            if new != new2:
                st.error("Passwords do not match.")
            else:
                with common.guard():
                    auth.change_password(u.id, old, new)
                    st.rerun()


def mid_caption():
    return st.columns([1, 1.2, 1])[1]


# ---------------------------------------------------------------- sidebar

def sidebar(u) -> None:
    st.logo(str(BRAND / "lucerna-logo-horizontal-dark.png"), size="large", icon_image=str(BRAND / "lucerna-symbol.png"))
    with st.sidebar:
        projects = orgs.list_projects(u)
        if projects:
            ids = [p["id"] for p in projects]
            cur = st.session_state.get("project_id")
            if cur not in ids:
                cur = ids[0]
            label = {p["id"]: f"{p['name']} · {p.get('org_name') or ''}" for p in projects}
            st.session_state["project_id"] = st.selectbox("Project", ids, index=ids.index(cur), format_func=lambda i: label[i], key="sb_project")
        else:
            st.session_state.pop("project_id", None)
            st.caption("No projects yet. Create one under Settings › Projects.")
        with st.popover(f"{u.full_name or u.username}", icon=":material/account_circle:", width="stretch"):
            st.caption(("System administrator · " if u.is_system_admin else "") + f"Lucerna {__version__} · local-first")
            dark = st.toggle("Dark interface", value=theme.mode() == "dark", key="tg_dark", help="Lucerna's own interface. Dashboards keep their own theme and brand.")
            if dark != (theme.mode() == "dark"):
                st.session_state["ui_mode"] = "dark" if dark else "light"
                st.rerun()
            if st.button("Sign out", icon=":material/logout:", width="stretch"):
                auth.logout(st.session_state.get("sid"), u.username)
                for k in list(st.session_state.keys()):
                    if k != "ui_mode":
                        del st.session_state[k]
                st.rerun()


# ---------------------------------------------------------------- navigation

def main() -> None:
    st.set_page_config(page_title="Lucerna — From Data to Decisions", page_icon=str(BRAND / "favicon.png"), layout="wide", initial_sidebar_state="expanded")
    theme.inject()
    boot = st.empty()
    boot.markdown(theme.loader_html("Starting Lucerna…"), unsafe_allow_html=True)
    _startup()
    boot.empty()
    if auth.user_count() == 0:
        first_run()
        return
    u = common.user()
    if not u:
        login()
        return
    row = auth.get_user_by_id(u.id)
    if row.get("must_change_password"):
        must_change(u)
        return

    from .pages import home, hubs, mixed, quant, reports, studio, viewer
    P = st.Page
    pages = {
        "home": P(home.page, title="Home", icon=":material/home:", url_path="home", default=True),
        "data": P(quant.library, title="Data Library", icon=":material/database:", url_path="data"),
        "intelligence": P(hubs.data_intelligence, title="Data Intelligence", icon=":material/insights:", url_path="intelligence"),
        "studio": P(studio.page, title="Dashboard Studio", icon=":material/dashboard_customize:", url_path="studio"),
        "qualitative": P(hubs.qualitative, title="Qualitative Intelligence", icon=":material/forum:", url_path="qualitative"),
        "mixed": P(mixed.page, title="Mixed Methods", icon=":material/join_inner:", url_path="mixed"),
        "reports": P(reports.page, title="Reports", icon=":material/article:", url_path="reports"),
        "settings": P(hubs.settings, title="Settings", icon=":material/settings:", url_path="settings"),
        "viewer": P(viewer.page, title="Dashboard", icon=":material/monitoring:", url_path="dashboard", visibility="hidden"),
    }
    sidebar(u)
    st.session_state["_pages"] = pages
    pid = st.session_state.get("project_id")
    analyst = u.is_system_admin or (pid is not None and rbac.can(u, "analysis.run", pid))
    uploader = analyst or (pid is not None and rbac.can(u, "data.upload", pid))
    order = ["home"] + (["data"] if uploader else []) + (["intelligence"] if analyst else []) + ["studio"] + \
            (["qualitative", "mixed"] if analyst else []) + ["reports", "settings", "viewer"]
    nav = [pages[k] for k in order]
    pg = st.navigation(nav, position="sidebar", expanded=True)
    st.session_state["_user"] = u
    pg.run()
