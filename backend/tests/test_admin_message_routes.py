"""
Tests for the /api/admin/messages endpoints covering:
  - member visibility (list org/global messages)
  - member write-prohibition (create/update/delete returns 403)
  - org_admin can manage org-scoped messages, but not global ones
  - global org_admin / superadmin can manage global messages
  - start/end active-window filtering
  - placement filtering
"""
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.api.routes.auth import get_current_user
from app.db.base import Base
from app.db.session import get_db
from app.models import AdminMessage, Organization, Role, User, UserOrganizationRole


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="function")
def test_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, expire_on_commit=False
    )
    Base.metadata.create_all(bind=engine)

    def _get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _get_db
    yield TestingSessionLocal
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def client(test_db):
    return TestClient(app)


# ---------------------------------------------------------------------------
# Helper: build SimpleNamespace users that satisfy RBAC helpers
# ---------------------------------------------------------------------------


def _make_member(org_id: str):
    """A plain member with an org assignment but no admin role."""
    role = SimpleNamespace(name="member", is_global=False)
    assignment = SimpleNamespace(role=role, organization_id=org_id)
    return SimpleNamespace(id=str(uuid.uuid4()), organization_roles=[assignment])


def _make_org_admin(org_id: str):
    """org_admin for a specific (non-global) organization."""
    role = SimpleNamespace(name="org_admin", is_global=False)
    assignment = SimpleNamespace(role=role, organization_id=org_id)
    return SimpleNamespace(id=str(uuid.uuid4()), organization_roles=[assignment])


def _make_global_org_admin():
    """org_admin whose role has is_global=True (can manage global messages)."""
    role = SimpleNamespace(name="org_admin", is_global=True)
    assignment = SimpleNamespace(role=role, organization_id=None)
    return SimpleNamespace(id=str(uuid.uuid4()), organization_roles=[assignment])


def _make_superadmin():
    """superadmin user."""
    role = SimpleNamespace(name="superadmin", is_global=True)
    assignment = SimpleNamespace(role=role, organization_id=None)
    return SimpleNamespace(id=str(uuid.uuid4()), organization_roles=[assignment])


def _override_user(user):
    app.dependency_overrides[get_current_user] = lambda: user


# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------


def _seed_org(Session) -> str:
    db = Session()
    try:
        org = Organization(id=str(uuid.uuid4()), name=f"TestOrg-{uuid.uuid4().hex[:6]}")
        db.add(org)
        db.commit()
        return org.id
    finally:
        db.close()


def _seed_message(Session, org_id=None, placement="banner", start=None, end=None, priority=0) -> str:
    db = Session()
    try:
        msg = AdminMessage(
            id=str(uuid.uuid4()),
            title="Test message",
            body="Body text",
            organization_id=org_id,
            placement=placement,
            start=start,
            end=end,
            priority=priority,
        )
        db.add(msg)
        db.commit()
        return msg.id
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 1. Member visibility: list org and global messages
# ---------------------------------------------------------------------------


def test_member_can_list_global_messages(client, test_db):
    """A member with no org_id query can retrieve global messages."""
    _seed_message(test_db, org_id=None)
    member = _make_member(org_id=str(uuid.uuid4()))
    _override_user(member)
    res = client.get("/api/admin/messages")
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)
    assert len(data) >= 1


def test_member_can_list_org_messages_for_assigned_org(client, test_db):
    """A member can list messages for their own org (org-scoped + global)."""
    org_id = _seed_org(test_db)
    _seed_message(test_db, org_id=org_id)
    _seed_message(test_db, org_id=None)

    member = _make_member(org_id=org_id)
    _override_user(member)

    res = client.get(f"/api/admin/messages?organization_id={org_id}")
    assert res.status_code == 200
    data = res.json()
    # Should include the org-specific message and the global one
    assert len(data) >= 2


def test_member_cannot_list_messages_for_unassigned_org(client, test_db):
    """A member cannot view messages for an org they don't belong to."""
    org_id = _seed_org(test_db)
    other_org_id = _seed_org(test_db)
    member = _make_member(org_id=org_id)
    _override_user(member)

    res = client.get(f"/api/admin/messages?organization_id={other_org_id}")
    assert res.status_code == 403


# ---------------------------------------------------------------------------
# 2. Member write-prohibition
# ---------------------------------------------------------------------------


def test_member_cannot_create_message(client, test_db):
    org_id = _seed_org(test_db)
    member = _make_member(org_id=org_id)
    _override_user(member)

    res = client.post(
        "/api/admin/messages",
        json={"title": "New msg", "organization_id": org_id},
    )
    assert res.status_code == 403


def test_member_cannot_create_global_message(client, test_db):
    member = _make_member(org_id=str(uuid.uuid4()))
    _override_user(member)

    res = client.post("/api/admin/messages", json={"title": "Global msg"})
    assert res.status_code == 403


