from sqlalchemy.orm import Session

from app.models import UserOrganizationRole


def assign_role(db: Session, user_id: str, role_id: str, organization_id: str | None = None) -> UserOrganizationRole:
    assign = UserOrganizationRole(user_id=user_id, role_id=role_id, organization_id=organization_id)
    db.add(assign)
    db.commit()
    db.refresh(assign)
    return assign


def get_assignment(db: Session, assignment_id: str):
    return db.query(UserOrganizationRole).filter(UserOrganizationRole.id == assignment_id).first()


def list_assignments_for_user(db: Session, user_id: str):
    return db.query(UserOrganizationRole).filter(UserOrganizationRole.user_id == user_id).all()


def list_assignments(db: Session):
    return db.query(UserOrganizationRole).all()


def list_assignments_for_org(db: Session, organization_id: str | None):
    # organization_id may be None to represent global assignments
    return db.query(UserOrganizationRole).filter(UserOrganizationRole.organization_id == organization_id).all()


def delete_assignment(db: Session, assignment: UserOrganizationRole):
    db.delete(assignment)
    db.commit()
