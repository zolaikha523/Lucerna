"""Organisations, projects and membership (all permission-checked)."""
from __future__ import annotations

from .. import db
from ..security import audit
from ..security.rbac import ORG_ROLES, PROJECT_ROLES, CurrentUser, PermissionDenied, accessible_project_ids, require, can


class ValidationError(Exception):
    pass


def create_organization(user: CurrentUser, name: str, short_name: str = "") -> int:
    if not user.is_system_admin:
        raise PermissionDenied("Only a System Administrator can create organisations.")
    name = (name or "").strip()
    if not name:
        raise ValidationError("Organisation name is required.")
    if db.query_one("SELECT 1 FROM organizations WHERE lower(name)=lower(?)", (name,)):
        raise ValidationError("An organisation with that name already exists.")
    oid = db.execute("INSERT INTO organizations(name, short_name, created_at, updated_at) VALUES(?,?,?,?)",
                     (name, short_name.strip() or None, db.now(), db.now()))
    audit.log(user.username, "ORG_CREATED", name, org_id=oid, object_type="organization", object_id=oid)
    return oid


def list_organizations(user: CurrentUser) -> list[dict]:
    if user.is_system_admin:
        return db.query("SELECT * FROM organizations ORDER BY name")
    return db.query("SELECT o.*, m.role AS my_role FROM organizations o JOIN org_members m ON m.org_id=o.id"
                    " WHERE m.user_id=? ORDER BY o.name", (user.id,))


def update_branding(user: CurrentUser, org_id: int, *, primary: str, accent: str, logo_path: str | None = None) -> None:
    require(user, "org.manage", org_id=org_id)
    for c in (primary, accent):
        if not (isinstance(c, str) and len(c) == 7 and c.startswith("#")):
            raise ValidationError("Colours must be hex values like #173B68.")
    db.execute("UPDATE organizations SET brand_primary=?, brand_accent=?, logo_path=COALESCE(?, logo_path), updated_at=? WHERE id=?",
               (primary, accent, logo_path, db.now(), org_id))
    audit.log(user.username, "ORG_BRANDING_UPDATED", "", org_id=org_id)


def add_org_member(user: CurrentUser, org_id: int, target_user_id: int, role: str) -> None:
    require(user, "org.manage", org_id=org_id)
    if role not in ORG_ROLES:
        raise ValidationError("Unknown organisation role.")
    db.execute("INSERT INTO org_members(org_id, user_id, role) VALUES(?,?,?) ON CONFLICT(org_id, user_id) DO UPDATE SET role=excluded.role",
               (org_id, target_user_id, role))
    audit.log(user.username, "ORG_MEMBER_SET", f"user #{target_user_id} -> {role}", org_id=org_id)


def org_members(user: CurrentUser, org_id: int) -> list[dict]:
    require(user, "org.manage", org_id=org_id)
    return db.query("SELECT u.id, u.username, u.full_name, u.active, m.role FROM org_members m JOIN users u ON u.id=m.user_id"
                    " WHERE m.org_id=? ORDER BY u.username", (org_id,))


def create_project(user: CurrentUser, org_id: int, name: str, **meta) -> int:
    if not (user.is_system_admin or can(user, "org.manage", org_id=org_id)):
        raise PermissionDenied("Only organisation administrators can create projects in this organisation.")
    name = (name or "").strip()
    if not name:
        raise ValidationError("Project name is required.")
    if db.query_one("SELECT 1 FROM projects WHERE org_id=? AND lower(name)=lower(?)", (org_id, name)):
        raise ValidationError("A project with that name already exists in this organisation.")
    fields = {k: (meta.get(k) or None) for k in ("code", "description", "sector", "geography", "period_start", "period_end", "donor", "classification")}
    pid = db.execute(
        "INSERT INTO projects(org_id, name, code, description, sector, geography, period_start, period_end, donor, classification, created_by, created_at, updated_at)"
        " VALUES(?,?,?,?,?,?,?,?,?,COALESCE(?, 'Restricted'),?,?,?)",
        (org_id, name, fields["code"], fields["description"], fields["sector"], fields["geography"], fields["period_start"],
         fields["period_end"], fields["donor"], fields["classification"], user.id, db.now(), db.now()))
    db.execute("INSERT OR IGNORE INTO project_members(project_id, user_id, role, added_at) VALUES(?,?,?,?)",
               (pid, user.id, "project_manager", db.now()))
    audit.log(user.username, "PROJECT_CREATED", name, org_id=org_id, project_id=pid, object_type="project", object_id=pid)
    return pid


