"""Workspace administration: projects, organisations, users & permissions, AI settings, privacy & system, audit log."""
from __future__ import annotations

import secrets

import pandas as pd
import streamlit as st

from ...ai import providers
from ...config import settings
from ...security import audit, auth, rbac
from ...services import backup, bootstrap, orgs
from .. import common, theme

CLASSIFICATIONS = ["Restricted", "Confidential", "Internal", "Public"]


# ---------------------------------------------------------------- Projects

def projects() -> None:
    u = common.cu()
    theme.page_header("Projects", "Each project isolates its data, documents, dashboards and reports. Members get a role per project.", "folder-open")
    ol = orgs.list_organizations(u)
    admin_orgs = [o for o in ol if u.is_system_admin or rbac.can(u, "org.manage", org_id=o["id"])]
    ps = orgs.list_projects(u)
    if ps:
        common.table(ps, {"name": "Project", "org_name": "Organisation", "sector": "Sector", "geography": "Geography", "classification": "Classification",
                          "my_role": "My role", "n_datasets": "Datasets", "n_documents": "Documents", "n_reports": "Reports"})
    with st.expander("Create project", icon=":material/create_new_folder:", expanded=not ps):
        if not admin_orgs:
            st.info("Only organisation administrators can create projects." + (" Create an organisation first." if u.is_system_admin else ""))
        else:
            with st.form("newproj"):
                oid = st.selectbox("Organisation", [o["id"] for o in admin_orgs], format_func={o["id"]: o["name"] for o in admin_orgs}.get)
                c1, c2 = st.columns([3, 1])
                name = c1.text_input("Project name")
                code = c2.text_input("Code")
                desc = st.text_area("Description")
                c1, c2, c3 = st.columns(3)
                sector = c1.text_input("Sector")
                geo = c2.text_input("Geography")
                donor = c3.text_input("Donor")
                c1, c2, c3 = st.columns(3)
                ps_ = c1.text_input("Start (YYYY-MM-DD)")
                pe = c2.text_input("End (YYYY-MM-DD)")
                cls = c3.selectbox("Data classification", CLASSIFICATIONS, help="Restricted projects can never use an external AI provider.")
                if st.form_submit_button("Create", type="primary"):
                    with common.guard("Project created"):
                        st.session_state["project_id"] = orgs.create_project(u, oid, name, code=code, description=desc, sector=sector, geography=geo, donor=donor,
                                                                             period_start=ps_, period_end=pe, classification=cls)
                        st.rerun()
    p = common.project(u)
    if not p:
        return
    st.markdown(f"#### {theme.esc(p['name'])}")
    can_m = common.can(u, "project.manage", p["id"])
    t1, t2 = st.tabs(["Details", "Members"])
    with t1:
        with st.form("editproj"):
            c1, c2 = st.columns([3, 1])
            name = c1.text_input("Name", p["name"])
            code = c2.text_input("Code", p.get("code") or "")
            desc = st.text_area("Description", p.get("description") or "")
            c1, c2, c3 = st.columns(3)
            sector = c1.text_input("Sector", p.get("sector") or "")
            geo = c2.text_input("Geography", p.get("geography") or "")
            donor = c3.text_input("Donor", p.get("donor") or "")
            c1, c2, c3 = st.columns(3)
            ps_ = c1.text_input("Start", p.get("period_start") or "")
            pe = c2.text_input("End", p.get("period_end") or "")
            cls = c3.selectbox("Classification", CLASSIFICATIONS, index=CLASSIFICATIONS.index(p["classification"]) if p.get("classification") in CLASSIFICATIONS else 0)
            if st.form_submit_button("Save", disabled=not can_m):
                with common.guard("Saved"):
                    orgs.update_project(u, p["id"], name=name, code=code, description=desc, sector=sector, geography=geo, donor=donor,
                                        period_start=ps_, period_end=pe, classification=cls)
                    st.rerun()
    with t2:
        mem = orgs.project_members(u, p["id"])
        common.table(pd.DataFrame(mem).assign(role=lambda d: d["role"].map(rbac.PROJECT_ROLES)) if mem else [], {"username": "User", "full_name": "Name", "role": "Role"})
        if can_m:
            try:
                cand = orgs.org_members(u, p["org_id"]) if rbac.can(u, "org.manage", org_id=p["org_id"]) else mem
            except rbac.PermissionDenied:
                cand = mem
            if cand:
                c1, c2, c3 = st.columns([2, 2, 1])
                uid = c1.selectbox("User (organisation members)", [m["id"] for m in cand], format_func={m["id"]: m["username"] for m in cand}.get)
                role = c2.selectbox("Role", [None] + list(rbac.PROJECT_ROLES), format_func=lambda r: "Remove from project" if r is None else rbac.PROJECT_ROLES[r])
                if c3.button("Apply", type="primary"):
                    with common.guard("Membership updated"):
                        orgs.set_project_member(u, p["id"], uid, role)
                        st.rerun()
        with st.expander("What each role can do"):
            perms = sorted(rbac.PERMISSIONS)
            st.dataframe(pd.DataFrame([{"permission": k, **{rbac.PROJECT_ROLES[r]: "✓" if r in rbac.PERMISSIONS[k] else "" for r in rbac.PROJECT_ROLES}} for k in perms]),
                         hide_index=True, width="stretch")
            st.caption("Organisation administrators have every project permission in their organisation. System administrators manage the whole installation.")


