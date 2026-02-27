from sqlalchemy.orm import Session

from app.models import RolePermission, Permission, Role


def list_permissions_for_role(db: Session, role_id: str):
    return (
        db.query(Permission)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .filter(RolePermission.role_id == role_id)
        .all()
    )


def set_permissions_for_role(db: Session, role: Role, permission_ids: list[str]):
    # remove existing
    db.query(RolePermission).filter(RolePermission.role_id == role.id).delete()
    # add new
    for pid in permission_ids:
        rp = RolePermission(role_id=role.id, permission_id=pid)
        db.add(rp)
    db.commit()
    return list_permissions_for_role(db, role.id)
