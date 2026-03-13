"""Tests for admin-message endpoint permission logic and filtering.

Covers:
  (1) member can list org and global messages
  (2) member cannot create/update/delete
  (3) org_admin can manage org-scoped messages only
  (4) global org_admin / superadmin can manage global messages
  (5) start/end active-window filtering and placement filtering
"""
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
"""
Tests for admin_messages routes covering:
  1. Non-admin user denied (create, update, delete)
  2. org_admin allowed only for their own org
  3. Only global org_admin/superadmin can create/update/delete global messages
  4. Placement and org filtering in the list endpoint

Each test class uses its own fresh SQLite in-memory database to isolate state.
Because Role.name has a UNIQUE constraint, test classes that need both a
non-global "org_admin" role and a global "org_admin" role use separate DB
instances so there is only one role with a given name per database.
"""
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.db.base import Base
from app.db.session import get_db
from app.api.routes.auth import get_current_user
from app.models import Organization
from app.crud.admin_message import create_admin_message


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def test_db():
from app.models import User, Organization, Role, UserOrganizationRole
from app.crud.admin_message import create_admin_message


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_session_factory():
    """Create a fresh SQLite in-memory DB and return its session factory."""
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
    # expire_on_commit=False so that model instances stay usable outside the
    # session that created them (required for passing users to dependency overrides).
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)
    return TestingSessionLocal


def _build_client(db_session_factory, current_user):
    """Return a TestClient with DB and auth dependency overrides applied."""
    def override_get_db():
        db = db_session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _get_db
    yield TestingSessionLocal
    app.dependency_overrides.pop(get_db, None)
    # ensure user override is cleaned up even if a test forgot
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def client(test_db):
    return TestClient(app)


# ── user factory helpers ──────────────────────────────────────────────────────

def _make_member_user(org_id):
    """Plain member assigned to one org, no admin privileges."""
    return SimpleNamespace(
        id=str(uuid.uuid4()),
        organization_roles=[
            SimpleNamespace(
                organization_id=org_id,
                role=SimpleNamespace(name="member", is_global=False),
            )
        ],
    )


def _make_org_admin_user(org_id):
    """Org-admin scoped to the given organisation."""
    return SimpleNamespace(
        id=str(uuid.uuid4()),
        organization_roles=[
            SimpleNamespace(
                organization_id=org_id,
                role=SimpleNamespace(name="org_admin", is_global=False),
            )
        ],
    )


def _make_global_org_admin_user():
    """Global org_admin – can manage global messages."""
    return SimpleNamespace(
        id=str(uuid.uuid4()),
        organization_roles=[
            SimpleNamespace(
                organization_id=None,
                role=SimpleNamespace(name="org_admin", is_global=True),
            )
        ],
    )


def _make_superadmin_user():
    return SimpleNamespace(
        id=str(uuid.uuid4()),
        organization_roles=[
            SimpleNamespace(
                organization_id=None,
                role=SimpleNamespace(name="superadmin", is_global=True),
            )
        ],
    )


# ── data seeding helpers ──────────────────────────────────────────────────────

def _seed_org(Session):
    db = Session()
    try:
        org = Organization(id=str(uuid.uuid4()), name=f"Test Org {uuid.uuid4().hex[:8]}")
        db.add(org)
        db.commit()
        return org.id
    def override_get_current_user():
        return current_user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    return TestClient(app, raise_server_exceptions=True)


def _cleanup_overrides():
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_current_user, None)


