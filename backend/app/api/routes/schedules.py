from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.routes.auth import get_current_user
from app.core.rbac import require_org_admin_or_superadmin
from app.core.rbac import require_superadmin
from app.crud import (
    create_entry,
    create_schedule,
    delete_entry,
    delete_schedule,
    get_entry,
    get_schedule,
    list_entries,
    list_schedules,
    update_entry,
    update_schedule,
)
from app.db.session import get_db
from app.schemas.entry import EntryCreate, EntryUpdate
from app.schemas.schedule import ScheduleCreate, ScheduleUpdate

router = APIRouter()


def _entry_to_dict(entry):
    return {
        "id": entry.id,
        "schedule_id": entry.schedule_id,
        "date": entry.date.isoformat() if entry.date else None,
        "start": entry.start.isoformat() if getattr(entry, 'start', None) else None,
        "end": entry.end.isoformat() if getattr(entry, 'end', None) else None,
        "name": entry.name,
        "description": entry.description,
        "notes": entry.notes,
        "public_event": entry.public_event,
        "responsible_ids": [user.id for user in entry.responsible_users],
        "devotional_ids": [user.id for user in entry.devotional_users],
        "cant_come_ids": [user.id for user in entry.cant_come_users],
    }


@router.get("/schedules")
def schedules_index(
    activity_id: str | None = None,
    term_id: str | None = None,
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    schedules = list_schedules(db, activity_id=activity_id, term_id=term_id)
    return {
        "data": [
            {
                "id": schedule.id,
                "name": schedule.name,
                "term_id": schedule.term_id,
                "activity_id": schedule.activity_id,
            }
            for schedule in schedules
        ]
    }


@router.post("/schedules", status_code=status.HTTP_201_CREATED)
def schedules_create(
    payload: ScheduleCreate,
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    require_superadmin(_user)
    schedule = create_schedule(db, payload.name, payload.term_id, payload.activity_id)
    return {
        "data": {
            "id": schedule.id,
            "name": schedule.name,
            "term_id": schedule.term_id,
            "activity_id": schedule.activity_id,
        }
    }


@router.get("/schedules/{schedule_id}")
def schedules_detail(
    schedule_id: str,
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    schedule = get_schedule(db, schedule_id)
    if not schedule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Schedule not found")
    return {
        "data": {
            "id": schedule.id,
            "name": schedule.name,
            "term_id": schedule.term_id,
            "activity_id": schedule.activity_id,
        }
    }


@router.patch("/schedules/{schedule_id}")
def schedules_update(
    schedule_id: str,
    payload: ScheduleUpdate,
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    schedule = get_schedule(db, schedule_id)
    if not schedule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Schedule not found")
    require_superadmin(_user)
    schedule = update_schedule(db, schedule, payload.name, payload.term_id, payload.activity_id)
    return {
        "data": {
            "id": schedule.id,
            "name": schedule.name,
            "term_id": schedule.term_id,
            "activity_id": schedule.activity_id,
        }
    }


@router.delete("/schedules/{schedule_id}", status_code=status.HTTP_204_NO_CONTENT)
def schedules_delete(
    schedule_id: str,
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    schedule = get_schedule(db, schedule_id)
    if not schedule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Schedule not found")
    require_superadmin(_user)
    delete_schedule(db, schedule)
    return None


@router.get("/schedules/{schedule_id}/entries")
def entries_index(
    schedule_id: str,
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    entries = list_entries(db, schedule_id)
    return {"data": [_entry_to_dict(entry) for entry in entries]}


@router.post("/schedules/{schedule_id}/entries", status_code=status.HTTP_201_CREATED)
def entries_create(
    schedule_id: str,
    payload: EntryCreate,
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    schedule = get_schedule(db, schedule_id)
    if not schedule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Schedule not found")
    require_superadmin(_user)
    entry = create_entry(
        db,
        schedule_id,
        payload.date,
        getattr(payload, 'start', None),
        getattr(payload, 'end', None),
        payload.name,
        payload.description,
        payload.notes,
        payload.public_event,
        payload.responsible_ids,
        payload.devotional_ids,
        payload.cant_come_ids,
    )
    return {"data": _entry_to_dict(entry)}


@router.patch("/entries/{entry_id}")
def entries_update(
    entry_id: str,
    payload: EntryUpdate,
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    entry = get_entry(db, entry_id)
    if not entry:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entry not found")
    require_superadmin(_user)
    entry = update_entry(
        db,
        entry,
        payload.date,
        getattr(payload, 'start', None),
        getattr(payload, 'end', None),
        payload.name,
        payload.description,
        payload.notes,
        payload.public_event,
        payload.responsible_ids,
        payload.devotional_ids,
        payload.cant_come_ids,
    )
    return {"data": _entry_to_dict(entry)}


@router.delete("/entries/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
def entries_delete(
    entry_id: str,
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    entry = get_entry(db, entry_id)
    if not entry:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entry not found")
    require_superadmin(_user)
    delete_entry(db, entry)
    return None
