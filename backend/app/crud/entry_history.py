import json
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models import EntryHistory, ScheduleEntry
from app.models.schedule_entry import entry_responsible, entry_devotional, entry_cant_come

logger = logging.getLogger(__name__)


def _entry_snapshot(entry: ScheduleEntry, db: Session) -> str:
    """Return a JSON snapshot of the current entry state.

    Queries the association tables directly to avoid triggering lazy loads
    (which would cause 3 extra SELECTs per call when the relationships are
    not already present in the session identity map).
    """
    responsible_ids = [
        str(r) for (r,) in db.execute(
            select(entry_responsible.c.user_id).where(entry_responsible.c.entry_id == entry.id)
        )
    ]
    devotional_ids = [
        str(r) for (r,) in db.execute(
            select(entry_devotional.c.user_id).where(entry_devotional.c.entry_id == entry.id)
        )
    ]
    cant_come_ids = [
        str(r) for (r,) in db.execute(
            select(entry_cant_come.c.user_id).where(entry_cant_come.c.entry_id == entry.id)
        )
    ]
    return json.dumps(
        {
            "id": entry.id,
            "schedule_id": entry.schedule_id,
            "date": entry.date.isoformat() if entry.date else None,
            "start": entry.start.isoformat() if getattr(entry, "start", None) else None,
            "end": entry.end.isoformat() if getattr(entry, "end", None) else None,
            "name": entry.name,
            "description": entry.description,
            "notes": entry.notes,
            "public_event": entry.public_event,
            "responsible_ids": responsible_ids,
            "devotional_ids": devotional_ids,
            "cant_come_ids": cant_come_ids,
        }
    )


def record_history(
    db: Session,
    entry: ScheduleEntry,
    action: str,
    changed_by_id: str | None = None,
) -> EntryHistory:
    """Record a history entry for a schedule entry change.

    This must be called **before** any delete so that relationship data is
    still accessible for snapshotting.
    """
    hist = EntryHistory(
        entry_id=entry.id,
        schedule_id=entry.schedule_id,
        changed_by_id=changed_by_id,
        changed_at=datetime.now(timezone.utc),
        action=action,
        snapshot=_entry_snapshot(entry, db),
    )
    db.add(hist)
    return hist


def list_entry_history(
    db: Session, entry_id: str, limit: int = 50
) -> list[EntryHistory]:
    """Return history records for a specific entry, newest first."""
    return (
        db.query(EntryHistory)
        .options(joinedload(EntryHistory.changed_by))
        .filter(EntryHistory.entry_id == entry_id)
        .order_by(EntryHistory.changed_at.desc())
        .limit(limit)
        .all()
    )


def list_schedule_history(
    db: Session, schedule_id: str, limit: int = 100
) -> list[EntryHistory]:
    """Return history records for all entries in a schedule, newest first."""
    return (
        db.query(EntryHistory)
        .options(joinedload(EntryHistory.changed_by))
        .filter(EntryHistory.schedule_id == schedule_id)
        .order_by(EntryHistory.changed_at.desc())
        .limit(limit)
        .all()
    )


def get_history_entry(db: Session, history_id: str) -> EntryHistory | None:
    return db.query(EntryHistory).filter(EntryHistory.id == history_id).first()