def test_member_cannot_update_message(client, test_db):
    org_id = _seed_org(test_db)
    msg_id = _seed_message(test_db, org_id=org_id)
    member = _make_member(org_id=org_id)
    _override_user(member)

    res = client.patch(f"/api/admin/messages/{msg_id}", json={"title": "Updated"})
    assert res.status_code == 403


def test_member_cannot_delete_message(client, test_db):
    org_id = _seed_org(test_db)
    msg_id = _seed_message(test_db, org_id=org_id)
    member = _make_member(org_id=org_id)
    _override_user(member)

    res = client.delete(f"/api/admin/messages/{msg_id}")
    assert res.status_code == 403


# ---------------------------------------------------------------------------
# 3. org_admin: manage org-scoped messages, but NOT global
# ---------------------------------------------------------------------------


def test_org_admin_can_create_org_scoped_message(client, test_db):
    org_id = _seed_org(test_db)
    admin = _make_org_admin(org_id=org_id)
    _override_user(admin)

    res = client.post(
        "/api/admin/messages",
        json={"title": "Org msg", "organization_id": org_id},
    )
    assert res.status_code == 201
    data = res.json()
    assert data["organization_id"] == org_id


def test_org_admin_can_update_org_scoped_message(client, test_db):
    org_id = _seed_org(test_db)
    msg_id = _seed_message(test_db, org_id=org_id)
    admin = _make_org_admin(org_id=org_id)
    _override_user(admin)

    res = client.patch(f"/api/admin/messages/{msg_id}", json={"title": "Updated by admin"})
    assert res.status_code == 200
    assert res.json()["title"] == "Updated by admin"


def test_org_admin_can_delete_org_scoped_message(client, test_db):
    org_id = _seed_org(test_db)
    msg_id = _seed_message(test_db, org_id=org_id)
    admin = _make_org_admin(org_id=org_id)
    _override_user(admin)

    res = client.delete(f"/api/admin/messages/{msg_id}")
    assert res.status_code == 204


def test_org_admin_cannot_create_global_message(client, test_db):
    org_id = _seed_org(test_db)
    admin = _make_org_admin(org_id=org_id)
    _override_user(admin)

    res = client.post("/api/admin/messages", json={"title": "Global msg"})
    assert res.status_code == 403


def test_org_admin_cannot_update_global_message(client, test_db):
    msg_id = _seed_message(test_db, org_id=None)
    org_id = _seed_org(test_db)
    admin = _make_org_admin(org_id=org_id)
    _override_user(admin)

    res = client.patch(f"/api/admin/messages/{msg_id}", json={"title": "No permission"})
    assert res.status_code == 403


def test_org_admin_cannot_delete_global_message(client, test_db):
    msg_id = _seed_message(test_db, org_id=None)
    org_id = _seed_org(test_db)
    admin = _make_org_admin(org_id=org_id)
    _override_user(admin)

    res = client.delete(f"/api/admin/messages/{msg_id}")
    assert res.status_code == 403


def test_org_admin_cannot_manage_another_orgs_message(client, test_db):
    org_id = _seed_org(test_db)
    other_org_id = _seed_org(test_db)
    msg_id = _seed_message(test_db, org_id=other_org_id)
    admin = _make_org_admin(org_id=org_id)
    _override_user(admin)

    res = client.patch(f"/api/admin/messages/{msg_id}", json={"title": "Nope"})
    assert res.status_code == 403

    res = client.delete(f"/api/admin/messages/{msg_id}")
    assert res.status_code == 403


# ---------------------------------------------------------------------------
# 4. global org_admin / superadmin: manage global messages
# ---------------------------------------------------------------------------


def test_global_org_admin_can_create_global_message(client, test_db):
    admin = _make_global_org_admin()
    _override_user(admin)

    res = client.post("/api/admin/messages", json={"title": "Global"})
    assert res.status_code == 201
    assert res.json()["organization_id"] is None


def test_global_org_admin_can_update_global_message(client, test_db):
    msg_id = _seed_message(test_db, org_id=None)
    admin = _make_global_org_admin()
    _override_user(admin)

    res = client.patch(f"/api/admin/messages/{msg_id}", json={"title": "Updated global"})
    assert res.status_code == 200
    assert res.json()["title"] == "Updated global"


def test_global_org_admin_can_delete_global_message(client, test_db):
    msg_id = _seed_message(test_db, org_id=None)
    admin = _make_global_org_admin()
    _override_user(admin)

    res = client.delete(f"/api/admin/messages/{msg_id}")
    assert res.status_code == 204


def test_superadmin_can_create_global_message(client, test_db):
    superadmin = _make_superadmin()
    _override_user(superadmin)

    res = client.post("/api/admin/messages", json={"title": "Superadmin global"})
    assert res.status_code == 201
    assert res.json()["organization_id"] is None