def _seed_orgs_and_users(Session, org_admin_role_is_global=False):
    """
    Create two orgs and three users:
      - plain_user: no role
      - org_admin_user: org_admin for org1 only
      - superadmin_user: superadmin

    ``org_admin_role_is_global`` controls the ``is_global`` flag on the
    single "org_admin" role, which allows callers to test either the
    org-scoped behaviour (False) or the global-admin behaviour (True).
    """
    db = Session()
    try:
        org1 = Organization(id=str(uuid.uuid4()), name="Org1")
        org2 = Organization(id=str(uuid.uuid4()), name="Org2")
        db.add_all([org1, org2])
        db.flush()

        plain_user = User(id=str(uuid.uuid4()), username="plain", display_name="Plain", hashed_password="x")
        org_admin_user = User(id=str(uuid.uuid4()), username="org_admin", display_name="OrgAdmin", hashed_password="x")
        superadmin_user = User(id=str(uuid.uuid4()), username="superadmin", display_name="Superadmin", hashed_password="x")
        db.add_all([plain_user, org_admin_user, superadmin_user])
        db.flush()

        org_admin_role = Role(id=str(uuid.uuid4()), name="org_admin", is_global=org_admin_role_is_global)
        superadmin_role = Role(id=str(uuid.uuid4()), name="superadmin", is_global=True)
        db.add_all([org_admin_role, superadmin_role])
        db.flush()

        # org_admin_user is an admin for org1 only
        db.add(UserOrganizationRole(
            id=str(uuid.uuid4()),
            user_id=org_admin_user.id,
            organization_id=org1.id,
            role_id=org_admin_role.id,
        ))
        # superadmin_user has the global superadmin role
        db.add(UserOrganizationRole(
            id=str(uuid.uuid4()),
            user_id=superadmin_user.id,
            organization_id=None,
            role_id=superadmin_role.id,
        ))
        db.commit()
        for obj in (plain_user, org_admin_user, superadmin_user, org1, org2):
            db.refresh(obj)
        # Eagerly load lazy relationships so the objects remain usable after
        # the session is closed.
        for user in (plain_user, org_admin_user, superadmin_user):
            for uor in user.organization_roles:
                _ = uor.role
        return {
            "org1_id": org1.id,
            "org2_id": org2.id,
            "plain_user": plain_user,
            "org_admin_user": org_admin_user,
            "superadmin_user": superadmin_user,
        }
    finally:
        db.close()


def _seed_message(Session, *, org_id=None, placement="banner", start=None, end=None, title="Test"):
    db = Session()
    try:
        msg = create_admin_message(
            db,
            title=title,
            body="Body",
            organization_id=org_id,
            placement=placement,
            start=start,
            end=end,
        )
        return msg.id
def _seed_global_admin(Session, ids):
    """
    Add a second user (global_admin_user) who holds an "org_admin" role with
    is_global=True and no org assignment.  Call this only on a DB that was
    seeded with ``org_admin_role_is_global=True`` (so there is already a
    global "org_admin" role to reuse).
    """
    db = Session()
    try:
        global_admin_user = User(
            id=str(uuid.uuid4()), username="global_admin",
            display_name="GlobalAdmin", hashed_password="x",
        )
        db.add(global_admin_user)
        db.flush()

        # Reuse the existing global org_admin role
        from app.models import Role as RoleModel
        global_role = db.query(RoleModel).filter_by(name="org_admin", is_global=True).first()
        db.add(UserOrganizationRole(
            id=str(uuid.uuid4()),
            user_id=global_admin_user.id,
            organization_id=None,
            role_id=global_role.id,
        ))
        db.commit()
        db.refresh(global_admin_user)
        # Eagerly load relationships so the object stays usable outside the session.
        for uor in global_admin_user.organization_roles:
            _ = uor.role
        ids["global_admin_user"] = global_admin_user
        return ids
    finally:
        db.close()


def _as_user(user):
    """Override the current-user dependency for the duration of a test."""
    app.dependency_overrides[get_current_user] = lambda: user


def _clear_user():
    app.dependency_overrides.pop(get_current_user, None)


# ── (1) member can list org and global messages ───────────────────────────────

def test_member_can_list_own_org_messages(client, test_db):
    org_id = _seed_org(test_db)
    _seed_message(test_db, org_id=org_id)
    _as_user(_make_member_user(org_id))
    try:
        res = client.get(f"/api/admin/messages?organization_id={org_id}")
        assert res.status_code == 200
        assert len(res.json()) >= 1
    finally:
        _clear_user()


def test_member_can_list_global_messages(client, test_db):
    _seed_message(test_db, org_id=None)
    org_id = _seed_org(test_db)
    _as_user(_make_member_user(org_id))
    try:
        res = client.get("/api/admin/messages")
        assert res.status_code == 200
        assert len(res.json()) >= 1
    finally:
        _clear_user()


