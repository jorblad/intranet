"""
Tests for the /api/admin/messages endpoints covering:
  1. Members can list org/global messages.
  2. Members cannot create, update, or delete messages.
  3. Org admins can manage messages scoped to their org only.
  4. Global org admins and superadmins can manage global (org-less) messages.
  5. Active-window (start/end) filtering and placement filtering.
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
from app.db.base import Base
from app.db.session import get_db
from app.api.routes.auth import get_current_user


# ---------------------------------------------------------------------------
# Shared in-memory database fixture
# ---------------------------------------------------------------------------

@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Helpers to build lightweight mock user objects
# ---------------------------------------------------------------------------

def _make_role(name: str, is_global: bool = False):
    return SimpleNamespace(name=name, is_global=is_global)


def _make_assignment(role_name: str, org_id: str | None = None, is_global: bool = False):
    return SimpleNamespace(
        role=_make_role(role_name, is_global=is_global),
        organization_id=org_id,
    )


def _make_user(user_id: str | None = None, assignments: list | None = None):
    return SimpleNamespace(
        id=user_id or str(uuid.uuid4()),
        is_active=True,
        organization_roles=assignments or [],
    )


def _member_user(org_id: str):
    """Regular member assigned to org_id (no admin role)."""
    return _make_user(assignments=[_make_assignment("member", org_id=org_id)])


def _org_admin_user(org_id: str):
    """Admin for a specific (non-global) org."""
    return _make_user(assignments=[_make_assignment("org_admin", org_id=org_id)])


def _global_org_admin_user():
    """org_admin with a global role (manages global messages)."""
    return _make_user(assignments=[_make_assignment("org_admin", is_global=True)])


def _superadmin_user():
    """Superadmin (global role named 'superadmin')."""
    return _make_user(assignments=[_make_assignment("superadmin", is_global=True)])


# ---------------------------------------------------------------------------
# TestClient factory: wires a fixed user and shared DB into the app
# ---------------------------------------------------------------------------


class OverrideClearingTestClient(TestClient):
    """
    TestClient that clears FastAPI dependency overrides when it is cleaned up.

    This helps prevent leakage of app.dependency_overrides between tests.
    """

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            return super().__exit__(exc_type, exc_val, exc_tb)
        finally:
            # Ensure overrides do not leak into subsequent tests
            app.dependency_overrides = {}

    def __del__(self):
        # Best-effort cleanup in case the client is not used as a context manager
        try:
            app.dependency_overrides = {}
        except Exception:
            # Avoid raising during interpreter shutdown
            pass


def _client(db, user):
    def override_db():
        yield db

    def override_user():
        return user

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_user
    client = OverrideClearingTestClient(app)
    return client


# ---------------------------------------------------------------------------
# Test data helpers
# ---------------------------------------------------------------------------

def _seed_message(db, title="Test", org_id=None, placement="banner",
                  start=None, end=None, priority=0):
    from app.crud.admin_message import create_admin_message
    return create_admin_message(
        db,
        title=title,
        body=None,
        organization_id=org_id,
        start=start,
        end=end,
        priority=priority,
        placement=placement,
    )


# ===========================================================================
# 1. Members can read org & global messages
# ===========================================================================

def test_member_can_list_global_messages(db_session):
    _seed_message(db_session, title="Global", org_id=None)
    user = _member_user("org-1")
    client = _client(db_session, user)
    resp = client.get("/api/admin/messages")
    assert resp.status_code == 200
    data = resp.json()
    assert any(m["title"] == "Global" for m in data)


def test_member_can_list_org_messages(db_session):
    org_id = "org-abc"
    _seed_message(db_session, title="OrgMsg", org_id=org_id)
    user = _member_user(org_id)
    client = _client(db_session, user)
    resp = client.get(f"/api/admin/messages?organization_id={org_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert any(m["title"] == "OrgMsg" for m in data)


def test_member_cannot_list_other_org_messages(db_session):
    """A member of org-1 must not see messages scoped to org-2."""
    org_id = "org-2"
    _seed_message(db_session, title="Other", org_id=org_id)
    user = _member_user("org-1")
    client = _client(db_session, user)
    resp = client.get(f"/api/admin/messages?organization_id={org_id}")
    assert resp.status_code == 403


# ===========================================================================
# 2. Members cannot create, update, or delete
# ===========================================================================

def test_member_cannot_create_message(db_session):
    org_id = "org-1"
    user = _member_user(org_id)
    client = _client(db_session, user)
    resp = client.post(
        "/api/admin/messages",
        json={"title": "New", "organization_id": org_id},
    )
    assert resp.status_code == 403


def test_member_cannot_update_message(db_session):
    org_id = "org-1"
    msg = _seed_message(db_session, title="Existing", org_id=org_id)
    user = _member_user(org_id)
    client = _client(db_session, user)
    resp = client.patch(f"/api/admin/messages/{msg.id}", json={"title": "Changed"})
    assert resp.status_code == 403


def test_member_cannot_delete_message(db_session):
    org_id = "org-1"
    msg = _seed_message(db_session, title="ToDelete", org_id=org_id)
    user = _member_user(org_id)
    client = _client(db_session, user)
    resp = client.delete(f"/api/admin/messages/{msg.id}")
    assert resp.status_code == 403


# ===========================================================================
# 3. Org admin can manage their own org, not other orgs or global scope
# ===========================================================================

def test_org_admin_can_create_org_message(db_session):
    org_id = "org-owned"
    from app.models import Organization
    db_session.add(Organization(id=org_id, name="Owned Org"))
    db_session.commit()
    user = _org_admin_user(org_id)
    client = _client(db_session, user)
    resp = client.post(
        "/api/admin/messages",
        json={"title": "OrgBanner", "organization_id": org_id},
    )
    assert resp.status_code == 201
    assert resp.json()["organization_id"] == org_id


def test_org_admin_cannot_create_message_for_other_org(db_session):
    org_id = "org-owned"
    other_org = "org-other"
    from app.models import Organization
    db_session.add(Organization(id=org_id, name="Owned"))
    db_session.add(Organization(id=other_org, name="Other"))
    db_session.commit()
    user = _org_admin_user(org_id)
    client = _client(db_session, user)
    resp = client.post(
        "/api/admin/messages",
        json={"title": "Unauthorized", "organization_id": other_org},
    )
    assert resp.status_code == 403


def test_org_admin_cannot_create_global_message(db_session):
    org_id = "org-owned"
    user = _org_admin_user(org_id)
    client = _client(db_session, user)
    resp = client.post(
        "/api/admin/messages",
        json={"title": "GlobalAttempt"},
    )
    assert resp.status_code == 403


def test_org_admin_can_update_own_org_message(db_session):
    org_id = "org-upd"
    msg = _seed_message(db_session, title="Old", org_id=org_id)
    user = _org_admin_user(org_id)
    client = _client(db_session, user)
    resp = client.patch(f"/api/admin/messages/{msg.id}", json={"title": "New"})
    assert resp.status_code == 200
    assert resp.json()["title"] == "New"


def test_org_admin_cannot_update_global_message(db_session):
    msg = _seed_message(db_session, title="GlobalMsg", org_id=None)
    user = _org_admin_user("org-x")
    client = _client(db_session, user)
    resp = client.patch(f"/api/admin/messages/{msg.id}", json={"title": "Hacked"})
    assert resp.status_code == 403


def test_org_admin_can_delete_own_org_message(db_session):
    org_id = "org-del"
    msg = _seed_message(db_session, title="Deletable", org_id=org_id)
    user = _org_admin_user(org_id)
    client = _client(db_session, user)
    resp = client.delete(f"/api/admin/messages/{msg.id}")
    assert resp.status_code == 204


def test_org_admin_cannot_delete_other_org_message(db_session):
    msg = _seed_message(db_session, title="OtherOrg", org_id="org-other")
    user = _org_admin_user("org-mine")
    client = _client(db_session, user)
    resp = client.delete(f"/api/admin/messages/{msg.id}")
    assert resp.status_code == 403


# ===========================================================================
# 4. Global org admin and superadmin can manage global messages
# ===========================================================================

def test_global_org_admin_can_create_global_message(db_session):
    user = _global_org_admin_user()
    client = _client(db_session, user)
    resp = client.post(
        "/api/admin/messages",
        json={"title": "GlobalNew"},
    )
    assert resp.status_code == 201
    assert resp.json()["organization_id"] is None


def test_superadmin_can_create_global_message(db_session):
    user = _superadmin_user()
    client = _client(db_session, user)
    resp = client.post(
        "/api/admin/messages",
        json={"title": "SuperGlobal"},
    )
    assert resp.status_code == 201
    assert resp.json()["organization_id"] is None


def test_global_org_admin_can_update_global_message(db_session):
    msg = _seed_message(db_session, title="Original", org_id=None)
    user = _global_org_admin_user()
    client = _client(db_session, user)
    resp = client.patch(f"/api/admin/messages/{msg.id}", json={"title": "Updated"})
    assert resp.status_code == 200
    assert resp.json()["title"] == "Updated"


def test_superadmin_can_delete_global_message(db_session):
    msg = _seed_message(db_session, title="GlobalDel", org_id=None)
    user = _superadmin_user()
    client = _client(db_session, user)
    resp = client.delete(f"/api/admin/messages/{msg.id}")
    assert resp.status_code == 204


# ===========================================================================
# 5. Start/end filtering and placement filtering
# ===========================================================================

def test_active_filtering_excludes_not_yet_started(db_session):
    future = datetime.now(timezone.utc) + timedelta(hours=2)
    _seed_message(db_session, title="Future", org_id=None, start=future)
    user = _global_org_admin_user()
    client = _client(db_session, user)
    resp = client.get("/api/admin/messages?active=true")
    assert resp.status_code == 200
    assert all(m["title"] != "Future" for m in resp.json())


def test_active_filtering_excludes_expired(db_session):
    past = datetime.now(timezone.utc) - timedelta(hours=2)
    _seed_message(db_session, title="Expired", org_id=None, end=past)
    user = _global_org_admin_user()
    client = _client(db_session, user)
    resp = client.get("/api/admin/messages?active=true")
    assert resp.status_code == 200
    assert all(m["title"] != "Expired" for m in resp.json())


def test_active_false_returns_all_messages(db_session):
    future = datetime.now(timezone.utc) + timedelta(hours=2)
    past = datetime.now(timezone.utc) - timedelta(hours=2)
    _seed_message(db_session, title="Future", org_id=None, start=future)
    _seed_message(db_session, title="Expired", org_id=None, end=past)
    _seed_message(db_session, title="Current", org_id=None)
    user = _global_org_admin_user()
    client = _client(db_session, user)
    resp = client.get("/api/admin/messages?active=false")
    assert resp.status_code == 200
    titles = {m["title"] for m in resp.json()}
    assert {"Future", "Expired", "Current"}.issubset(titles)


def test_placement_filter_returns_only_matching(db_session):
    _seed_message(db_session, title="Banner", org_id=None, placement="banner")
    _seed_message(db_session, title="Frontpage", org_id=None, placement="frontpage")
    user = _global_org_admin_user()
    client = _client(db_session, user)
    resp = client.get("/api/admin/messages?placement=frontpage")
    assert resp.status_code == 200
    data = resp.json()
    assert all(m["placement"] == "frontpage" for m in data)
    assert any(m["title"] == "Frontpage" for m in data)
    assert all(m["title"] != "Banner" for m in data)


def test_placement_filter_banner(db_session):
    _seed_message(db_session, title="BannerMsg", org_id=None, placement="banner")
    _seed_message(db_session, title="SidebarMsg", org_id=None, placement="sidebar")
    user = _global_org_admin_user()
    client = _client(db_session, user)
    resp = client.get("/api/admin/messages?placement=banner")
    assert resp.status_code == 200
    data = resp.json()
    assert all(m["placement"] == "banner" for m in data)
