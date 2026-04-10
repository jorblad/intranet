"""Tests for entry history recording and revert functionality."""
import datetime
import json
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.db.base import Base
from app.db.session import get_db
from app.models import User, Term, Schedule, ScheduleEntry
from app.models.entry_history import EntryHistory
from app.crud.entry import create_entry, update_entry, delete_entry
from app.crud.entry_history import list_entry_history, get_history_entry


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return engine


def _seed(Session):
    db = Session()
    try:
        u1 = User(username="hist_u1", display_name="User 1", hashed_password="x")
        u2 = User(username="hist_u2", display_name="User 2", hashed_password="x")
        db.add_all([u1, u2])
        t = Term(id=str(uuid.uuid4()), name="HistTerm")
        db.add(t)
        db.commit()
        s = Schedule(id=str(uuid.uuid4()), name="HistSched", term_id=t.id)
        db.add(s)
        db.commit()
        db.refresh(u1)
        db.refresh(u2)
        db.refresh(s)
        return str(u1.id), str(u2.id), str(s.id)
    finally:
        db.close()


# ---------------------------------------------------------------------------
# CRUD-level tests
# ---------------------------------------------------------------------------

def test_create_entry_records_history():
    engine = _make_engine()
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    u1_id, u2_id, schedule_id = _seed(Session)

    db = Session()
    try:
        entry = create_entry(
            db,
            schedule_id,
            datetime.date.today(),
            None,
            None,
            "Test Event",
            "desc",
            None,
            False,
            [u1_id],
            [],
            [],
            changed_by_id=u1_id,
        )
        history = list_entry_history(db, entry.id)
        assert len(history) == 1
        h = history[0]
        assert h.action == "create"
        assert h.changed_by_id == u1_id
        assert h.entry_id == entry.id
        snap = json.loads(h.snapshot)
        assert snap["name"] == "Test Event"
        assert u1_id in snap["responsible_ids"]
    finally:
        db.close()


def test_update_entry_records_history():
    engine = _make_engine()
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    u1_id, u2_id, schedule_id = _seed(Session)

    db = Session()
    try:
        entry = create_entry(
            db,
            schedule_id,
            datetime.date.today(),
            None,
            None,
            "Original",
            None,
            None,
            False,
            [],
            [],
            [],
            changed_by_id=u1_id,
        )
        entry = update_entry(
            db, entry, None, None, None, "Updated", None, None, None,
            responsible_ids=None,
            devotional_ids=None,
            cant_come_ids=None,
            changed_by_id=u2_id,
        )
        history = list_entry_history(db, entry.id)
        # 2 records: one for create, one for update
        assert len(history) == 2
        actions = {h.action for h in history}
        assert "create" in actions
        assert "update" in actions
        update_hist = next(h for h in history if h.action == "update")
        assert update_hist.changed_by_id == u2_id
        snap = json.loads(update_hist.snapshot)
        assert snap["name"] == "Updated"
    finally:
        db.close()


def test_delete_entry_records_history():
    engine = _make_engine()
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    u1_id, u2_id, schedule_id = _seed(Session)

    db = Session()
    try:
        entry = create_entry(
            db,
            schedule_id,
            datetime.date.today(),
            None,
            None,
            "ToDelete",
            None,
            None,
            False,
            [],
            [],
            [],
            changed_by_id=u1_id,
        )
        entry_id = entry.id
        delete_entry(db, entry, changed_by_id=u2_id)

        # Entry should be gone
        assert db.query(ScheduleEntry).filter(ScheduleEntry.id == entry_id).first() is None

        # History record (entry_id now NULL because of SET NULL on delete)
        history = db.query(EntryHistory).filter(EntryHistory.schedule_id == schedule_id).all()
        delete_hist = [h for h in history if h.action == "delete"]
        assert len(delete_hist) == 1
        assert delete_hist[0].changed_by_id == u2_id
    finally:
        db.close()


# ---------------------------------------------------------------------------
# HTTP route tests for /history and /revert
# ---------------------------------------------------------------------------

def _make_member_user(user_id: str, org_id: str):
    """SimpleNamespace user that satisfies RBAC helpers."""
    from types import SimpleNamespace
    role = SimpleNamespace(name="member", is_global=False)
    assignment = SimpleNamespace(role=role, organization_id=org_id)
    return SimpleNamespace(id=user_id, display_name="Member", organization_roles=[assignment])


def _make_org_admin_user(user_id: str, org_id: str):
    from types import SimpleNamespace
    role = SimpleNamespace(name="org_admin", is_global=False)
    assignment = SimpleNamespace(role=role, organization_id=org_id)
    return SimpleNamespace(id=user_id, display_name="Admin", organization_roles=[assignment])


