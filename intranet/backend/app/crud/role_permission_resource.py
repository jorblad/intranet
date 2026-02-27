from sqlalchemy.orm import Session

from app.models import RolePermissionResource, Permission, Role


def list_permissions_for_role_resource(db: Session, role_id: str, resource_type: str, resource_id: str | None):
    q = db.query(Permission).join(RolePermissionResource, RolePermissionResource.permission_id == Permission.id).filter(RolePermissionResource.role_id == role_id, RolePermissionResource.resource_type == resource_type)
    if resource_id is None:
        q = q.filter(RolePermissionResource.resource_id.is_(None))
    else:
        q = q.filter(RolePermissionResource.resource_id == resource_id)
    return q.all()


def set_permissions_for_role_resource(db: Session, role: Role, permission_ids: list[str], resource_type: str, resource_id: str | None):
    # remove existing for this role+resource
    q = db.query(RolePermissionResource).filter(RolePermissionResource.role_id == role.id, RolePermissionResource.resource_type == resource_type)
    if resource_id is None:
        q = q.filter(RolePermissionResource.resource_id.is_(None))
    else:
        q = q.filter(RolePermissionResource.resource_id == resource_id)
    q.delete()
    # add new
    for pid in permission_ids:
        rpr = RolePermissionResource(role_id=role.id, permission_id=pid, resource_type=resource_type, resource_id=resource_id)
        db.add(rpr)
    db.commit()
    return list_permissions_for_role_resource(db, role.id, resource_type, resource_id)


def list_role_permission_resources(db: Session, role_id: str):
    # return grouped resources for a role: {(resource_type, resource_id): [permission_ids]}
    rows = db.query(RolePermissionResource).filter(RolePermissionResource.role_id == role_id).all()
    out = {}
    for r in rows:
        key = (r.resource_type, r.resource_id)
        out.setdefault(key, []).append(r.permission_id)
    items = []
    for (rtype, rid), pids in out.items():
        items.append({"resource_type": rtype, "resource_id": rid, "permission_ids": pids})
    return items


def delete_role_permission_resource(db: Session, role_id: str, resource_type: str, resource_id: str | None):
    q = db.query(RolePermissionResource).filter(RolePermissionResource.role_id == role_id, RolePermissionResource.resource_type == resource_type)
    if resource_id is None:
        q = q.filter(RolePermissionResource.resource_id.is_(None))
    else:
        q = q.filter(RolePermissionResource.resource_id == resource_id)
    q.delete()
    db.commit()
