from sqlalchemy.orm import Session

from app.models import Term


def list_terms(db: Session, organization_id: str | None = None) -> list[Term]:
    query = db.query(Term)
    if organization_id:
        query = query.filter(Term.organization_id == organization_id)
    return query.all()


def get_term(db: Session, term_id: str) -> Term | None:
    return db.query(Term).filter(Term.id == term_id).first()


def create_term(db: Session, name: str, organization_id: str | None = None) -> Term:
    term = Term(name=name, organization_id=organization_id)
    db.add(term)
    db.commit()
    db.refresh(term)
    return term


def update_term(db: Session, term: Term, name: str | None, organization_id: str | None = None) -> Term:
    if name is not None:
        term.name = name
    if organization_id is not None:
        term.organization_id = organization_id
    db.commit()
    db.refresh(term)
    return term


def delete_term(db: Session, term: Term) -> None:
    db.delete(term)
    db.commit()