def test_member_cannot_list_other_org_messages(client, test_db):
    org1_id = _seed_org(test_db)
    org2_id = _seed_org(test_db)
    _as_user(_make_member_user(org1_id))
    try:
        res = client.get(f"/api/admin/messages?organization_id={org2_id}")
        assert res.status_code == 403
    finally:
        _clear_user()


# ── (2) member cannot create / update / delete ────────────────────────────────

def test_member_cannot_create(client, test_db):
    org_id = _seed_org(test_db)
    _as_user(_make_member_user(org_id))
    try:
        res = client.post("/api/admin/messages", json={"title": "Member Created Message", "organization_id": org_id})
        assert res.status_code == 403
    finally:
        _clear_user()


def test_member_cannot_update(client, test_db):
    org_id = _seed_org(test_db)
    msg_id = _seed_message(test_db, org_id=org_id)
    _as_user(_make_member_user(org_id))
    try:
        res = client.patch(f"/api/admin/messages/{msg_id}", json={"title": "Updated by Member"})
        assert res.status_code == 403
    finally:
        _clear_user()


def test_member_cannot_delete(client, test_db):
    org_id = _seed_org(test_db)
    msg_id = _seed_message(test_db, org_id=org_id)
    _as_user(_make_member_user(org_id))
    try:
        res = client.delete(f"/api/admin/messages/{msg_id}")
        assert res.status_code == 403
    finally:
        _clear_user()


# ── (3) org_admin manages own org only ───────────────────────────────────────

def test_org_admin_can_create_for_own_org(client, test_db):
    org_id = _seed_org(test_db)
    _as_user(_make_org_admin_user(org_id))
    try:
        res = client.post("/api/admin/messages", json={"title": "Msg", "organization_id": org_id})
        assert res.status_code == 201
    finally:
        _clear_user()


def test_org_admin_cannot_create_for_other_org(client, test_db):
    org1_id = _seed_org(test_db)
    org2_id = _seed_org(test_db)
    _as_user(_make_org_admin_user(org1_id))
    try:
        res = client.post("/api/admin/messages", json={"title": "Msg", "organization_id": org2_id})
        assert res.status_code == 403
    finally:
        _clear_user()


def test_org_admin_cannot_create_global_message(client, test_db):
    org_id = _seed_org(test_db)
    _as_user(_make_org_admin_user(org_id))
    try:
        res = client.post("/api/admin/messages", json={"title": "Global"})
        assert res.status_code == 403
    finally:
        _clear_user()


def test_org_admin_can_update_own_org_message(client, test_db):
    org_id = _seed_org(test_db)
    msg_id = _seed_message(test_db, org_id=org_id)
    _as_user(_make_org_admin_user(org_id))
    try:
        res = client.patch(f"/api/admin/messages/{msg_id}", json={"title": "Updated"})
        assert res.status_code == 200
        assert res.json()["title"] == "Updated"
    finally:
        _clear_user()


def test_org_admin_cannot_update_other_org_message(client, test_db):
    org1_id = _seed_org(test_db)
    org2_id = _seed_org(test_db)
    msg_id = _seed_message(test_db, org_id=org2_id)
    _as_user(_make_org_admin_user(org1_id))
    try:
        res = client.patch(f"/api/admin/messages/{msg_id}", json={"title": "Nope"})
        assert res.status_code == 403
    finally:
        _clear_user()


def test_org_admin_can_delete_own_org_message(client, test_db):
    org_id = _seed_org(test_db)
    msg_id = _seed_message(test_db, org_id=org_id)
    _as_user(_make_org_admin_user(org_id))
    try:
        res = client.delete(f"/api/admin/messages/{msg_id}")
        assert res.status_code == 204
    finally:
        _clear_user()


def test_org_admin_cannot_delete_other_org_message(client, test_db):
    org1_id = _seed_org(test_db)
    org2_id = _seed_org(test_db)
    msg_id = _seed_message(test_db, org_id=org2_id)
    _as_user(_make_org_admin_user(org1_id))
    try:
        res = client.delete(f"/api/admin/messages/{msg_id}")
        assert res.status_code == 403
    finally:
        _clear_user()


