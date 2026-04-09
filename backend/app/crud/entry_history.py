import json
import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session, joinedload

from app.models import EntryHistory, ScheduleEntry

logger = logging.getLogger(__name__)


def _entry_snapshot(entry: ScheduleEntry) -> str:
    """Return a JSON snapshot of the current entry state."""
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
            "responsible_ids": [str(u.id) for u in (entry.responsible_users or [])],
            "devotional_ids": [str(u.id) for u in (entry.devotional_users or [])],
            "cant_come_ids": [str(u.id) for u in (entry.cant_come_users or [])],
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
        snapshot=_entry_snapshot(entry),
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
