from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.routes.auth import get_current_user
from app.core.rbac import require_org_admin_or_superadmin
from app.core.rbac import require_superadmin
from app.core.rbac import user_assigned_to_org, is_superadmin
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
    organization_id: str | None = None,
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    # If an organization filter is provided, ensure the user belongs to that org or is superadmin
    # (frontend passes organization via query in some cases)
    org_id = None
    # try to read organization_id from query params via request (FastAPI already maps explicit param, so check function signature)
    # list_schedules supports organization_id but the route doesn't expose it; respect activity_id/term_id filters only.
    # If org filter provided, ensure the requester may view that org
    if organization_id is not None:
        if not (is_superadmin(_user) or user_assigned_to_org(_user, organization_id)):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to view schedules for this organization")
        schedules = list_schedules(db, activity_id=activity_id, term_id=term_id, organization_id=organization_id)
    else:
        all_scheds = list_schedules(db, activity_id=activity_id, term_id=term_id)
        if is_superadmin(_user):
            schedules = all_scheds
        else:
            # only include global schedules or those in user's orgs
            from app.crud.organization import list_organizations_for_user

            assigned = {str(o.id) for o in list_organizations_for_user(db, _user.id)}
            schedules = [s for s in all_scheds if (s.organization_id is None) or (str(s.organization_id) in assigned)]

    return {
        "data": [
            {
                "id": schedule.id,
                "name": schedule.name,
                "term_id": schedule.term_id,
                "activity_id": schedule.activity_id,
                "organization_id": getattr(schedule, 'organization_id', None),
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
    # Require an explicit organization_id for new schedules. If the requester
    # is assigned to exactly one organization and did not provide one, default
    # to that org. Superadmins or users with multiple orgs must provide
    # `organization_id` in the payload; creating a global (null) schedule is
    # disallowed for all users.
    org_id = getattr(payload, "organization_id", None)
    try:
        from app.crud.organization import list_organizations_for_user

        assigned = list_organizations_for_user(db, _user.id)
    except Exception:
        assigned = []

    if org_id is None:
        # default to single assigned org if available
        if len(assigned) == 1:
            org_id = str(assigned[0].id)
        else:
            # require explicit org when user has multiple orgs or is superadmin
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="organization_id is required")

    # Verify the requester may create schedules for this organization
    if not (is_superadmin(_user) or user_assigned_to_org(_user, org_id)):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to create schedule for this organization")

    # Avoid creating duplicate schedules when clients race: if a schedule
    # with the same name/activity/term/organization already exists, return it.
    org_val = org_id
    q = db.query(Schedule).filter(Schedule.name == payload.name)
    q = q.filter(Schedule.term_id == payload.term_id)
    q = q.filter(Schedule.activity_id == payload.activity_id)
    if org_val is not None:
        q = q.filter(Schedule.organization_id == org_val)
    else:
        q = q.filter(Schedule.organization_id.is_(None))
    existing = q.first()
    if existing:
        schedule = existing
    else:
        schedule = create_schedule(
            db, payload.name, payload.term_id, payload.activity_id, org_val
        )
    return {
        "data": {
            "id": schedule.id,
            "name": schedule.name,
            "term_id": schedule.term_id,
            "activity_id": schedule.activity_id,
            "organization_id": getattr(schedule, 'organization_id', None),
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
    # Enforce organization membership for schedule visibility
    if getattr(schedule, 'organization_id', None):
        if not (is_superadmin(_user) or user_assigned_to_org(_user, schedule.organization_id)):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to view this schedule")

    return {
        "data": {
            "id": schedule.id,
            "name": schedule.name,
            "term_id": schedule.term_id,
            "activity_id": schedule.activity_id,
            "organization_id": getattr(schedule, 'organization_id', None),
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
    # Require org admin for the schedule's organization; if schedule is global require superadmin
    org = getattr(schedule, "organization_id", None)
    if org is None:
        require_superadmin(_user)
    else:
        require_org_admin_or_superadmin(_user, org)

    schedule = update_schedule(db, schedule, payload.name, payload.term_id, payload.activity_id)
    return {
        "data": {
            "id": schedule.id,
            "name": schedule.name,
            "term_id": schedule.term_id,
            "activity_id": schedule.activity_id,
            "organization_id": getattr(schedule, 'organization_id', None),
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
    org = getattr(schedule, "organization_id", None)
    if org is None:
        require_superadmin(_user)
    else:
        require_org_admin_or_superadmin(_user, org)

    delete_schedule(db, schedule)
    return None


@router.get("/schedules/{schedule_id}/entries")
def entries_index(
    schedule_id: str,
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    schedule = get_schedule(db, schedule_id)
    if not schedule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Schedule not found")
    if getattr(schedule, 'organization_id', None):
        if not (is_superadmin(_user) or user_assigned_to_org(_user, schedule.organization_id)):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to view entries for this schedule")

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
    # Allow any user assigned to the schedule's organization to create entries.
    org = getattr(schedule, "organization_id", None)
    if org is None:
        require_superadmin(_user)
    else:
        if not (is_superadmin(_user) or user_assigned_to_org(_user, org)):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to create entries for this schedule")
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
    # Allow any user assigned to the parent schedule's organization to update entries.
    schedule = get_schedule(db, entry.schedule_id)
    org = getattr(schedule, "organization_id", None) if schedule else None
    if org is None:
        require_superadmin(_user)
    else:
        if not (is_superadmin(_user) or user_assigned_to_org(_user, org)):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to update this entry")
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
    schedule = get_schedule(db, entry.schedule_id)
    org = getattr(schedule, "organization_id", None) if schedule else None
    if org is None:
        require_superadmin(_user)
    else:
        if not (is_superadmin(_user) or user_assigned_to_org(_user, org)):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to delete this entry")

    delete_entry(db, entry)
    return None
