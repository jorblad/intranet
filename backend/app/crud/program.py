from sqlalchemy.orm import Session

from app.models import Program


def list_programs(db: Session, term_id: str | None = None, organization_id: str | None = None) -> list[Program]:
    query = db.query(Program)
    if term_id:
        query = query.filter(Program.term_id == term_id)
    if organization_id:
        query = query.filter(Program.organization_id == organization_id)
    return query.all()


def get_program(db: Session, program_id: str) -> Program | None:
    return db.query(Program).filter(Program.id == program_id).first()


def create_program(db: Session, name: str, term_id: str, organization_id: str | None = None) -> Program:
    program = Program(name=name, term_id=term_id, organization_id=organization_id)
    db.add(program)
    db.commit()
    db.refresh(program)
    return program


def update_program(
    db: Session,
    program: Program,
    name: str | None,
    term_id: str | None,
    organization_id: str | None = None,
) -> Program:
    if name is not None:
        program.name = name
    if term_id is not None:
        program.term_id = term_id
    if organization_id is not None:
        program.organization_id = organization_id
    db.commit()
    db.refresh(program)
    return program


def delete_program(db: Session, program: Program) -> None:
    db.delete(program)
    db.commit()
