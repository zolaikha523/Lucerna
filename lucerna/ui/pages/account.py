"""My Account: password, two-step verification (MFA) and active sessions."""
from __future__ import annotations

import streamlit as st

from ...security import auth, mfa
from .. import common, theme


def page() -> None:
    u = common.cu()
    theme.page_header("My Account", "Your password, two-step verification and signed-in sessions.", "user-round")
    row = auth.get_user_by_id(u.id)
    t1, t2, t3 = st.tabs(["Password", "Two-step verification", "Sessions"])
    with t1:
        with st.form("pw", clear_on_submit=True):
            old = st.text_input("Current password", type="password")
            new = st.text_input("New password", type="password", help="At least 10 characters with three of: lower case, upper case, digits, symbols.")
            new2 = st.text_input("Repeat new password", type="password")
            if st.form_submit_button("Change password", type="primary"):
                if new != new2:
                    st.error("Passwords do not match.")
                else:
                    with common.guard("Password changed"):
                        auth.change_password(u.id, old, new)
    with t2:
        if row.get("mfa_secret"):
            st.success("Two-step verification is on.")
            with st.form("mfa_off"):
                pw = st.text_input("Password (required to turn it off)", type="password")
                if st.form_submit_button("Turn off two-step verification"):
                    with common.guard("Two-step verification turned off"):
                        auth.disable_mfa(u.id, pw)
                        st.rerun()
        else:
            st.caption("Use an authenticator app (Microsoft Authenticator, Google Authenticator, Aegis…). Two-step verification is only switched on after you confirm a code.")
            if "mfa_enrol" not in st.session_state and st.button("Set up two-step verification", type="primary"):
                st.session_state["mfa_enrol"] = auth.begin_mfa_enrolment()
                st.rerun()
            if "mfa_enrol" in st.session_state:
                secret, codes = st.session_state["mfa_enrol"]
                uri = mfa.provisioning_uri(secret, u.username)
                c1, c2 = st.columns([1, 2])
                try:
                    import io

                    import segno
                    buf = io.BytesIO()
                    segno.make(uri, error="m").save(buf, kind="png", scale=5, border=2)
                    c1.image(buf.getvalue(), caption="Scan with your app")
                except ImportError:
                    c1.caption("Install the optional 'segno' package to show a QR code.")
                c2.markdown("**Or enter this key manually**")
                c2.code(secret)
                c2.markdown("**Recovery codes** — store them somewhere safe; each works once.")
                c2.code("\n".join(codes))
                with st.form("mfa_confirm"):
                    code = st.text_input("6-digit code from the app", max_chars=6)
                    a, b = st.columns(2)
                    if a.form_submit_button("Confirm and turn on", type="primary"):
                        with common.guard("Two-step verification is on"):
                            auth.confirm_mfa_enrolment(u.id, secret, codes, code.strip())
                            st.session_state.pop("mfa_enrol", None)
                            st.rerun()
                    if b.form_submit_button("Cancel"):
                        st.session_state.pop("mfa_enrol", None)
                        st.rerun()
    with t3:
        sid = st.session_state.get("sid")
        rows = [s for s in auth.list_sessions(u.id) if not s["revoked"]]
        for s in rows:
            c1, c2 = st.columns([5, 1])
            c1.markdown(f"**{theme.esc(s['device_label'])}** {'(this session)' if s['id'] == sid else ''}  \n"
                        f"<span class='lc-muted'>Signed in {common.fmt_time(s['created_at'])} · last active {common.fmt_time(s['last_seen'])} · expires {common.fmt_time(s['expires_at'])}</span>",
                        unsafe_allow_html=True)
            if s["id"] != sid and c2.button("Sign out", key=f"rs_{s['id']}"):
                auth.revoke_session(s["id"], u.id, u.username)
                st.rerun()
        if len(rows) > 1 and st.button("Sign out all other sessions"):
            auth.revoke_all_sessions(u.id, u.username, except_sid=sid)
            st.rerun()
