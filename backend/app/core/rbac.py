from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models import Role, UserOrganizationRole


def is_superadmin(user) -> bool:
    for a in getattr(user, "organization_roles", []) or []:
        if a.role and a.role.name == "superadmin" and a.role.is_global:
            return True
    return False


def user_has_role(user, role_name: str, organization_id: str | None = None) -> bool:
    for a in getattr(user, "organization_roles", []) or []:
        if not a.role:
            continue
        if a.role.name == role_name:
            if organization_id is None:
                return True
            if a.organization_id == organization_id:
                return True
    return False


def user_has_permission(user, permission_codename: str, organization_id: str | None = None) -> bool:
    # Check all assigned roles for the permission
    for a in getattr(user, "organization_roles", []) or []:
        r = a.role
        if not r:
            continue
        # global roles apply across orgs
        if r.is_global or organization_id is None or a.organization_id == organization_id:
            for rp in getattr(r, "permissions", []) or []:
                if getattr(rp.permission, "codename", None) == permission_codename:
                    return True
    return False


def require_superadmin(user):
    if not is_superadmin(user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Requires superadmin")


def require_org_admin_or_superadmin(user, organization_id: str | None = None):
    if is_superadmin(user):
        return
    if user_has_role(user, "org_admin", organization_id):
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Requires organization admin or superadmin")


def user_assigned_to_org(user, organization_id: str | None) -> bool:
    if organization_id is None:
        return False
    for a in getattr(user, "organization_roles", []) or []:
        if a.organization_id == organization_id:
            return True
    return False