def test_org_admin_cannot_delete_global_message(client, test_db):
    org_id = _seed_org(test_db)
    msg_id = _seed_message(test_db, org_id=None)
    _as_user(_make_org_admin_user(org_id))
    try:
        res = client.delete(f"/api/admin/messages/{msg_id}")
        assert res.status_code == 403
    finally:
        _clear_user()


# ── (4) global org_admin / superadmin manages global messages ─────────────────

def test_global_org_admin_can_create_global_message(client, test_db):
    _as_user(_make_global_org_admin_user())
    try:
        res = client.post("/api/admin/messages", json={"title": "Global msg"})
        assert res.status_code == 201
        assert res.json()["organization_id"] is None
    finally:
        _clear_user()


def test_superadmin_can_create_global_message(client, test_db):
    _as_user(_make_superadmin_user())
    try:
        res = client.post("/api/admin/messages", json={"title": "Super global"})
        assert res.status_code == 201
        assert res.json()["organization_id"] is None
    finally:
        _clear_user()


def test_global_org_admin_can_update_global_message(client, test_db):
    msg_id = _seed_message(test_db, org_id=None)
    _as_user(_make_global_org_admin_user())
    try:
        res = client.patch(f"/api/admin/messages/{msg_id}", json={"title": "Updated global"})
        assert res.status_code == 200
        assert res.json()["title"] == "Updated global"
    finally:
        _clear_user()


def test_superadmin_can_delete_global_message(client, test_db):
    msg_id = _seed_message(test_db, org_id=None)
    _as_user(_make_superadmin_user())
    try:
        res = client.delete(f"/api/admin/messages/{msg_id}")
        assert res.status_code == 204
    finally:
        _clear_user()


def test_superadmin_can_create_org_scoped_message(client, test_db):
    org_id = _seed_org(test_db)
    _as_user(_make_superadmin_user())
    try:
        res = client.post("/api/admin/messages", json={"title": "SA org msg", "organization_id": org_id})
        assert res.status_code == 201
        assert res.json()["organization_id"] == org_id
    finally:
        _clear_user()


# ── (5) start/end active-window filtering and placement filtering ─────────────

def test_placement_filter_returns_only_matching_placement(client, test_db):
    _seed_message(test_db, org_id=None, placement="banner", title="Banner msg")
    _seed_message(test_db, org_id=None, placement="frontpage", title="Frontpage msg")
    _as_user(_make_superadmin_user())
    try:
        res = client.get("/api/admin/messages?placement=banner&active=false")
        assert res.status_code == 200
        data = res.json()
        assert len(data) == 1
        assert data[0]["placement"] == "banner"
    finally:
        _clear_user()


def test_placement_filter_frontpage(client, test_db):
    _seed_message(test_db, org_id=None, placement="banner", title="Banner msg")
    _seed_message(test_db, org_id=None, placement="frontpage", title="Frontpage msg")
    _as_user(_make_superadmin_user())
    try:
        res = client.get("/api/admin/messages?placement=frontpage&active=false")
        assert res.status_code == 200
        data = res.json()
        assert len(data) == 1
        assert data[0]["placement"] == "frontpage"
    finally:
        _clear_user()


def test_active_filter_excludes_not_yet_started_message(client, test_db):
    now = datetime.now(timezone.utc)
    future_start = now + timedelta(hours=2)
    future_end = now + timedelta(hours=4)
    _seed_message(test_db, org_id=None, start=future_start, end=future_end, title="Future")
    _as_user(_make_superadmin_user())
    try:
        res = client.get("/api/admin/messages?active=true")
        assert res.status_code == 200
        titles = [m["title"] for m in res.json()]
        assert "Future" not in titles
    finally:
        _clear_user()


def test_active_filter_excludes_expired_message(client, test_db):
    now = datetime.now(timezone.utc)
    old_start = now - timedelta(hours=4)
    old_end = now - timedelta(hours=2)
    _seed_message(test_db, org_id=None, start=old_start, end=old_end, title="Expired")
    _as_user(_make_superadmin_user())
    try:
        res = client.get("/api/admin/messages?active=true")
        assert res.status_code == 200
        titles = [m["title"] for m in res.json()]
        assert "Expired" not in titles
    finally:
        _clear_user()