def update_project(user: CurrentUser, project_id: int, **meta) -> None:
    require(user, "project.manage", project_id)
    allowed = ("name", "code", "description", "sector", "geography", "period_start", "period_end", "donor", "classification", "status")
    vals = {k: v for k, v in meta.items() if k in allowed}
    if not vals:
        return
    sets = ", ".join(f"{k}=?" for k in vals)
    db.execute(f"UPDATE projects SET {sets}, updated_at=? WHERE id=?", (*vals.values(), db.now(), project_id))
    audit.log(user.username, "PROJECT_UPDATED", ", ".join(vals), project_id=project_id)


def list_projects(user: CurrentUser) -> list[dict]:
    ids = accessible_project_ids(user)
    if not ids:
        return []
    marks = ",".join("?" * len(ids))
    return db.query(
        f"SELECT p.*, o.name AS org_name,"
        f" (SELECT role FROM project_members pm WHERE pm.project_id=p.id AND pm.user_id=?) AS my_role,"
        f" (SELECT COUNT(*) FROM datasets d WHERE d.project_id=p.id) AS n_datasets,"
        f" (SELECT COUNT(*) FROM qual_documents q WHERE q.project_id=p.id) AS n_documents,"
        f" (SELECT COUNT(*) FROM reports r WHERE r.project_id=p.id) AS n_reports"
        f" FROM projects p LEFT JOIN organizations o ON o.id=p.org_id WHERE p.id IN ({marks}) ORDER BY p.updated_at DESC",
        (user.id, *ids))


def get_project(user: CurrentUser, project_id: int) -> dict:
    require(user, "project.view", project_id)
    p = db.query_one("SELECT p.*, o.name AS org_name, o.brand_primary, o.brand_accent, o.logo_path FROM projects p"
                     " LEFT JOIN organizations o ON o.id=p.org_id WHERE p.id=?", (project_id,))
    if not p:
        raise PermissionDenied("Project not found.")
    return p


def set_project_member(user: CurrentUser, project_id: int, target_user_id: int, role: str | None) -> None:
    require(user, "project.manage", project_id)
    if role is None:
        db.execute("DELETE FROM project_members WHERE project_id=? AND user_id=?", (project_id, target_user_id))
        audit.log(user.username, "PROJECT_MEMBER_REMOVED", f"user #{target_user_id}", project_id=project_id)
        return
    if role not in PROJECT_ROLES:
        raise ValidationError("Unknown project role.")
    # The target user must belong to the project's organisation (organisation isolation).
    org_id = db.query_one("SELECT org_id FROM projects WHERE id=?", (project_id,))["org_id"]
    if not db.query_one("SELECT 1 FROM org_members WHERE org_id=? AND user_id=?", (org_id, target_user_id)):
        raise ValidationError("Add the user to this project's organisation first.")
    db.execute("INSERT INTO project_members(project_id, user_id, role, added_at) VALUES(?,?,?,?)"
               " ON CONFLICT(project_id, user_id) DO UPDATE SET role=excluded.role", (project_id, target_user_id, role, db.now()))
    audit.log(user.username, "PROJECT_MEMBER_SET", f"user #{target_user_id} -> {role}", project_id=project_id)


def project_members(user: CurrentUser, project_id: int) -> list[dict]:
    require(user, "project.view", project_id)
    return db.query("SELECT u.id, u.username, u.full_name, m.role FROM project_members m JOIN users u ON u.id=m.user_id"
                    " WHERE m.project_id=? ORDER BY u.username", (project_id,))


def list_users(user: CurrentUser) -> list[dict]:
    if user.is_system_admin:
        return db.query("SELECT id, username, full_name, email, system_role, active, mfa_secret IS NOT NULL AS mfa, locked_until FROM users ORDER BY username")
    orgs = [r["org_id"] for r in db.query("SELECT org_id FROM org_members WHERE user_id=? AND role='org_admin'", (user.id,))]
    if not orgs:
        return []
    marks = ",".join("?" * len(orgs))
    return db.query(f"SELECT DISTINCT u.id, u.username, u.full_name, u.email, u.system_role, u.active, u.mfa_secret IS NOT NULL AS mfa, u.locked_until"
                    f" FROM users u JOIN org_members m ON m.user_id=u.id WHERE m.org_id IN ({marks}) ORDER BY u.username", orgs)