# ---------------------------------------------------------------- Organisations

def organizations() -> None:
    u = common.cu()
    theme.page_header("Organisations", "Organisations separate agencies or country offices. Users of one organisation cannot see another's projects.", "building-2")
    ol = orgs.list_organizations(u)
    if ol:
        common.table(ol, {"name": "Organisation", "short_name": "Short name", "my_role": "My role", "brand_primary": "Primary colour"})
    if u.is_system_admin:
        with st.expander("Create organisation", icon=":material/add_business:", expanded=not ol):
            with st.form("neworg"):
                name = st.text_input("Name")
                short = st.text_input("Short name")
                if st.form_submit_button("Create", type="primary"):
                    with common.guard("Organisation created"):
                        oid = orgs.create_organization(u, name, short)
                        orgs.add_org_member(u, oid, u.id, "org_admin")
                        st.rerun()
    admin_orgs = [o for o in ol if u.is_system_admin or rbac.can(u, "org.manage", org_id=o["id"])]
    if not admin_orgs:
        return
    oid = st.selectbox("Manage organisation", [o["id"] for o in admin_orgs], format_func={o["id"]: o["name"] for o in admin_orgs}.get)
    o = next(x for x in admin_orgs if x["id"] == oid)
    t1, t2 = st.tabs(["Members", "Report branding"])
    with t1:
        mem = orgs.org_members(u, oid)
        common.table(mem, {"username": "User", "full_name": "Name", "role": "Organisation role", "active": "Active"})
        users = orgs.list_users(u)
        if users:
            c1, c2, c3 = st.columns([2, 2, 1])
            uid = c1.selectbox("User", [x["id"] for x in users], format_func={x["id"]: x["username"] for x in users}.get, key="om_u")
            role = c2.selectbox("Role", list(rbac.ORG_ROLES), format_func=rbac.ORG_ROLES.get, key="om_r")
            if c3.button("Add / update", type="primary"):
                with common.guard("Updated"):
                    orgs.add_org_member(u, oid, uid, role)
                    st.rerun()
    with t2:
        st.caption("Colours used on report covers, headings and tables for this organisation's projects.")
        c1, c2 = st.columns(2)
        prim = c1.color_picker("Primary", o.get("brand_primary") or "#173B68")
        acc = c2.color_picker("Accent", o.get("brand_accent") or "#18B6A4")
        if st.button("Save branding"):
            with common.guard("Saved"):
                orgs.update_branding(u, oid, primary=prim.upper(), accent=acc.upper())


