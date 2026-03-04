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


def bulk_create_entries(db: Session, schedule_id: str, entries_data: list[dict]) -> list[ScheduleEntry]:
    created = []
    try:
        for entry in entries_data:
            e = ScheduleEntry(
                schedule_id=schedule_id,
                date=entry.get('date'),
                start=entry.get('start'),
                end=entry.get('end'),
                name=entry.get('name'),
                description=entry.get('description'),
                notes=entry.get('notes'),
                public_event=bool(entry.get('public_event')),
            )
            db.add(e)
            # resolve relationships after flush
            created.append((e, entry))
        db.flush()
        # assign relationships
        for e_obj, src in created:
            def _resolve_ids(arr):
                if not arr:
                    return []
                out = []
                for a in arr:
                    if isinstance(a, dict):
                        if 'value' in a:
                            out.append(str(a.get('value')))
                        elif 'id' in a:
                            out.append(str(a.get('id')))
                    else:
                        out.append(str(a))
                return out

            resp_ids = _resolve_ids(src.get('responsible_ids') or src.get('responsible'))
            dev_ids = _resolve_ids(src.get('devotional_ids') or src.get('devotional'))
            cant_ids = _resolve_ids(src.get('cant_come_ids') or src.get('cant_come'))
            e_obj.responsible_users = _resolve_users(db, resp_ids)
            e_obj.devotional_users = _resolve_users(db, dev_ids)
            e_obj.cant_come_users = _resolve_users(db, cant_ids)
        db.commit()
        # refresh and return
        out = []
        for e_obj, _ in created:
            db.refresh(e_obj)
            out.append(e_obj)
        return out
    except Exception:
        db.rollback()
        raise


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


def bulk_update_entries(db: Session, schedule_id: str, updates: list[dict]) -> list[ScheduleEntry]:
    """Apply multiple entry updates in a single transaction and return updated objects.

    Each update dict must include 'id' and any update fields.
    """
    updated = []
    skipped = []
    try:
        for u in updates:
            eid = u.get('id')
            if not eid:
                skipped.append({'id': None, 'reason': 'missing id'})
                continue
            # skip local placeholder ids created by clients prior to server persistence
            if isinstance(eid, str) and eid.startswith('local-'):
                skipped.append({'id': eid, 'reason': 'local placeholder id'})
                continue
            entry = db.query(ScheduleEntry).filter(ScheduleEntry.id == eid, ScheduleEntry.schedule_id == schedule_id).first()
            if not entry:
                skipped.append({'id': eid, 'reason': 'not found or wrong schedule'})
                continue
            entry = update_entry(
                db,
                entry,
                u.get('date', None),
                u.get('start', None),
                u.get('end', None),
                u.get('name', None),
                u.get('description', None),
                u.get('notes', None),
                u.get('public_event', None),
                u.get('responsible_ids', None),
                u.get('devotional_ids', None),
                u.get('cant_come_ids', None),
            )
            updated.append(entry)
        try:
            if skipped:
                print(f"bulk_update_entries: skipped {len(skipped)} items: {skipped}")
        except Exception:
            pass
        return updated
    except Exception:
        db.rollback()
        raise
