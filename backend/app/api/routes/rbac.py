from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.routes.auth import get_current_user
from app.core.rbac import require_superadmin, require_org_admin_or_superadmin, is_superadmin
from app.db.session import get_db
from app.schemas.rbac import (
    OrganizationCreate,
    OrganizationUpdate,
    OrganizationOut,
    RoleCreate,
    RoleUpdate,
    RoleOut,
    PermissionUpdate,
    PermissionOut,
    AssignmentCreate,
    AssignmentUpdate,
    AssignmentOut,
    RolePermissionsUpdate,
    ApplyProgramPreset,
)
from app.crud import (
    create_organization,
    get_organization,
    list_organizations,
    update_organization,
    delete_organization,
    create_role,
    get_role,
    list_roles,
    update_role,
    delete_role,
    create_permission,
    get_permission,
    list_permissions,
    update_permission,
    delete_permission,
    list_permissions_for_role,
    set_permissions_for_role,
    list_permissions_for_role_resource,
    list_role_permission_resources,
    set_permissions_for_role_resource,
    list_activities,
    list_schedules,
    delete_role_permission_resource,
    assign_role,
    get_assignment,
    list_assignments_for_user,
    list_assignments,
    list_assignments_for_org,
    delete_assignment,
)

router = APIRouter()


@router.get("/rbac/organizations")
def organizations_index(db: Session = Depends(get_db), _user=Depends(get_current_user)):
    # Superadmins may see all organizations
    if is_superadmin(_user):
        orgs = list_organizations(db)
    else:
        # Otherwise only return organizations the user has assignments for
        from app.crud.organization import list_organizations_for_user

        orgs = list_organizations_for_user(db, _user.id)

    return [OrganizationOut(id=o.id, name=o.name, language=o.language) for o in orgs]