# ---------------------------------------------------------------- Users

def users() -> None:
    u = common.cu()
    theme.page_header("Users & Permissions", "Create accounts, reset passwords, lock or unlock access. Every change is audited.", "users")
    if not (u.is_system_admin or rbac.admin_org_ids(u)):
        st.info("Only system or organisation administrators can manage users.")
        return
    rows = orgs.list_users(u)
    import time as _t
    df = pd.DataFrame(rows)
    if not df.empty:
        df["status"] = df.apply(lambda r: "locked" if (r["locked_until"] or 0) > _t.time() else ("active" if r["active"] else "deactivated"), axis=1)
        df["mfa"] = df["mfa"].map({1: "on", 0: "off"})
    common.table(df, {"username": "Username", "full_name": "Name", "email": "E-mail", "system_role": "System role", "mfa": "MFA", "status": "Status"})
    t1, t2 = st.tabs(["Create user", "Manage user"])
    with t1:
        with st.form("newuser", clear_on_submit=True):
            c1, c2 = st.columns(2)
            un = c1.text_input("Username")
            fn = c2.text_input("Full name")
            em = st.text_input("E-mail (optional, for your records; Lucerna sends no e-mail)")
            temp = st.text_input("Temporary password", value=_temp_password(), help="Share it securely. The user must change it at first sign-in.")
            sysrole = st.selectbox("System role", ["user", "system_admin"], disabled=not u.is_system_admin)
            ol = [o for o in orgs.list_organizations(u) if u.is_system_admin or o["id"] in rbac.admin_org_ids(u)]
            oid = st.selectbox("Add to organisation", [o["id"] for o in ol], format_func={o["id"]: o["name"] for o in ol}.get) if ol else None
            if st.form_submit_button("Create user", type="primary"):
                with common.guard("User created"):
                    uid = auth.create_user(un, temp, full_name=fn, email=em, system_role=sysrole if u.is_system_admin else "user", must_change=True, created_by=u.username)
                    if oid:
                        orgs.add_org_member(u, oid, uid, "member")
                    st.rerun()
    with t2:
        if not rows:
            return
        tid = st.selectbox("User", [r["id"] for r in rows], format_func={r["id"]: r["username"] for r in rows}.get)
        target = next(r for r in rows if r["id"] == tid)
        c1, c2, c3 = st.columns(3)
        with c1:
            temp = st.text_input("New temporary password", value=_temp_password(), key="rp_t")
            if st.button("Reset password", disabled=tid == u.id):
                with common.guard("Password reset; the user's sessions were signed out"):
                    auth.admin_reset_password(tid, temp, u.username)
        with c2:
            if target["active"]:
                if st.button("Deactivate", disabled=tid == u.id):
                    with common.guard("Deactivated"):
                        auth.set_active(tid, False, u.username)
                        st.rerun()
            elif st.button("Reactivate"):
                with common.guard("Reactivated"):
                    auth.set_active(tid, True, u.username)
                    st.rerun()
        with c3:
            if st.button("Sign out all sessions"):
                with common.guard("Signed out"):
                    auth.revoke_all_sessions(tid, u.username)


def _temp_password() -> str:
    return "Lc-" + secrets.token_urlsafe(9) + "7a"


# ---------------------------------------------------------------- AI

