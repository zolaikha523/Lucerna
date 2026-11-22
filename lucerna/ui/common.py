"""Shared UI state, guards and widgets used by every Lucerna page."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime

import pandas as pd
import streamlit as st

from ..security import auth, rbac
from ..security.rbac import CurrentUser, PermissionDenied
from ..services import jobs, orgs
from . import theme


# ---------------------------------------------------------------- session state

def user() -> CurrentUser | None:
    """Re-validated on every rerun, so revoked or expired sessions end immediately."""
    sid = st.session_state.get("sid")
    u = auth.validate_session(sid)
    if not u and sid:
        st.session_state.pop("sid", None)
    return u


def project_id() -> int | None:
    return st.session_state.get("project_id")


def project(u: CurrentUser) -> dict | None:
    pid = project_id()
    if not pid:
        return None
    try:
        return orgs.get_project(u, pid)
    except PermissionDenied:
        st.session_state.pop("project_id", None)
        return None


def can(u: CurrentUser, perm: str, pid: int | None = None) -> bool:
    return rbac.can(u, perm, pid if pid is not None else project_id())


def need_project(u: CurrentUser) -> dict | None:
    p = project(u)
    if not p:
        theme.empty_state("Choose or create a project", "Select a project in the sidebar. Every dataset, document, dashboard and report belongs to a project, "
                          "and access is granted per project.", "folder-open")
    return p


def _expected_errors() -> tuple:
    from ..ai.providers import AIError
    from ..qual.extract import ExtractionError
    from ..qual.store import QualError
    from ..quant.charts import Unsupported
    from ..quant.indicators import IndicatorConfigError
    from ..quant.ingest import IngestError
    from ..quant.store import DatasetError
    from ..reports.service import ReportError
    from ..services.files import UploadRejected
    from ..services.orgs import ValidationError
    return (ValueError, KeyError, auth.AuthError, AIError, ExtractionError, QualError, Unsupported, IndicatorConfigError,
            IngestError, DatasetError, ReportError, UploadRejected, ValidationError)


_EXPECTED = _expected_errors()


def cu() -> CurrentUser:
    return st.session_state["_user"]


@contextmanager
def guard(success: str | None = None):
    """Run a UI action; show permission and validation errors as messages instead of tracebacks."""
    try:
        yield
        if success:
            st.toast(success, icon=":material/check_circle:")
    except PermissionDenied as e:
        st.error(f"Not permitted: {e}")
    except _EXPECTED as e:
        st.error(str(e).strip("'\""))
    except Exception as e:  # noqa: BLE001 — shown to the user; details stay in the server log
        import logging
        logging.getLogger("lucerna.ui").exception("UI action failed")
        st.error(f"Something went wrong: {type(e).__name__}: {e}")


def fmt_time(ts) -> str:
    if ts in (None, "", 0):
        return "—"
    try:
        if isinstance(ts, (int, float)):
            return datetime.fromtimestamp(ts).strftime("%d %b %Y %H:%M")
        return datetime.fromisoformat(str(ts).replace("Z", "")).strftime("%d %b %Y %H:%M")
    except ValueError:
        return str(ts)


def table(rows: list[dict] | pd.DataFrame, columns: dict[str, str] | None = None, height: int | None = None, key: str | None = None, **kw):
    df = rows if isinstance(rows, pd.DataFrame) else pd.DataFrame(rows)
    for c in df.columns:
        if (c.endswith("_at") or c in ("ts", "last_seen")) and not df.empty:
            df[c] = df[c].map(fmt_time)
    if columns and not df.empty:
        df = df[[c for c in columns if c in df.columns]].rename(columns=columns)
    args = dict(width="stretch", hide_index=True, key=key, **kw)
    if height:
        args["height"] = height
    return st.dataframe(df, **args)


def options(rows: list[dict], label_key: str = "name", id_key: str = "id") -> dict:
    return {r[id_key]: r[label_key] for r in rows}


# ---------------------------------------------------------------- background jobs

def job_panel(job_key: str, on_done=None) -> None:
    """Show live progress for the job whose id is stored in st.session_state[job_key]."""
    job_id = st.session_state.get(job_key)
    if not job_id:
        return

    @st.fragment(run_every=1.5)
    def _poll():
        j = jobs.get(job_id)
        if not j:
            return
        status = j["status"]
        with st.container(border=True):
            c1, c2 = st.columns([5, 1])
            c1.markdown(f"**{theme.esc(j['kind'].replace('_', ' ').title())}** &nbsp; {theme.status_pill(status)}  \n"
                        f"<span class='lc-muted'>{theme.esc(j.get('stage') or '')} — {theme.esc(j.get('message') or '')}</span>", unsafe_allow_html=True)
            if status in ("queued", "running"):
                c1.progress(min(1.0, float(j.get("progress") or 0)))
                if c2.button("Cancel", key=f"cancel_{job_id}", icon=":material/stop_circle:"):
                    jobs.cancel(job_id)
            elif status == "completed":
                if c2.button("Dismiss", key=f"dismiss_{job_id}"):
                    st.session_state.pop(job_key, None)
                    st.rerun()
            else:
                if j.get("error"):
                    c1.error(j["error"])
                if c2.button("Dismiss", key=f"dismiss_{job_id}"):
                    st.session_state.pop(job_key, None)
                    st.rerun()
        if status not in ("queued", "running") and not st.session_state.get(f"{job_key}_handled") == job_id:
            st.session_state[f"{job_key}_handled"] = job_id
            if on_done and status == "completed":
                on_done(j)
            st.rerun(scope="app")

    _poll()



def page_ref(name: str):
    """The st.Page registered under `name` in app.main (navigation targets live there)."""
    return st.session_state.get("_pages", {}).get(name)


def goto(name: str, **query) -> None:
    ref = page_ref(name)
    if ref is None:
        st.error(f"Page '{name}' is not available.")
        return
    st.switch_page(ref, query_params=query or None)
