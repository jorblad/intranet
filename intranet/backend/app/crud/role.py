from sqlalchemy.orm import Session

from app.models import Role


def create_role(db: Session, name: str, description: str | None = None, is_global: bool = False) -> Role:
    role = Role(name=name, description=description, is_global=is_global)
    db.add(role)
    db.commit()
    db.refresh(role)
    return role


def get_role(db: Session, role_id: str):
    return db.query(Role).filter(Role.id == role_id).first()


def list_roles(db: Session):
    return db.query(Role).all()


def update_role(db: Session, role: Role, name: str | None = None, description: str | None = None, is_global: bool | None = None):
    if name is not None:
        role.name = name
    if description is not None:
        role.description = description
    if is_global is not None:
        role.is_global = is_global
    db.add(role)
    db.commit()
    db.refresh(role)
    return role


def delete_role(db: Session, role: Role):
    db.delete(role)
    db.commit()