def test_active_filter_includes_message_within_window(client, test_db):
    now = datetime.now(timezone.utc)
    past_start = now - timedelta(hours=2)
    future_end = now + timedelta(hours=2)
    _seed_message(test_db, org_id=None, start=past_start, end=future_end, title="Active")
    _as_user(_make_superadmin_user())
    try:
        res = client.get("/api/admin/messages?active=true")
        assert res.status_code == 200
        titles = [m["title"] for m in res.json()]
        assert "Active" in titles
    finally:
        _clear_user()


def test_active_filter_includes_message_with_no_window(client, test_db):
    _seed_message(test_db, org_id=None, start=None, end=None, title="Always active")
    _as_user(_make_superadmin_user())
    try:
        res = client.get("/api/admin/messages?active=true")
        assert res.status_code == 200
        titles = [m["title"] for m in res.json()]
        assert "Always active" in titles
    finally:
        _clear_user()


def test_inactive_filter_returns_all_messages_including_future(client, test_db):
    now = datetime.now(timezone.utc)
    past_start = now - timedelta(hours=2)
    future_start = now + timedelta(hours=2)
    future_end = now + timedelta(hours=4)
    _seed_message(test_db, org_id=None, start=past_start, end=future_end, title="Active")
    _seed_message(test_db, org_id=None, start=future_start, end=future_end, title="Future")
    _as_user(_make_superadmin_user())
    try:
        res = client.get("/api/admin/messages?active=false")
        assert res.status_code == 200
        titles = [m["title"] for m in res.json()]
        assert "Active" in titles
        assert "Future" in titles
    finally:
        _clear_user()
# ---------------------------------------------------------------------------
# 1. Non-admin denied
# ---------------------------------------------------------------------------

class TestNonAdminDenied:
    def setup_method(self):
        self.Session = _make_session_factory()
        self.ids = _seed_orgs_and_users(self.Session)

    def teardown_method(self):
        _cleanup_overrides()

    def test_plain_user_cannot_create_org_message(self):
        client = _build_client(self.Session, self.ids["plain_user"])
        resp = client.post("/api/admin/messages", json={
            "title": "Test",
            "organization_id": self.ids["org1_id"],
        })
        assert resp.status_code == 403

    def test_plain_user_cannot_create_global_message(self):
        client = _build_client(self.Session, self.ids["plain_user"])
        resp = client.post("/api/admin/messages", json={"title": "Global"})
        assert resp.status_code == 403

    def test_plain_user_cannot_update_org_message(self):
        db = self.Session()
        msg = create_admin_message(db, title="Msg", organization_id=self.ids["org1_id"])
        db.close()

        client = _build_client(self.Session, self.ids["plain_user"])
        resp = client.patch(f"/api/admin/messages/{msg.id}", json={"title": "Updated"})
        assert resp.status_code == 403

    def test_plain_user_cannot_delete_org_message(self):
        db = self.Session()
        msg = create_admin_message(db, title="Msg", organization_id=self.ids["org1_id"])
        db.close()

        client = _build_client(self.Session, self.ids["plain_user"])
        resp = client.delete(f"/api/admin/messages/{msg.id}")
        assert resp.status_code == 403

    def test_plain_user_cannot_delete_global_message(self):
        db = self.Session()
        msg = create_admin_message(db, title="Global Msg")
        db.close()

        client = _build_client(self.Session, self.ids["plain_user"])
        resp = client.delete(f"/api/admin/messages/{msg.id}")
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# 2. org_admin allowed only for their own org
#    Uses a NON-global "org_admin" role so _has_global_org_admin returns False.
# ---------------------------------------------------------------------------

