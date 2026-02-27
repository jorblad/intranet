from sqlalchemy.orm import Session

from app.models import Permission


def create_permission(db: Session, codename: str, description: str | None = None) -> Permission:
    perm = Permission(codename=codename, description=description)
    db.add(perm)
    db.commit()
    db.refresh(perm)
    return perm


def get_permission(db: Session, permission_id: str):
    return db.query(Permission).filter(Permission.id == permission_id).first()


def list_permissions(db: Session):
    return db.query(Permission).all()


def update_permission(db: Session, perm: Permission, codename: str | None = None, description: str | None = None):
    if codename is not None:
        perm.codename = codename
    if description is not None:
        perm.description = description
    db.add(perm)
    db.commit()
    db.refresh(perm)
    return perm


def delete_permission(db: Session, perm: Permission):
    db.delete(perm)
    db.commit()
