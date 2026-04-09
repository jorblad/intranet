from sqlalchemy.orm import Session

from app.models import ScheduleEntry, User
from app.crud.entry_history import record_history
import logging

logger = logging.getLogger(__name__)

def list_entries(db: Session, schedule_id: str) -> list[ScheduleEntry]:
    return db.query(ScheduleEntry).filter(ScheduleEntry.schedule_id == schedule_id).all()


def _ensure_list_ids(val):
    """Normalize various id-list shapes into a list of string ids."""
    if val is None:
        return []
    # If a single string id is provided, wrap it in a list to avoid
    # iterating over its characters.
    if isinstance(val, str):
        return [val]
    out = []
    try:
        for a in val:
            if isinstance(a, dict):
                v = a.get('value') or a.get('id') or a.get('user_id')
                if v is not None:
                    out.append(str(v))
            else:
                out.append(str(a))
    except Exception:
        # Fallback: try to coerce the whole thing to a single string id
        try:
            return [str(val)]
        except Exception:
            return []
    return out


def _sanitize_assignment_lists(responsible_ids, devotional_ids, cant_come_ids):
    """Return (responsible, devotional, cant_come) lists where any id present
    in cant_come is removed from responsible and devotional. Dedupe order-preserving.
    """
    resp = _ensure_list_ids(responsible_ids)
    devo = _ensure_list_ids(devotional_ids)
    cant = _ensure_list_ids(cant_come_ids)

    cant_set = set(cant)

    def _uniq_keep_order(seq):
        seen = set()
        out = []
        for x in seq:
            if x in seen:
                continue
            seen.add(x)
            out.append(x)
        return out

    resp_filtered = [r for r in resp if r not in cant_set]
    devo_filtered = [d for d in devo if d not in cant_set]

    return _uniq_keep_order(resp_filtered), _uniq_keep_order(devo_filtered), _uniq_keep_order(cant)


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
    changed_by_id: str | None = None,
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
    # sanitize so cant_come dominates (users in cant_come are removed from other assignments)
    r_ids, d_ids, c_ids = _sanitize_assignment_lists(responsible_ids, devotional_ids, cant_come_ids)
    entry.responsible_users = _resolve_users(db, r_ids)
    entry.devotional_users = _resolve_users(db, d_ids)
    entry.cant_come_users = _resolve_users(db, c_ids)
    db.add(entry)
    db.flush()
    record_history(db, entry, "create", changed_by_id)
    db.commit()
    db.refresh(entry)
    return entry


def bulk_create_entries(db: Session, schedule_id: str, entries_data: list[dict], changed_by_id: str | None = None) -> list[ScheduleEntry]:
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
        # assign relationships (sanitize so cant_come dominates)
        for e_obj, src in created:
            resp_ids = src.get('responsible_ids') or src.get('responsible')
            dev_ids = src.get('devotional_ids') or src.get('devotional')
            cant_ids = src.get('cant_come_ids') or src.get('cant_come')
            r_ids, d_ids, c_ids = _sanitize_assignment_lists(resp_ids, dev_ids, cant_ids)
            e_obj.responsible_users = _resolve_users(db, r_ids)
            e_obj.devotional_users = _resolve_users(db, d_ids)
            e_obj.cant_come_users = _resolve_users(db, c_ids)
        db.flush()
        # record history after relationships are set
        for e_obj, _ in created:
            record_history(db, e_obj, "create", changed_by_id)
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


def _update_entry_in_session(
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
    commit: bool = True,
    changed_by_id: str | None = None,
    action: str = "update",
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
    # Normalize and enforce cant_come dominance when any of the assignment
    # lists are being modified. If a list is None, use the current persisted
    # values so that simultaneous changes (e.g., adding cant_come) remove
    # users from other assignments.
    relationships_modified = False
    if responsible_ids is not None or devotional_ids is not None or cant_come_ids is not None:
        existing_resp = [str(u.id) for u in (entry.responsible_users or [])]
        existing_devo = [str(u.id) for u in (entry.devotional_users or [])]
        existing_cant = [str(u.id) for u in (entry.cant_come_users or [])]

        final_resp_src = responsible_ids if responsible_ids is not None else existing_resp
        final_devo_src = devotional_ids if devotional_ids is not None else existing_devo
        final_cant_src = cant_come_ids if cant_come_ids is not None else existing_cant

        r_ids, d_ids, c_ids = _sanitize_assignment_lists(final_resp_src, final_devo_src, final_cant_src)

        entry.responsible_users = _resolve_users(db, r_ids)
        entry.devotional_users = _resolve_users(db, d_ids)
        entry.cant_come_users = _resolve_users(db, c_ids)
        relationships_modified = True
    # Flush only when relationship/association-table changes are pending so
    # _entry_snapshot queries see the updated rows without an extra roundtrip
    # on scalar-only updates.
    if relationships_modified:
        db.flush()
    record_history(db, entry, action, changed_by_id)
    if commit:
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
    changed_by_id: str | None = None,
    action: str = "update",
) -> ScheduleEntry:
    return _update_entry_in_session(
        db,
        entry,
        date,
        start,
        end,
        name,
        description,
        notes,
        public_event,
        responsible_ids,
        devotional_ids,
        cant_come_ids,
        changed_by_id=changed_by_id,
        action=action,
    )


def delete_entry(db: Session, entry: ScheduleEntry, changed_by_id: str | None = None) -> None:
    record_history(db, entry, "delete", changed_by_id)
    db.delete(entry)
    db.commit()


def bulk_update_entries(db: Session, schedule_id: str, updates: list[dict], changed_by_id: str | None = None) -> list[ScheduleEntry]:
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
            entry = _update_entry_in_session(
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
                commit=False,
                changed_by_id=changed_by_id,
            )
            updated.append(entry)
        db.commit()
        # refresh updated entries before returning
        for entry in updated:
            db.refresh(entry)
        if skipped:
            logger.info("bulk_update_entries: skipped %d items", len(skipped))
            logger.debug("bulk_update_entries skipped details: %r", skipped)
        return updated
    except Exception:
        db.rollback()
        raise
