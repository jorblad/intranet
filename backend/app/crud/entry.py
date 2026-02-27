from sqlalchemy.orm import Session

from app.models import ScheduleEntry, User


def list_entries(db: Session, schedule_id: str) -> list[ScheduleEntry]:
    return db.query(ScheduleEntry).filter(ScheduleEntry.schedule_id == schedule_id).all()


def get_entry(db: Session, entry_id: str) -> ScheduleEntry | None:
    return db.query(ScheduleEntry).filter(ScheduleEntry.id == entry_id).first()


def _resolve_users(db: Session, user_ids: list[str] | None) -> list[User]:
    if not user_ids:
        return []
    return db.query(User).filter(User.id.in_(user_ids)).all()


def create_entry(
    db: Session,
    schedule_id: str,
    date,
    start,
    end,
    name: str,
    description: str | None,
    notes: str | None,
    public_event: bool,
    responsible_ids: list[str],
    devotional_ids: list[str],
    cant_come_ids: list[str],
) -> ScheduleEntry:
    entry = ScheduleEntry(
        schedule_id=schedule_id,
        date=date,
        start=start,
        end=end,
        name=name,
        description=description,
        notes=notes,
        public_event=public_event,
    )
    entry.responsible_users = _resolve_users(db, responsible_ids)
    entry.devotional_users = _resolve_users(db, devotional_ids)
    entry.cant_come_users = _resolve_users(db, cant_come_ids)
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def update_entry(
    db: Session,
    entry: ScheduleEntry,
    date,
    start,
    end,
    name: str | None,
    description: str | None,
    notes: str | None,
    public_event: bool | None,
    responsible_ids: list[str] | None,
    devotional_ids: list[str] | None,
    cant_come_ids: list[str] | None,
) -> ScheduleEntry:
    if date is not None:
        entry.date = date
    if start is not None:
        entry.start = start
    if end is not None:
        entry.end = end
    if name is not None:
        entry.name = name
    if description is not None:
        entry.description = description
    if notes is not None:
        entry.notes = notes
    if public_event is not None:
        entry.public_event = public_event
    if responsible_ids is not None:
        entry.responsible_users = _resolve_users(db, responsible_ids)
    if devotional_ids is not None:
        entry.devotional_users = _resolve_users(db, devotional_ids)
    if cant_come_ids is not None:
        entry.cant_come_users = _resolve_users(db, cant_come_ids)
    db.commit()
    db.refresh(entry)
    return entry


def delete_entry(db: Session, entry: ScheduleEntry) -> None:
    db.delete(entry)
    db.commit()