def test_superadmin_can_create_org_scoped_message(client, test_db):
    org_id = _seed_org(test_db)
    superadmin = _make_superadmin()
    _override_user(superadmin)

    res = client.post(
        "/api/admin/messages",
        json={"title": "Superadmin org msg", "organization_id": org_id},
    )
    assert res.status_code == 201
    assert res.json()["organization_id"] == org_id


def test_superadmin_can_update_and_delete_any_message(client, test_db):
    org_id = _seed_org(test_db)
    org_msg_id = _seed_message(test_db, org_id=org_id)
    global_msg_id = _seed_message(test_db, org_id=None)
    superadmin = _make_superadmin()
    _override_user(superadmin)

    res = client.patch(f"/api/admin/messages/{org_msg_id}", json={"title": "SA updated org"})
    assert res.status_code == 200

    res = client.patch(f"/api/admin/messages/{global_msg_id}", json={"title": "SA updated global"})
    assert res.status_code == 200

    res = client.delete(f"/api/admin/messages/{org_msg_id}")
    assert res.status_code == 204

    res = client.delete(f"/api/admin/messages/{global_msg_id}")
    assert res.status_code == 204


# ---------------------------------------------------------------------------
# 5. start/end active-window filtering
# ---------------------------------------------------------------------------


def test_active_filter_excludes_not_yet_started(client, test_db):
    """Messages whose start is in the future should not appear when active=true."""
    future = datetime.now(timezone.utc) + timedelta(hours=1)
    _seed_message(test_db, org_id=None, start=future)

    member = _make_member(org_id=str(uuid.uuid4()))
    _override_user(member)

    res = client.get("/api/admin/messages?active=true")
    assert res.status_code == 200
    data = res.json()
    for item in data:
        if item["start"] is not None:
            assert datetime.fromisoformat(item["start"]) <= datetime.now(timezone.utc)


def test_active_filter_excludes_already_ended(client, test_db):
    """Messages whose end is in the past should not appear when active=true."""
    past = datetime.now(timezone.utc) - timedelta(hours=1)
    _seed_message(test_db, org_id=None, end=past)

    member = _make_member(org_id=str(uuid.uuid4()))
    _override_user(member)

    res = client.get("/api/admin/messages?active=true")
    assert res.status_code == 200
    data = res.json()
    for item in data:
        if item["end"] is not None:
            assert datetime.fromisoformat(item["end"]) >= datetime.now(timezone.utc)


def test_active_false_includes_expired_messages(client, test_db):
    """With active=false, expired messages are included."""
    past = datetime.now(timezone.utc) - timedelta(hours=2)
    msg_id = _seed_message(test_db, org_id=None, end=past)

    member = _make_member(org_id=str(uuid.uuid4()))
    _override_user(member)

    res = client.get("/api/admin/messages?active=false")
    assert res.status_code == 200
    ids = [item["id"] for item in res.json()]
    assert msg_id in ids


def test_active_filter_includes_message_within_window(client, test_db):
    """A message within its start-end window should appear when active=true."""
    past = datetime.now(timezone.utc) - timedelta(hours=1)
    future = datetime.now(timezone.utc) + timedelta(hours=1)
    msg_id = _seed_message(test_db, org_id=None, start=past, end=future)

    member = _make_member(org_id=str(uuid.uuid4()))
    _override_user(member)

    res = client.get("/api/admin/messages?active=true")
    assert res.status_code == 200
    ids = [item["id"] for item in res.json()]
    assert msg_id in ids


# ---------------------------------------------------------------------------
# 6. placement filtering
# ---------------------------------------------------------------------------


def test_placement_filter_returns_only_matching_placement(client, test_db):
    _seed_message(test_db, org_id=None, placement="banner")
    _seed_message(test_db, org_id=None, placement="frontpage")

    member = _make_member(org_id=str(uuid.uuid4()))
    _override_user(member)

    res = client.get("/api/admin/messages?active=false&placement=banner")
    assert res.status_code == 200
    data = res.json()
    assert all(item["placement"] == "banner" for item in data)
    assert len(data) >= 1


def test_placement_filter_no_match_returns_empty(client, test_db):
    _seed_message(test_db, org_id=None, placement="banner")

    member = _make_member(org_id=str(uuid.uuid4()))
    _override_user(member)

    res = client.get("/api/admin/messages?active=false&placement=nonexistent")
    assert res.status_code == 200
    assert res.json() == []


def test_no_placement_filter_returns_all_placements(client, test_db):
    _seed_message(test_db, org_id=None, placement="banner")
    _seed_message(test_db, org_id=None, placement="frontpage")

    member = _make_member(org_id=str(uuid.uuid4()))
    _override_user(member)

    res = client.get("/api/admin/messages?active=false")
    assert res.status_code == 200
    placements = {item["placement"] for item in res.json()}
    assert "banner" in placements
    assert "frontpage" in placements