def ai_settings() -> None:
    u = common.cu()
    theme.page_header("AI & Models", "Lucerna uses a local model by default. External providers are blocked unless enabled by the administrator, approved after a terms review, and allowed by the project's classification.", "cpu")
    rows = providers.list_providers()
    df = pd.DataFrame(rows)
    if not df.empty:
        df["location"] = df["is_external"].map({0: "Local", 1: "External"})
        df["approved"] = df.apply(lambda r: "n/a" if not r["is_external"] else ("yes" if r["approved_at"] else "no"), axis=1)
    common.table(df, {"name": "Provider", "kind": "Type", "base_url": "URL", "model": "Model", "location": "Location", "approved": "Approved", "is_default": "Default"})
    s = settings()
    ext_env = s.external_ai_enabled
    ext_app = bootstrap.get_setting("privacy.external_ai_allowed", "0") == "1"
    st.markdown(f"External AI — environment switch (LUCERNA_EXTERNAL_AI_ENABLED): {theme.pill('on' if ext_env else 'off', 'warning' if ext_env else 'good')} · "
                f"application setting: {theme.pill('on' if ext_app else 'off', 'warning' if ext_app else 'good')}", unsafe_allow_html=True)
    st.caption("Lucerna never trains or fine-tunes models on your data and never falls back to another provider silently. AI logs record prompt versions, timings and sizes, not content.")
    if not rows:
        return
    pid = st.selectbox("Provider", [r["id"] for r in rows], format_func={r["id"]: r["name"] for r in rows}.get)
    if st.button("Check connection", icon=":material/network_check:"):
        with st.spinner("Contacting the provider…"):
            h = providers.health_check(pid)
        (st.success if h.get("reachable") and h.get("model_installed") is not False else st.warning)(h["message"])
        if h.get("installed_models"):
            st.caption("Installed models: " + ", ".join(h["installed_models"]))
    if not common.can(u, "ai.configure"):
        st.caption("Only a system administrator can change AI providers.")
        return
    cur = next(r for r in rows if r["id"] == pid)
    with st.expander("Edit provider / add a provider", icon=":material/tune:"):
        new = st.checkbox("Add a new provider instead of editing", value=False)
        c = {} if new else cur
        with st.form("prov"):
            name = st.text_input("Name", c.get("name") or "")
            kind = st.selectbox("Type", ["ollama", "openai_compatible"], index=0 if (c.get("kind") or "ollama") == "ollama" else 1)
            url = st.text_input("Base URL", c.get("base_url") or "http://localhost:11434")
            model = st.text_input("Model", c.get("model") or "gemma3:4b")
            key_env = st.text_input("Name of the environment variable holding the API key (external only; the key itself is never stored in the database)", c.get("api_key_env") or "")
            default = st.checkbox("Default provider", value=bool(c.get("is_default")))
            if st.form_submit_button("Save provider", type="primary"):
                with common.guard("Saved"):
                    providers.save_provider(u, name=name, kind=kind, base_url=url, model=model, api_key_env=key_env or None, provider_id=None if new else pid, is_default=default)
                    st.rerun()
    if cur["is_external"]:
        with st.expander("Approve external provider", icon=":material/gavel:"):
            st.warning("Approval records that the provider's data retention, training exclusion and contract terms were reviewed. It does not by itself allow use: "
                       "the environment switch and application setting must also be on, and Restricted projects are always blocked.")
            note = st.text_area("Terms review record (who, when, outcome)", cur.get("terms_review_note") or "")
            if st.button("Record approval"):
                with common.guard("Approval recorded"):
                    providers.approve_external(u, pid, note)
                    st.rerun()
    st.markdown("**Recent AI runs** (metadata only)")
    from ... import db
    common.table(db.query("SELECT created_at, provider, prompt_name, prompt_version, model, status, attempts, duration_ms, input_chars, output_chars FROM ai_runs ORDER BY id DESC LIMIT 30"),
                 {"created_at": "When", "provider": "Provider", "prompt_name": "Prompt", "prompt_version": "Version", "model": "Model", "status": "Status",
                  "attempts": "Attempts", "duration_ms": "ms", "input_chars": "Input chars", "output_chars": "Output chars"})


# ---------------------------------------------------------------- Privacy & system