@pytest.fixture()
def http_test_db():
    """Fixture that wires an in-memory SQLite DB into the FastAPI app for route tests.

    The ``get_db`` override is always removed in teardown (even when a test
    fails), preventing leak into subsequent tests.
    """
    from app.api.routes.auth import get_current_user

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    yield TestingSession
    app.dependency_overrides.pop(get_db, None)
    # ensure a stale user override never leaks to the next test
    app.dependency_overrides.pop(get_current_user, None)


def _seed_http_entry(Session):
    """Seed a minimal schedule+entry+history for route tests."""
    db = Session()
    try:
        org_id = str(uuid.uuid4())
        u_id = str(uuid.uuid4())
        # Create a real User so changed_by_id FK is satisfied and joinedload works
        u = User(id=u_id, username=f"http_user_{u_id[:8]}", display_name="HTTP User", hashed_password="x")
        db.add(u)
        t = Term(id=str(uuid.uuid4()), name="T")
        db.add(t)
        db.commit()
        s = Schedule(id=str(uuid.uuid4()), name="S", term_id=t.id, organization_id=org_id)
        db.add(s)
        db.commit()
        e = ScheduleEntry(schedule_id=s.id, date=datetime.date.today(), name="Entry")
        db.add(e)
        db.flush()
        hist = EntryHistory(
            entry_id=e.id,
            schedule_id=s.id,
            changed_by_id=u_id,
            changed_at=datetime.datetime.now(datetime.timezone.utc),
            action="create",
            snapshot=json.dumps({
                "id": e.id,
                "schedule_id": s.id,
                "date": e.date.isoformat(),
                "start": None,
                "end": None,
                "name": "Original Name",
                "description": None,
                "notes": None,
                "public_event": False,
                "responsible_ids": [],
                "devotional_ids": [],
                "cant_come_ids": [],
            }),
        )
        db.add(hist)
        db.commit()
        return s.id, e.id, hist.id, org_id, u_id
    finally:
        db.close()


def test_history_endpoint_returns_history(http_test_db):
    from app.api.routes.auth import get_current_user

    schedule_id, entry_id, hist_id, org_id, u_id = _seed_http_entry(http_test_db)
    user = _make_member_user(u_id, org_id)
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        client = TestClient(app)
        resp = client.get(f"/api/schedules/{schedule_id}/entries/{entry_id}/history")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) == 1
        assert data[0]["action"] == "create"
        assert data[0]["entry_id"] == entry_id
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_history_endpoint_cross_org_forbidden(http_test_db):
    """A user from a different org must not access the history endpoint."""
    from app.api.routes.auth import get_current_user

    schedule_id, entry_id, hist_id, org_id, u_id = _seed_http_entry(http_test_db)
    # Different org — this user is not assigned to `org_id`
    other_org_id = str(uuid.uuid4())
    outsider = _make_member_user(str(uuid.uuid4()), other_org_id)
    app.dependency_overrides[get_current_user] = lambda: outsider
    try:
        client = TestClient(app)
        resp = client.get(f"/api/schedules/{schedule_id}/entries/{entry_id}/history")
        assert resp.status_code == 403
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_revert_own_change_as_member(http_test_db):
    """A member can revert their own change."""
    from app.api.routes.auth import get_current_user

    schedule_id, entry_id, hist_id, org_id, u_id = _seed_http_entry(http_test_db)
    user = _make_member_user(u_id, org_id)
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        client = TestClient(app)
        resp = client.post(
            f"/api/schedules/{schedule_id}/entries/{entry_id}/revert/{hist_id}"
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["name"] == "Original Name"
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_revert_other_change_as_non_admin_forbidden(http_test_db):
    """A member cannot revert another user's change."""
    from app.api.routes.auth import get_current_user

    schedule_id, entry_id, hist_id, org_id, u_id = _seed_http_entry(http_test_db)
    # A different user in the same org
    other_u_id = str(uuid.uuid4())
    user = _make_member_user(other_u_id, org_id)
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        client = TestClient(app)
        resp = client.post(
            f"/api/schedules/{schedule_id}/entries/{entry_id}/revert/{hist_id}"
        )
        assert resp.status_code == 403
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_revert_by_org_admin_allowed(http_test_db):
    """An org admin can revert any change in their org."""
    from app.api.routes.auth import get_current_user

    schedule_id, entry_id, hist_id, org_id, u_id = _seed_http_entry(http_test_db)
    # Seed a real User for the admin so changed_by_id FK is satisfied on revert
    admin_id = str(uuid.uuid4())
    db = http_test_db()
    try:
        db.add(User(id=admin_id, username=f"org_admin_{admin_id[:8]}", display_name="Org Admin", hashed_password="x"))
        db.commit()
    finally:
        db.close()
    user = _make_org_admin_user(admin_id, org_id)
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        client = TestClient(app)
        resp = client.post(
            f"/api/schedules/{schedule_id}/entries/{entry_id}/revert/{hist_id}"
        )
        assert resp.status_code == 200
    finally:
        app.dependency_overrides.pop(get_current_user, None)