class TestOrgAdminScopedToOrg:
    def setup_method(self):
        self.Session = _make_session_factory()
        self.ids = _seed_orgs_and_users(self.Session, org_admin_role_is_global=False)

    def teardown_method(self):
        _cleanup_overrides()

    def test_org_admin_can_create_message_for_own_org(self):
        client = _build_client(self.Session, self.ids["org_admin_user"])
        resp = client.post("/api/admin/messages", json={
            "title": "Hello Org1",
            "organization_id": self.ids["org1_id"],
        })
        assert resp.status_code == 201
        assert resp.json()["organization_id"] == self.ids["org1_id"]

    def test_org_admin_cannot_create_message_for_other_org(self):
        client = _build_client(self.Session, self.ids["org_admin_user"])
        resp = client.post("/api/admin/messages", json={
            "title": "Hello Org2",
            "organization_id": self.ids["org2_id"],
        })
        assert resp.status_code == 403

    def test_org_admin_cannot_create_global_message(self):
        client = _build_client(self.Session, self.ids["org_admin_user"])
        resp = client.post("/api/admin/messages", json={"title": "Global"})
        assert resp.status_code == 403

    def test_org_admin_can_update_message_for_own_org(self):
        db = self.Session()
        msg = create_admin_message(db, title="Org1 Msg", organization_id=self.ids["org1_id"])
        db.close()

        client = _build_client(self.Session, self.ids["org_admin_user"])
        resp = client.patch(f"/api/admin/messages/{msg.id}", json={"title": "Updated"})
        assert resp.status_code == 200
        assert resp.json()["title"] == "Updated"

    def test_org_admin_cannot_update_message_for_other_org(self):
        db = self.Session()
        msg = create_admin_message(db, title="Org2 Msg", organization_id=self.ids["org2_id"])
        db.close()

        client = _build_client(self.Session, self.ids["org_admin_user"])
        resp = client.patch(f"/api/admin/messages/{msg.id}", json={"title": "Updated"})
        assert resp.status_code == 403

    def test_org_admin_cannot_update_global_message(self):
        db = self.Session()
        msg = create_admin_message(db, title="Global Msg")
        db.close()

        client = _build_client(self.Session, self.ids["org_admin_user"])
        resp = client.patch(f"/api/admin/messages/{msg.id}", json={"title": "Hacked"})
        assert resp.status_code == 403

    def test_org_admin_can_delete_message_for_own_org(self):
        db = self.Session()
        msg = create_admin_message(db, title="Org1 Msg", organization_id=self.ids["org1_id"])
        db.close()

        client = _build_client(self.Session, self.ids["org_admin_user"])
        resp = client.delete(f"/api/admin/messages/{msg.id}")
        assert resp.status_code == 204

    def test_org_admin_cannot_delete_message_for_other_org(self):
        db = self.Session()
        msg = create_admin_message(db, title="Org2 Msg", organization_id=self.ids["org2_id"])
        db.close()

        client = _build_client(self.Session, self.ids["org_admin_user"])
        resp = client.delete(f"/api/admin/messages/{msg.id}")
        assert resp.status_code == 403

    def test_org_admin_cannot_delete_global_message(self):
        db = self.Session()
        msg = create_admin_message(db, title="Global Msg")
        db.close()

        client = _build_client(self.Session, self.ids["org_admin_user"])
        resp = client.delete(f"/api/admin/messages/{msg.id}")
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# 3. Only global org_admin/superadmin can modify global messages
#    Uses a GLOBAL "org_admin" role so _has_global_org_admin returns True.
# ---------------------------------------------------------------------------

