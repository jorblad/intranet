import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

from app.api.routes.auth import get_current_user
from app.core.rbac import require_org_admin_or_superadmin
from app.core.rbac import require_superadmin
from app.core.rbac import user_assigned_to_org, is_superadmin, user_has_role
from app.models import Schedule

# TestClient-based route tests for schedules/entries bulk APIs
from fastapi import FastAPI
import sys
import types
from types import SimpleNamespace
from app.crud import (
    create_entry,
    create_schedule,
    delete_entry,
    delete_schedule,
    get_entry,
    get_schedule,
    list_entries,
    list_schedules,
    revert_entry,
    update_entry,
    update_schedule,
    get_history_entry,
    list_entry_history,
)
from app.db.session import get_db
from app.schemas.entry import EntryCreate, EntryUpdate, EntryBulkUpdate
from typing import List
from app.schemas.entry import EntryBase
from app.schemas.schedule import ScheduleCreate, ScheduleUpdate
import asyncio
import json
import os

# reuse the ws pubsub instance so published messages are forwarded to connected websockets
from app.api.routes.ws import _pubsub

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
        try:
            schedule = create_schedule(
                db, payload.name, payload.term_id, payload.activity_id, org_val
            )
        except Exception as e:
            # Log the exception for debugging and return a 500 with a concise message
            import traceback
            traceback.print_exc()
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
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
        changed_by_id=getattr(_user, 'id', None),
    )
    return {"data": _entry_to_dict(entry)}


