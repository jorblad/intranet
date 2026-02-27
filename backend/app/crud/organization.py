from sqlalchemy.orm import Session

from app.models import Organization


def create_organization(db: Session, name: str, language: str | None = None) -> Organization:
    org = Organization(name=name, language=language)
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


def get_organization(db: Session, org_id: str):
    return db.query(Organization).filter(Organization.id == org_id).first()


def list_organizations(db: Session):
    return db.query(Organization).all()


def list_organizations_for_user(db: Session, user_id: str):
    # Return organizations the user has assignments for (non-global)
    from app.models import UserOrganizationRole

    return (
        db.query(Organization)
        .join(UserOrganizationRole, UserOrganizationRole.organization_id == Organization.id)
        .filter(UserOrganizationRole.user_id == user_id)
        .all()
    )


def update_organization(db: Session, org: Organization, name: str | None = None, language: str | None = None):
    if name is not None:
        org.name = name
    if language is not None:
        org.language = language
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


def delete_organization(db: Session, org: Organization):
    db.delete(org)
    db.commit()