@router.post("/rbac/organizations", status_code=status.HTTP_201_CREATED)
def organizations_create(payload: OrganizationCreate, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    require_superadmin(_user)
    org = create_organization(db, payload.name, payload.language)
    return OrganizationOut(id=org.id, name=org.name, language=org.language)


@router.get("/rbac/organizations/{org_id}")
def organizations_detail(org_id: str, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    org = get_organization(db, org_id)
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    return OrganizationOut(id=org.id, name=org.name, language=org.language)


@router.patch("/rbac/organizations/{org_id}")
def organizations_update(org_id: str, payload: OrganizationUpdate, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    org = get_organization(db, org_id)
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    require_org_admin_or_superadmin(_user, org_id)
    org = update_organization(db, org, payload.name, payload.language)
    return OrganizationOut(id=org.id, name=org.name, language=org.language)


@router.delete("/rbac/organizations/{org_id}", status_code=status.HTTP_204_NO_CONTENT)
def organizations_delete(org_id: str, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    org = get_organization(db, org_id)
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    require_superadmin(_user)
    delete_organization(db, org)
    return None


# Roles
@router.get("/rbac/roles")
def roles_index(db: Session = Depends(get_db), _user=Depends(get_current_user)):
    roles = list_roles(db)
    return [RoleOut(id=r.id, name=r.name, description=r.description, is_global=r.is_global) for r in roles]


@router.post("/rbac/roles", status_code=status.HTTP_201_CREATED)
def roles_create(payload: RoleCreate, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    require_superadmin(_user)
    role = create_role(db, payload.name, payload.description, bool(payload.is_global))
    return RoleOut(id=role.id, name=role.name, description=role.description, is_global=role.is_global)


@router.get("/rbac/roles/{role_id}")
def roles_detail(role_id: str, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    role = get_role(db, role_id)
    if not role:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")
    return RoleOut(id=role.id, name=role.name, description=role.description, is_global=role.is_global)


@router.patch("/rbac/roles/{role_id}")
def roles_update(role_id: str, payload: RoleUpdate, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    role = get_role(db, role_id)
    if not role:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")
    require_superadmin(_user)
    role = update_role(db, role, payload.name, payload.description, payload.is_global)
    return RoleOut(id=role.id, name=role.name, description=role.description, is_global=role.is_global)


@router.delete("/rbac/roles/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
def roles_delete(role_id: str, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    role = get_role(db, role_id)
    if not role:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")
    require_superadmin(_user)
    delete_role(db, role)
    return None


# Permissions
@router.get("/rbac/permissions")
def permissions_index(db: Session = Depends(get_db), _user=Depends(get_current_user)):
    perms = list_permissions(db)
    return [PermissionOut(id=p.id, codename=p.codename, description=p.description) for p in perms]


@router.get("/rbac/permissions/{permission_id}")
def permissions_detail(permission_id: str, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    perm = get_permission(db, permission_id)
    if not perm:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Permission not found")
    return PermissionOut(id=perm.id, codename=perm.codename, description=perm.description)


@router.patch("/rbac/permissions/{permission_id}")
def permissions_update(permission_id: str, payload: PermissionUpdate, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    perm = get_permission(db, permission_id)
    if not perm:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Permission not found")
    require_superadmin(_user)
    perm = update_permission(db, perm, payload.codename, payload.description)
    return PermissionOut(id=perm.id, codename=perm.codename, description=perm.description)


@router.delete("/rbac/permissions/{permission_id}", status_code=status.HTTP_204_NO_CONTENT)
def permissions_delete(permission_id: str, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    perm = get_permission(db, permission_id)
    if not perm:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Permission not found")
    require_superadmin(_user)
    delete_permission(db, perm)
    return None


# Role <-> Permission relations
@router.get("/rbac/roles/{role_id}/permissions")
def role_permissions_index(role_id: str, resource_type: str | None = None, resource_id: str | None = None, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    role = get_role(db, role_id)
    if not role:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")
    # reading role permissions is allowed for superadmin
    require_superadmin(_user)

    if resource_type:
        perms = list_permissions_for_role_resource(db, role_id, resource_type, resource_id)
        return {"role_id": role_id, "permission_ids": [p.id for p in perms], "resource_type": resource_type, "resource_id": resource_id}

    perms = list_permissions_for_role(db, role_id)
    return {"role_id": role_id, "permission_ids": [p.id for p in perms]}


@router.put("/rbac/roles/{role_id}/permissions")
def role_permissions_update(role_id: str, payload: RolePermissionsUpdate, resource_type: str | None = None, resource_id: str | None = None, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    role = get_role(db, role_id)
    if not role:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")
    require_superadmin(_user)

    if resource_type:
        perms = set_permissions_for_role_resource(db, role, payload.permission_ids, resource_type, resource_id)
        return {"role_id": role_id, "permission_ids": [p.id for p in perms], "resource_type": resource_type, "resource_id": resource_id}

    perms = set_permissions_for_role(db, role, payload.permission_ids)
    return {"role_id": role_id, "permission_ids": [p.id for p in perms]}


@router.get("/rbac/roles/{role_id}/permission-resources")
def role_permission_resources_list(role_id: str, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    role = get_role(db, role_id)
    if not role:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")
    require_superadmin(_user)
    try:
        items = list_role_permission_resources(db, role_id)
        return items
    except Exception as e:
        # Return a clear 500 with the error message to aid debugging (not exposing sensitive info in prod)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.delete("/rbac/roles/{role_id}/permission-resources")
def role_permission_resources_delete(role_id: str, resource_type: str, resource_id: str | None = None, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    role = get_role(db, role_id)
    if not role:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")
    require_superadmin(_user)
    delete_role_permission_resource(db, role_id, resource_type, resource_id)
    return None


@router.post("/rbac/roles/{role_id}/apply-program-preset")
def role_apply_program_preset(role_id: str, payload: ApplyProgramPreset, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    role = get_role(db, role_id)
    if not role:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")
    # only superadmin may perform bulk RBAC changes
    require_superadmin(_user)

    # choose the resource_type to operate on (default to 'activity')
    rtype = (payload.resource_type or 'activity')
    # Normalize legacy/type aliases: historically the UI used 'program' as the
    # resource_type name while newer flows use 'activity'. To remain
    # compatible with existing DB rows and tests, store resource rows under
    # 'program' while still accepting 'activity' as input.
    store_rtype = 'program' if rtype in ('activity', 'program') else rtype
    preset = (payload.preset or '').lower()

    # build codenames based on resource type
    if preset == 'none':
        codenames = []
    elif preset == 'read':
        codenames = [f"{rtype}.read"]
    elif preset == 'readwrite':
        codenames = [f"{rtype}.read", f"{rtype}.write"]
    elif preset == 'admin':
        # admin means all resource.* permissions that exist (or will be created)
        codenames = [f"{rtype}.read", f"{rtype}.write"]
    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Unknown preset')

    # ensure permissions exist (create if missing)
    from app.models import Permission

    permission_ids = []
    for code in codenames:
        perm = db.query(Permission).filter(Permission.codename == code).first()
        if not perm:
            perm = create_permission(db, code, None)
        permission_ids.append(perm.id)

    # If admin preset, include any other {rtype}.* permissions present in DB
    if payload.preset and payload.preset.lower() == 'admin':
        likepat = f"{rtype}.%"
        extra = db.query(Permission).filter(Permission.codename.like(likepat)).all()
        permission_ids = list({p.id for p in extra})

    # apply as default first (resource_id = None). Use `store_rtype` for the
    # persisted resource_type so legacy tests and DB rows that expect
    # 'program' continue to work while callers may provide 'activity'.
    set_permissions_for_role_resource(db, role, permission_ids, store_rtype, None)

    # apply to specific resource ids if provided (frontend sends resource_ids)
    # accept multiple possible payload fields for resource ids
    ids = payload.resource_ids or payload.activity_ids or []
    if ids:
        for rid in ids:
            set_permissions_for_role_resource(db, role, permission_ids, store_rtype, rid)

    # optionally apply to all existing resources of this type
    if payload.apply_to_existing:
        if rtype == 'activity':
            acts = list_activities(db)
            for a in acts:
                set_permissions_for_role_resource(db, role, permission_ids, store_rtype, a.id)
        elif rtype == 'schedule':
            scheds = list_schedules(db)
            for s in scheds:
                set_permissions_for_role_resource(db, role, permission_ids, store_rtype, s.id)
        else:
            # Unknown resource type: no-op
            pass

    return {"role_id": role_id, "applied_permission_ids": permission_ids}


# Assignments
@router.post("/rbac/assignments", status_code=status.HTTP_201_CREATED)
def assignments_create(payload: AssignmentCreate, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    # Only superadmin for global assignments; otherwise org_admin or superadmin for the target org
    if payload.organization_id is None:
        require_superadmin(_user)
    else:
        require_org_admin_or_superadmin(_user, payload.organization_id)
    assign = assign_role(db, payload.user_id, payload.role_id, payload.organization_id)
    return AssignmentOut(id=assign.id, user_id=assign.user_id, role_id=assign.role_id, organization_id=assign.organization_id)


@router.get("/rbac/assignments")
def assignments_index(user_id: str | None = None, organization_id: str | None = None, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    # If user_id provided, return assignments for that user
    if user_id:
        items = list_assignments_for_user(db, user_id)
        return [AssignmentOut(id=i.id, user_id=i.user_id, role_id=i.role_id, organization_id=i.organization_id) for i in items]

    # If organization_id provided, allow org admins or superadmin to view
    if organization_id is not None:
        require_org_admin_or_superadmin(_user, organization_id)
        items = list_assignments_for_org(db, organization_id)
        return [AssignmentOut(id=i.id, user_id=i.user_id, role_id=i.role_id, organization_id=i.organization_id) for i in items]

    # No filters: only superadmin can view all
    require_superadmin(_user)
    items = list_assignments(db)
    return [AssignmentOut(id=i.id, user_id=i.user_id, role_id=i.role_id, organization_id=i.organization_id) for i in items]


@router.get("/rbac/users/{user_id}/assignments")
def assignments_for_user(user_id: str, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    items = list_assignments_for_user(db, user_id)
    return [AssignmentOut(id=i.id, user_id=i.user_id, role_id=i.role_id, organization_id=i.organization_id) for i in items]


@router.delete("/rbac/assignments/{assignment_id}", status_code=status.HTTP_204_NO_CONTENT)
def assignments_delete(assignment_id: str, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    assign = get_assignment(db, assignment_id)
    if not assign:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found")
    if assign.organization_id is None:
        require_superadmin(_user)
    else:
        require_org_admin_or_superadmin(_user, assign.organization_id)
    delete_assignment(db, assign)
    return None


@router.patch("/rbac/assignments/{assignment_id}")
def assignments_update(assignment_id: str, payload: AssignmentUpdate, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    assign = get_assignment(db, assignment_id)
    if not assign:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found")
    # require permission on existing assignment org (or superadmin)
    if assign.organization_id is None:
        require_superadmin(_user)
    else:
        require_org_admin_or_superadmin(_user, assign.organization_id)
    # apply updates
    if payload.role_id is not None:
        assign.role_id = payload.role_id
    if payload.organization_id is not None:
        assign.organization_id = payload.organization_id
    db.add(assign)
    db.commit()
    db.refresh(assign)
    return AssignmentOut(id=assign.id, user_id=assign.user_id, role_id=assign.role_id, organization_id=assign.organization_id)