def system() -> None:
    u = common.cu()
    theme.page_header("Privacy & System", "Privacy defaults, storage locations and backups.", "shield-check")
    if not u.is_system_admin:
        st.info("Only a system administrator can change system settings.")
        return
    t1, t2, t3 = st.tabs(["Privacy", "Storage", "Backups"])
    with t1:
        ext = st.toggle("Allow external AI providers (application setting)", value=bootstrap.get_setting("privacy.external_ai_allowed") == "1",
                        help="Also requires LUCERNA_EXTERNAL_AI_ENABLED=1 in .env and an approved provider. Restricted projects are always blocked.")
        pii = st.toggle("Scan uploads for personal data patterns", value=bootstrap.get_setting("privacy.pii_scan_on_upload") == "1")
        pseudo = st.toggle("Pseudonymise identifier columns in exports by default", value=bootstrap.get_setting("privacy.pseudonymize_exports") == "1")
        geo = st.selectbox("Default geographic precision in exports", ["admin1", "admin2", "admin3", "exact"],
                           index=["admin1", "admin2", "admin3", "exact"].index(bootstrap.get_setting("privacy.geo_precision", "admin2")))
        if st.button("Save privacy settings", type="primary"):
            with common.guard("Saved"):
                for k, v in (("privacy.external_ai_allowed", ext), ("privacy.pii_scan_on_upload", pii), ("privacy.pseudonymize_exports", pseudo)):
                    bootstrap.set_setting(k, "1" if v else "0", u.username)
                bootstrap.set_setting("privacy.geo_precision", geo, u.username)
        st.caption("Encryption at rest is provided by the operating system (for example BitLocker on the D: drive). Lucerna does not claim certification against any standard.")
    with t2:
        st.dataframe(pd.DataFrame(backup.storage_report()), hide_index=True, width="stretch")
        st.caption("Paths come from .env (LUCERNA_DATA_DIR, LUCERNA_DB, LUCERNA_UPLOAD_DIR, …). Change them there and restart Lucerna. See docs/INSTALLATION_WINDOWS.md.")
    with t3:
        inc = st.checkbox("Include uploaded files, analytical copies and reports", value=True)
        if st.button("Create backup now", type="primary", icon=":material/backup:"):
            with common.guard(), st.spinner("Writing backup…"):
                p = backup.create_backup(u.username, inc)
                st.success(f"Backup written: {p}")
        common.table(backup.list_backups(), {"name": "File", "size_mb": "MB", "created": "Created"})
        st.caption("Restore is a manual step with Lucerna stopped; see docs/BACKUP_AND_RECOVERY.md. Automate nightly backups with backup_windows.bat in Windows Task Scheduler.")


# ---------------------------------------------------------------- Audit

def audit_page() -> None:
    u = common.cu()
    theme.page_header("Audit Log", "Security and data events. Content of documents and prompts is never written to the log.", "history")
    p = common.project(u)
    scope = ["This project"] if p else []
    if u.is_system_admin:
        scope.append("Whole installation")
    elif rbac.admin_org_ids(u):
        scope.append("My organisations")
    if not scope:
        st.info("Select a project to see its audit trail.")
        return
    sc = st.segmented_control("Scope", scope, default=scope[0])
    if sc == "This project":
        if not common.can(u, "project.manage", p["id"]) and not common.can(u, "report.approve", p["id"]):
            st.info("Project audit logs are visible to Project Managers and MEAL Managers.")
            return
        rows = audit.recent(500, project_id=p["id"])
    elif sc == "Whole installation":
        rows = audit.recent(500)
    else:
        rows = audit.recent(500, org_ids=rbac.admin_org_ids(u))
    df = pd.DataFrame(rows)
    if df.empty:
        st.caption("No events.")
        return
    c1, c2 = st.columns(2)
    sev = c1.multiselect("Severity", sorted(df["severity"].dropna().unique()))
    act = c2.text_input("Action contains")
    if sev:
        df = df[df["severity"].isin(sev)]
    if act:
        df = df[df["action"].str.contains(act, case=False, na=False)]
    common.table(df, {"ts": "When", "username": "User", "action": "Action", "severity": "Severity", "detail": "Detail", "object_type": "Object", "object_id": "ID"}, height=520)
    st.download_button("Export CSV", df.to_csv(index=False).encode("utf-8-sig"), "lucerna_audit.csv", "text/csv")