class TestGlobalMessagePermissions:
    def setup_method(self):
        # DB with a global "org_admin" role so global_admin_user qualifies
        self.Session = _make_session_factory()
        self.ids = _seed_orgs_and_users(self.Session, org_admin_role_is_global=True)
        self.ids = _seed_global_admin(self.Session, self.ids)

    def teardown_method(self):
        _cleanup_overrides()

    def test_global_org_admin_can_create_global_message(self):
        client = _build_client(self.Session, self.ids["global_admin_user"])
        resp = client.post("/api/admin/messages", json={"title": "Global"})
        assert resp.status_code == 201
        assert resp.json()["organization_id"] is None

    def test_superadmin_can_create_global_message(self):
        client = _build_client(self.Session, self.ids["superadmin_user"])
        resp = client.post("/api/admin/messages", json={"title": "Global SA"})
        assert resp.status_code == 201
        assert resp.json()["organization_id"] is None

    def test_global_org_admin_can_update_global_message(self):
        db = self.Session()
        msg = create_admin_message(db, title="Global Msg")
        db.close()

        client = _build_client(self.Session, self.ids["global_admin_user"])
        resp = client.patch(f"/api/admin/messages/{msg.id}", json={"title": "Updated"})
        assert resp.status_code == 200

    def test_superadmin_can_update_global_message(self):
        db = self.Session()
        msg = create_admin_message(db, title="Global SA Msg")
        db.close()

        client = _build_client(self.Session, self.ids["superadmin_user"])
        resp = client.patch(f"/api/admin/messages/{msg.id}", json={"title": "Updated SA"})
        assert resp.status_code == 200

    def test_global_org_admin_can_delete_global_message(self):
        db = self.Session()
        msg = create_admin_message(db, title="Global Msg")
        db.close()

        client = _build_client(self.Session, self.ids["global_admin_user"])
        resp = client.delete(f"/api/admin/messages/{msg.id}")
        assert resp.status_code == 204

    def test_superadmin_can_delete_global_message(self):
        db = self.Session()
        msg = create_admin_message(db, title="Global SA Msg")
        db.close()

        client = _build_client(self.Session, self.ids["superadmin_user"])
        resp = client.delete(f"/api/admin/messages/{msg.id}")
        assert resp.status_code == 204


# ---------------------------------------------------------------------------
# 4. Placement/org filtering in list endpoints
# ---------------------------------------------------------------------------

class TestListFiltering:
    def setup_method(self):
        self.Session = _make_session_factory()
        self.ids = _seed_orgs_and_users(self.Session)
        # seed messages with varying placement and org
        db = self.Session()
        create_admin_message(db, title="Global Banner", placement="banner")
        create_admin_message(db, title="Global Front", placement="frontpage")
        create_admin_message(db, title="Org1 Banner", placement="banner", organization_id=self.ids["org1_id"])
        create_admin_message(db, title="Org2 Banner", placement="banner", organization_id=self.ids["org2_id"])
        db.close()

    def teardown_method(self):
        _cleanup_overrides()

    def _superadmin_client(self):
        return _build_client(self.Session, self.ids["superadmin_user"])

    def test_list_without_org_returns_only_global_messages(self):
        resp = self._superadmin_client().get("/api/admin/messages")
        assert resp.status_code == 200
        titles = {m["title"] for m in resp.json()}
        assert "Global Banner" in titles
        assert "Global Front" in titles
        # org-specific messages must not appear when no org filter is provided
        assert "Org1 Banner" not in titles
        assert "Org2 Banner" not in titles

    def test_list_with_org_includes_org_and_global_messages(self):
        resp = self._superadmin_client().get(f"/api/admin/messages?organization_id={self.ids['org1_id']}")
        assert resp.status_code == 200
        titles = {m["title"] for m in resp.json()}
        assert "Org1 Banner" in titles
        assert "Global Banner" in titles
        assert "Global Front" in titles
        assert "Org2 Banner" not in titles

    def test_list_placement_filter(self):
        resp = self._superadmin_client().get(
            f"/api/admin/messages?organization_id={self.ids['org1_id']}&placement=frontpage"
        )
        assert resp.status_code == 200
        titles = {m["title"] for m in resp.json()}
        assert "Global Front" in titles
        assert "Global Banner" not in titles
        assert "Org1 Banner" not in titles

    def test_list_org_filter_excludes_other_org(self):
        resp = self._superadmin_client().get(f"/api/admin/messages?organization_id={self.ids['org2_id']}")
        assert resp.status_code == 200
        titles = {m["title"] for m in resp.json()}
        assert "Org2 Banner" in titles
        assert "Org1 Banner" not in titles

    def test_non_member_forbidden_from_viewing_org_messages(self):
        # org_admin_user is only in org1; must not access org2 messages
        client = _build_client(self.Session, self.ids["org_admin_user"])
        resp = client.get(f"/api/admin/messages?organization_id={self.ids['org2_id']}")
        assert resp.status_code == 403
