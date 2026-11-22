"""Role-based access control, enforced in the service layer (not only in the UI).

Every service function that reads or changes project data calls `require(user, permission, project_id)`.
`PermissionDenied` is raised on failure, and the denial is audited.
"""
from __future__ import annotations

from dataclasses import dataclass

from .. import db

PROJECT_ROLES = {
    "project_manager": "Project Manager",
    "meal_manager": "MEAL Manager",
    "meal_officer": "MEAL Officer",
    "analyst": "Researcher / Analyst",
    "data_collector": "Data Collector",
    "viewer": "Viewer",
}
ORG_ROLES = {"org_admin": "Organization Administrator", "member": "Member"}

_ALL = set(PROJECT_ROLES)
_ANALYSTS = {"project_manager", "meal_manager", "meal_officer", "analyst"}
_MANAGERS = {"project_manager", "meal_manager"}

PERMISSIONS: dict[str, set[str]] = {
    "project.view": _ALL,
    "data.upload": _ANALYSTS | {"data_collector"},
    "data.transform": _ANALYSTS,
    "data.delete": {"project_manager"},
    "analysis.run": _ANALYSTS,
    "indicator.manage": {"project_manager", "meal_manager", "meal_officer"},
    "indicator.verify": _MANAGERS,
    "dashboard.edit": _ANALYSTS,
    "qual.code": _ANALYSTS,
    "quote.review": _ANALYSTS,
    "report.edit": _ANALYSTS,
    "report.approve": _MANAGERS,
    "export": _ANALYSTS | {"viewer"},
    "project.manage": {"project_manager"},
    "ai.use": _ANALYSTS,
}
SYSTEM_PERMISSIONS = {"system.settings", "ai.configure", "org.create", "user.manage_all"}


class PermissionDenied(Exception):
    pass


@dataclass
class CurrentUser:
    id: int
    username: str
    system_role: str = "user"
    full_name: str | None = None

    @property
    def is_system_admin(self) -> bool:
        return self.system_role == "system_admin"


def org_role(user: CurrentUser, org_id: int | None) -> str | None:
    if org_id is None:
        return None
    r = db.query_one("SELECT role FROM org_members WHERE org_id=? AND user_id=?", (org_id, user.id))
    return r["role"] if r else None


def project_role(user: CurrentUser, project_id: int) -> str | None:
    r = db.query_one("SELECT role FROM project_members WHERE project_id=? AND user_id=?", (project_id, user.id))
    return r["role"] if r else None


def project_org(project_id: int) -> int | None:
    r = db.query_one("SELECT org_id FROM projects WHERE id=?", (project_id,))
    if r is None:
        raise PermissionDenied("Project not found or not accessible.")
    return r["org_id"]


def can(user: CurrentUser, permission: str, project_id: int | None = None, org_id: int | None = None) -> bool:
    if user is None:
        return False
    if user.is_system_admin:
        return True
    if permission in SYSTEM_PERMISSIONS:
        return False
    if permission.startswith("org."):
        return org_role(user, org_id) == "org_admin"
    if project_id is None:
        return False
    try:
        porg = project_org(project_id)
    except PermissionDenied:
        return False
    if org_role(user, porg) == "org_admin":
        return True
    role = project_role(user, project_id)
    return bool(role) and role in PERMISSIONS.get(permission, set())


def require(user: CurrentUser, permission: str, project_id: int | None = None, org_id: int | None = None) -> None:
    if not can(user, permission, project_id, org_id):
        from . import audit
        audit.log(getattr(user, "username", None), "PERMISSION_DENIED", permission, "WARNING",
                  project_id=project_id, org_id=org_id)
        raise PermissionDenied(f"You do not have permission for '{permission}' on this resource.")


def accessible_project_ids(user: CurrentUser) -> list[int]:
    if user.is_system_admin:
        return [r["id"] for r in db.query("SELECT id FROM projects ORDER BY id")]
    rows = db.query(
        "SELECT id FROM projects WHERE org_id IN (SELECT org_id FROM org_members WHERE user_id=? AND role='org_admin')"
        " UNION SELECT project_id FROM project_members WHERE user_id=?", (user.id, user.id))
    return sorted({r["id"] for r in rows})


def admin_org_ids(user: CurrentUser) -> list[int]:
    if user.is_system_admin:
        return [r["id"] for r in db.query("SELECT id FROM organizations")]
    return [r["org_id"] for r in db.query("SELECT org_id FROM org_members WHERE user_id=? AND role='org_admin'", (user.id,))]
