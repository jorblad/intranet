from sqlalchemy.orm import Session

from app.models import Schedule


def list_schedules(
    db: Session,
    activity_id: str | None = None,
    term_id: str | None = None,
    organization_id: str | None = None,
) -> list[Schedule]:
    query = db.query(Schedule)
    if activity_id:
        query = query.filter(Schedule.activity_id == activity_id)
    if term_id:
        query = query.filter(Schedule.term_id == term_id)
    if organization_id:
        query = query.filter(Schedule.organization_id == organization_id)
    return query.all()


def get_schedule(db: Session, schedule_id: str) -> Schedule | None:
    return db.query(Schedule).filter(Schedule.id == schedule_id).first()


def create_schedule(db: Session, name: str, term_id: str, activity_id: str, organization_id: str | None = None) -> Schedule:
    schedule = Schedule(name=name, term_id=term_id, activity_id=activity_id, organization_id=organization_id)
    db.add(schedule)
    db.commit()
    db.refresh(schedule)
    return schedule


def update_schedule(
    db: Session,
    schedule: Schedule,
    name: str | None,
    term_id: str | None,
    activity_id: str | None,
    organization_id: str | None = None,
) -> Schedule:
    if name is not None:
        schedule.name = name
    if term_id is not None:
        schedule.term_id = term_id
    if activity_id is not None:
        schedule.activity_id = activity_id
    if organization_id is not None:
        schedule.organization_id = organization_id
    db.commit()
    db.refresh(schedule)
    return schedule


def delete_schedule(db: Session, schedule: Schedule) -> None:
    db.delete(schedule)
    db.commit()