@router.patch("/schedules/{schedule_id}/entries/bulk", status_code=status.HTTP_200_OK)
def entries_bulk_update(
    schedule_id: str,
    payload: List[EntryBulkUpdate],
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
        if not (is_superadmin(_user) or user_assigned_to_org(_user, org)):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to update entries for this schedule")

    try:
        from app.crud.entry import bulk_update_entries
        updates = [p.model_dump(exclude_unset=True) for p in payload]
        logger.debug("entries_bulk_update: received %d updates", len(updates))
        # Filter out client-local placeholder ids (e.g., 'local-...') which are not persisted
        filtered = []
        skipped = []
        for u in updates:
            eid = u.get('id')
            if isinstance(eid, str) and eid.startswith('local-'):
                skipped.append(eid)
                continue
            filtered.append(u)
        if skipped:
            logger.debug("entries_bulk_update: filtered out %d local placeholder ids: %s", len(skipped), skipped)
        updated = bulk_update_entries(db, schedule_id, filtered, changed_by_id=getattr(_user, 'id', None))
    except ValueError as e:
        # Validation / client errors (e.g., missing id or invalid ownership) -> 400
        logger.warning("entries_bulk_update validation error for schedule %s: %s", schedule_id, e)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        # Unexpected server error: log full traceback for debugging
        logger.exception("entries_bulk_update unexpected error for schedule %s", schedule_id)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")

    # publish a notification to other connected clients so they can refresh
    try:
        # publish rows mapping so the frontend Orbit handler can apply them
        rows_map = {schedule_id: [_entry_to_dict(e) for e in updated]}
        transform = {"rows": rows_map}
        payload = {"type": "transform", "transform": transform}
        envelope = json.dumps({"__origin_pid": os.getpid(), "payload": payload})
        try:
            print(f"entries_bulk_update: scheduling publish envelope (len={len(envelope)}) preview={envelope[:200]}")
            _pubsub.schedule_publish(envelope)
        except Exception:
            pass
    except Exception:
        pass

    return {"data": [_entry_to_dict(e) for e in updated]}


# --- Embedded route-level tests for entries_bulk_update ---
# These tests use FastAPI's TestClient to exercise the bulk update endpoint
# for authorization behavior and payload handling semantics.

def _build_test_app():
    """
    Construct a minimal FastAPI app including this router for TestClient-based tests.
    """
    app = FastAPI()
    app.include_router(router)
    return app


def _set_fake_bulk_update_entries(fake_func):
    """
    Ensure that `from app.crud.entry import bulk_update_entries` inside
    entries_bulk_update resolves to `fake_func` during tests by populating
    sys.modules['app.crud.entry'].
    """
    # Ensure package structure exists
    if "app" not in sys.modules:
        sys.modules["app"] = types.ModuleType("app")
    if "app.crud" not in sys.modules:
        crud_mod = types.ModuleType("app.crud")
        sys.modules["app.crud"] = crud_mod
    else:
        crud_mod = sys.modules["app.crud"]

    entry_mod_name = "app.crud.entry"
    entry_mod = types.ModuleType(entry_mod_name)
    entry_mod.bulk_update_entries = fake_func
    sys.modules[entry_mod_name] = entry_mod


def _override_schedule_and_rbac(app, schedule_obj, assigned_to_org: bool, superadmin: bool):
    """
    Override get_schedule, user_assigned_to_org, and is_superadmin behavior
    for tests by monkeypatching symbols in this module.
    """
    # Override get_schedule by dependency override on get_db combined with local closure.
    # We patch at module level since get_schedule is imported, not a dependency.
    global get_schedule, user_assigned_to_org, is_superadmin

    original_get_schedule = get_schedule
    original_user_assigned_to_org = user_assigned_to_org
    original_is_superadmin = is_superadmin

    def fake_get_schedule(_db, _schedule_id):
        return schedule_obj

    def fake_user_assigned_to_org(_user, _org_id):
        return assigned_to_org

    def fake_is_superadmin(_user):
        return superadmin

    get_schedule = fake_get_schedule
    user_assigned_to_org = fake_user_assigned_to_org
    is_superadmin = fake_is_superadmin

    # Return a restore function so each test can clean up.
    def restore():
        global get_schedule, user_assigned_to_org, is_superadmin
        get_schedule = original_get_schedule
        user_assigned_to_org = original_user_assigned_to_org
        is_superadmin = original_is_superadmin

    return restore


def _override_dependencies(app, user):
    """
    Override get_current_user and get_db for tests to avoid touching real auth/DB.
    """
    def fake_get_current_user():
        return user

    def fake_get_db():
        class DummyDB:
            pass

        return DummyDB()

    app.dependency_overrides[get_current_user] = fake_get_current_user
    app.dependency_overrides[get_db] = fake_get_db


def test_entries_bulk_update_forbidden_for_user_not_assigned_to_org():
    """
    (1) 403 for users not assigned to the org.
    """
    app = _build_test_app()
    _override_dependencies(app, user={"id": "user-1"})

    # Schedule with an organization; user is not assigned and not superadmin.
    schedule = SimpleNamespace(id="sched-1", organization_id="org-1")
    restore = _override_schedule_and_rbac(app, schedule, assigned_to_org=False, superadmin=False)

    # We don't need bulk_update_entries here because the request should be rejected
    # by authorization before any DB logic executes.
    from fastapi.testclient import TestClient
    client = TestClient(app)

    response = client.patch(
        f"/schedules/{schedule.id}/entries/bulk",
        json=[{"id": "entry-1"}],
    )

    restore()

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json().get("detail") == "Not authorized to update entries for this schedule"


def test_entries_bulk_update_success_path_updates():
    """
    (2) Success path: authorized user gets 200 and updated entries.
    """
    app = _build_test_app()
    _override_dependencies(app, user={"id": "user-2"})

    schedule = SimpleNamespace(id="sched-2", organization_id="org-2")
    restore = _override_schedule_and_rbac(app, schedule, assigned_to_org=True, superadmin=False)

    def fake_bulk_update_entries(_db, _schedule, payload, changed_by_id=None):
        # Echo back payload as "updated" entries with an extra field to prove it ran.
        from types import SimpleNamespace as SN
        import datetime
        out = []
        for p in payload:
            ent = SN()
            ent.id = p.get('id') or 'entry-created'
            ent.schedule_id = _schedule
            # normalize date if provided as ISO string
            dt = p.get('date')
            if isinstance(dt, str):
                try:
                    ent.date = datetime.date.fromisoformat(dt)
                except Exception:
                    ent.date = None
            else:
                ent.date = dt
            ent.start = None
            ent.end = None
            ent.name = p.get('name')
            ent.description = p.get('description')
            ent.notes = p.get('notes')
            ent.public_event = p.get('public_event', False)
            ent.responsible_users = [SN(id=x) for x in (p.get('responsible_ids') or [])]
            ent.devotional_users = [SN(id=x) for x in (p.get('devotional_ids') or [])]
            ent.cant_come_users = [SN(id=x) for x in (p.get('cant_come_ids') or [])]
            out.append(ent)
        return out

    # Install our fake bulk updater and exercise the endpoint
    _set_fake_bulk_update_entries(fake_bulk_update_entries)
    from fastapi.testclient import TestClient
    client = TestClient(app)
    payload = [{"id": "entry-1", "name": "Name 1"}]
    response = client.patch(f"/schedules/{schedule.id}/entries/bulk", json=payload)
    restore()
    assert response.status_code == status.HTTP_200_OK
    data = response.json().get("data")
    assert isinstance(data, list)
    assert len(data) == len(payload)
    assert data[0]["name"] == "Name 1"
def entries_bulk_create(
    schedule_id: str,
    payload: List[EntryCreate],
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
        if not (is_superadmin(_user) or user_assigned_to_org(_user, org)):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to create entries for this schedule")

    # normalize payload to list of dicts suitable for bulk create
    entries_data = []
    for p in payload:
        entries_data.append(p.model_dump())

    try:
        from app.crud.entry import bulk_create_entries

        created = bulk_create_entries(db, schedule_id, entries_data, changed_by_id=getattr(_user, 'id', None))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

    # publish created entries so other clients receive authoritative entries
    try:
        rows_map = {schedule_id: [_entry_to_dict(e) for e in created]}
        transform = {"rows": rows_map}
        payload = {"type": "transform", "transform": transform}
        envelope = json.dumps({"__origin_pid": os.getpid(), "payload": payload})
        try:
            print(f"entries_bulk_create: scheduling publish envelope (len={len(envelope)}) preview={envelope[:200]}")
            _pubsub.schedule_publish(envelope)
        except Exception:
            pass
    except Exception:
        pass

    return {"data": [_entry_to_dict(e) for e in created]}


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
        changed_by_id=getattr(_user, 'id', None),
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

    delete_entry(db, entry, changed_by_id=getattr(_user, 'id', None))
    return None


def _history_to_dict(hist):
    return {
        "id": hist.id,
        "entry_id": hist.entry_id,
        "schedule_id": hist.schedule_id,
        "changed_by_id": hist.changed_by_id,
        "changed_by_name": hist.changed_by.display_name if hist.changed_by else None,
        "changed_at": hist.changed_at.isoformat() if hist.changed_at else None,
        "action": hist.action,
        "snapshot": hist.snapshot,
    }


@router.get("/schedules/{schedule_id}/entries/{entry_id}/history")
def entry_history_list(
    schedule_id: str,
    entry_id: str,
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    schedule = get_schedule(db, schedule_id)
    if not schedule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Schedule not found")
    if getattr(schedule, 'organization_id', None):
        if not (is_superadmin(_user) or user_assigned_to_org(_user, schedule.organization_id)):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")

    entry = get_entry(db, entry_id)
    if not entry or entry.schedule_id != schedule_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entry not found")

    history = list_entry_history(db, entry_id)
    return {"data": [_history_to_dict(h) for h in history]}


@router.post("/schedules/{schedule_id}/entries/{entry_id}/revert/{history_id}", status_code=status.HTTP_200_OK)
def entry_revert(
    schedule_id: str,
    entry_id: str,
    history_id: str,
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    import json as _json

    schedule = get_schedule(db, schedule_id)
    if not schedule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Schedule not found")

    org = getattr(schedule, 'organization_id', None)

    # Retrieve the history record
    hist = get_history_entry(db, history_id)
    if not hist or hist.entry_id != entry_id or hist.schedule_id != schedule_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="History record not found")

    user_id = getattr(_user, 'id', None)

    # Authorization: org admin (or superadmin) can revert any change; a regular
    # member can only revert their own changes if they still have access to the org.
    is_admin = is_superadmin(_user) or (org is not None and user_has_role(_user, "org_admin", org))
    has_org_access = org is not None and user_assigned_to_org(_user, org)
    is_own_change = user_id and hist.changed_by_id and str(hist.changed_by_id) == str(user_id)

    if not is_admin and not (has_org_access and is_own_change):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to revert this change",
        )

    entry = get_entry(db, entry_id)
    if not entry:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entry not found")
    if entry.schedule_id != schedule_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entry not found")

    # Parse snapshot and apply
    try:
        snap = _json.loads(hist.snapshot)
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid history snapshot")

    # Apply snapshot directly so that explicit-null fields (start, end,
    # description, notes …) are cleared rather than left unchanged.
    entry = revert_entry(db, entry, snap, changed_by_id=user_id)

    # Publish so other connected clients refresh
    try:
        rows_map = {schedule_id: [_entry_to_dict(entry)]}
        transform = {"rows": rows_map}
        pub_payload = {"type": "transform", "transform": transform}
        envelope = json.dumps({"__origin_pid": os.getpid(), "payload": pub_payload})
        _pubsub.schedule_publish(envelope)
    except Exception:
        logger.warning("revert_entry: failed to publish pubsub notification for schedule %s", schedule_id, exc_info=True)

    return {"data": _entry_to_dict(entry)}
