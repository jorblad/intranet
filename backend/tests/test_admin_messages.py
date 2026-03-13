"""
Tests for /api/admin/messages endpoints.

Covers:
 1. Member can list global and org-scoped messages.
 2. Member cannot create, update, or delete messages.
 3. org_admin can manage messages for their own org but NOT global messages.
 4. Global org_admin and superadmin can manage global messages.
 5. Active-window (start/end) filtering and placement filtering.

Each test class creates its own isolated in-memory SQLite database so that role
configurations that conflict on the ``roles.name`` unique constraint (e.g.
having two ``org_admin`` rows with different ``is_global`` values) can be set
up independently without interference between test classes.
"""
import uuid
from datetime import datetime, timezone, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.db.base import Base
from app.db.session import get_db
from app.api.routes.auth import get_current_user
from app.models import User, Organization, Role, UserOrganizationRole, AdminMessage


# ---------------------------------------------------------------------------
# Helpers to build isolated in-memory databases and FastAPI test clients
# ---------------------------------------------------------------------------

def _make_engine():
    """Create a fresh in-memory SQLite engine with all tables."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return engine


def _make_session_factory(engine):
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


def _load_user(Session, user_id: str):
    """Load a User with its organization_roles eagerly from *Session*."""
    db = Session()
    try:
        u = db.query(User).filter(User.id == user_id).first()
        for a in u.organization_roles:
            _ = a.role  # touch to load relationship
        return u
    finally:
        db.close()


def _make_client(Session, user):
    """Return a TestClient that overrides get_db and get_current_user."""
    def _override_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app, raise_server_exceptions=True)


def _add_message(Session, organization_id=None, placement="banner",
                 start=None, end=None, title="Test"):
    """Insert an AdminMessage directly into the test DB and return its id."""
    db = Session()
    try:
        msg = AdminMessage(
            id=str(uuid.uuid4()),
            title=title,
            body="body",
            organization_id=organization_id,
            placement=placement,
            start=start,
            end=end,
            priority=0,
        )
        db.add(msg)
        db.commit()
        return msg.id
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 1 & 2. Member – listing (allowed) and write operations (forbidden)
# ---------------------------------------------------------------------------

class TestMemberAccess:
    """Tests using a plain member user (assigned to one org only)."""

    @classmethod
    def setup_class(cls):
        engine = _make_engine()
        Session = _make_session_factory(engine)
        cls.Session = Session

        db = Session()
        try:
            member_role = Role(id=str(uuid.uuid4()), name="member", is_global=False)
            # org_admin role needed so we can create seed messages via a separate user
            org_admin_role = Role(id=str(uuid.uuid4()), name="org_admin", is_global=False)
            db.add_all([member_role, org_admin_role])

            org = Organization(id=str(uuid.uuid4()), name="TestOrg")
            other_org = Organization(id=str(uuid.uuid4()), name="OtherOrg")
            db.add_all([org, other_org])
            db.commit()

            member = User(id=str(uuid.uuid4()), username="member",
                          display_name="Member", hashed_password="x")
            db.add(member)
            db.commit()

            db.add(UserOrganizationRole(
                id=str(uuid.uuid4()),
                user_id=member.id,
                organization_id=org.id,
                role_id=member_role.id,
            ))
            db.commit()

            cls.org_id = org.id
            cls.other_org_id = other_org.id
            cls.member_id = member.id
        finally:
            db.close()

    def setup_method(self):
        user = _load_user(self.Session, self.member_id)
        self.client = _make_client(self.Session, user)

    # -- listing --

    def test_member_can_list_global_messages(self):
        msg_id = _add_message(self.Session, organization_id=None)
        resp = self.client.get("/api/admin/messages")
        assert resp.status_code == 200
        assert any(m["id"] == msg_id for m in resp.json())

    def test_member_can_list_org_messages_for_assigned_org(self):
        msg_id = _add_message(self.Session, organization_id=self.org_id)
        resp = self.client.get(f"/api/admin/messages?organization_id={self.org_id}")
        assert resp.status_code == 200
        assert any(m["id"] == msg_id for m in resp.json())

    def test_member_cannot_list_other_org_messages(self):
        resp = self.client.get(f"/api/admin/messages?organization_id={self.other_org_id}")
        assert resp.status_code == 403

    # -- write operations --

    def test_member_cannot_create_org_message(self):
        resp = self.client.post("/api/admin/messages",
                                json={"title": "Hello", "organization_id": self.org_id})
        assert resp.status_code == 403

    def test_member_cannot_create_global_message(self):
        resp = self.client.post("/api/admin/messages", json={"title": "Global"})
        assert resp.status_code == 403

    def test_member_cannot_update_message(self):
        msg_id = _add_message(self.Session, organization_id=self.org_id)
        resp = self.client.patch(f"/api/admin/messages/{msg_id}", json={"title": "Changed"})
        assert resp.status_code == 403

    def test_member_cannot_delete_message(self):
        msg_id = _add_message(self.Session, organization_id=self.org_id)
        resp = self.client.delete(f"/api/admin/messages/{msg_id}")
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# 3. org_admin (scoped, non-global) – can manage own org, cannot touch global
# ---------------------------------------------------------------------------

class TestOrgAdminAccess:
    """Tests using an org_admin user with a *non-global* org_admin role."""

    @classmethod
    def setup_class(cls):
        engine = _make_engine()
        Session = _make_session_factory(engine)
        cls.Session = Session

        db = Session()
        try:
            # is_global=False → this admin is scoped to one org only
            org_admin_role = Role(id=str(uuid.uuid4()), name="org_admin", is_global=False)
            db.add(org_admin_role)

            org = Organization(id=str(uuid.uuid4()), name="OrgA")
            db.add(org)
            db.commit()

            admin = User(id=str(uuid.uuid4()), username="org_admin",
                         display_name="OrgAdmin", hashed_password="x")
            db.add(admin)
            db.commit()

            db.add(UserOrganizationRole(
                id=str(uuid.uuid4()),
                user_id=admin.id,
                organization_id=org.id,
                role_id=org_admin_role.id,
            ))
            db.commit()

            cls.org_id = org.id
            cls.admin_id = admin.id
        finally:
            db.close()

    def setup_method(self):
        user = _load_user(self.Session, self.admin_id)
        self.client = _make_client(self.Session, user)

    def test_org_admin_can_create_org_message(self):
        resp = self.client.post("/api/admin/messages",
                                json={"title": "OrgMsg", "organization_id": self.org_id})
        assert resp.status_code == 201
        body = resp.json()
        assert body["organization_id"] == self.org_id
        assert body["title"] == "OrgMsg"
        # verify defaults are present in the response
        assert "placement" in body
        assert "priority" in body
        assert "id" in body

    def test_org_admin_can_update_org_message(self):
        msg_id = _add_message(self.Session, organization_id=self.org_id)
        resp = self.client.patch(f"/api/admin/messages/{msg_id}", json={"title": "Updated"})
        assert resp.status_code == 200
        assert resp.json()["title"] == "Updated"

    def test_org_admin_can_delete_org_message(self):
        msg_id = _add_message(self.Session, organization_id=self.org_id)
        resp = self.client.delete(f"/api/admin/messages/{msg_id}")
        assert resp.status_code == 204

    def test_org_admin_cannot_create_global_message(self):
        resp = self.client.post("/api/admin/messages", json={"title": "GlobalFromOrgAdmin"})
        assert resp.status_code == 403

    def test_org_admin_cannot_update_global_message(self):
        msg_id = _add_message(self.Session, organization_id=None)
        resp = self.client.patch(f"/api/admin/messages/{msg_id}", json={"title": "Nope"})
        assert resp.status_code == 403

    def test_org_admin_cannot_delete_global_message(self):
        msg_id = _add_message(self.Session, organization_id=None)
        resp = self.client.delete(f"/api/admin/messages/{msg_id}")
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# 4. Global org_admin and superadmin – can manage global messages
# ---------------------------------------------------------------------------

class TestGlobalAdminAccess:
    """Tests using a global org_admin and a superadmin user."""

    @classmethod
    def setup_class(cls):
        engine = _make_engine()
        Session = _make_session_factory(engine)
        cls.Session = Session

        db = Session()
        try:
            # is_global=True → qualifies as global org admin
            global_org_admin_role = Role(id=str(uuid.uuid4()), name="org_admin", is_global=True)
            superadmin_role = Role(id=str(uuid.uuid4()), name="superadmin", is_global=True)
            db.add_all([global_org_admin_role, superadmin_role])

            org = Organization(id=str(uuid.uuid4()), name="OrgGlobal")
            db.add(org)
            db.commit()

            global_admin = User(id=str(uuid.uuid4()), username="global_admin",
                                display_name="GlobalAdmin", hashed_password="x")
            superadmin = User(id=str(uuid.uuid4()), username="superadmin",
                              display_name="SuperAdmin", hashed_password="x")
            db.add_all([global_admin, superadmin])
            db.commit()

            db.add(UserOrganizationRole(
                id=str(uuid.uuid4()),
                user_id=global_admin.id,
                organization_id=None,
                role_id=global_org_admin_role.id,
            ))
            db.add(UserOrganizationRole(
                id=str(uuid.uuid4()),
                user_id=superadmin.id,
                organization_id=None,
                role_id=superadmin_role.id,
            ))
            db.commit()

            cls.org_id = org.id
            cls.global_admin_id = global_admin.id
            cls.superadmin_id = superadmin.id
        finally:
            db.close()

    def _client_as(self, user_id: str):
        user = _load_user(self.Session, user_id)
        return _make_client(self.Session, user)

    def test_global_org_admin_can_create_global_message(self):
        client = self._client_as(self.global_admin_id)
        resp = client.post("/api/admin/messages", json={"title": "GlobalByGlobalAdmin"})
        assert resp.status_code == 201
        assert resp.json()["organization_id"] is None

    def test_global_org_admin_can_update_global_message(self):
        client = self._client_as(self.global_admin_id)
        msg_id = _add_message(self.Session, organization_id=None)
        resp = client.patch(f"/api/admin/messages/{msg_id}", json={"title": "GlobalUpdated"})
        assert resp.status_code == 200

    def test_global_org_admin_can_delete_global_message(self):
        client = self._client_as(self.global_admin_id)
        msg_id = _add_message(self.Session, organization_id=None)
        resp = client.delete(f"/api/admin/messages/{msg_id}")
        assert resp.status_code == 204

    def test_superadmin_can_create_global_message(self):
        client = self._client_as(self.superadmin_id)
        resp = client.post("/api/admin/messages", json={"title": "GlobalBySuperadmin"})
        assert resp.status_code == 201

    def test_superadmin_can_update_global_message(self):
        client = self._client_as(self.superadmin_id)
        msg_id = _add_message(self.Session, organization_id=None)
        resp = client.patch(f"/api/admin/messages/{msg_id}", json={"title": "SAUpdated"})
        assert resp.status_code == 200

    def test_superadmin_can_delete_global_message(self):
        client = self._client_as(self.superadmin_id)
        msg_id = _add_message(self.Session, organization_id=None)
        resp = client.delete(f"/api/admin/messages/{msg_id}")
        assert resp.status_code == 204

    def test_superadmin_can_create_org_message(self):
        client = self._client_as(self.superadmin_id)
        resp = client.post("/api/admin/messages",
                           json={"title": "OrgBySA", "organization_id": self.org_id})
        assert resp.status_code == 201


# ---------------------------------------------------------------------------
# 5. Active-window (start/end) and placement filtering
# ---------------------------------------------------------------------------

class TestFiltering:
    """Tests for start/end active-window and placement query filters."""

    @classmethod
    def setup_class(cls):
        engine = _make_engine()
        Session = _make_session_factory(engine)
        cls.Session = Session

        db = Session()
        try:
            member_role = Role(id=str(uuid.uuid4()), name="member", is_global=False)
            db.add(member_role)
            db.commit()

            member = User(id=str(uuid.uuid4()), username="filter_member",
                          display_name="FilterMember", hashed_password="x")
            db.add(member)
            db.commit()

            cls.member_id = member.id
        finally:
            db.close()

    def setup_method(self):
        user = _load_user(self.Session, self.member_id)
        self.client = _make_client(self.Session, user)

    def test_active_message_is_returned(self):
        now = datetime.now(timezone.utc)
        msg_id = _add_message(self.Session,
                              start=now - timedelta(hours=1),
                              end=now + timedelta(hours=1))
        resp = self.client.get("/api/admin/messages?active=true")
        assert resp.status_code == 200
        assert any(m["id"] == msg_id for m in resp.json())

    def test_not_yet_started_message_excluded_when_active(self):
        now = datetime.now(timezone.utc)
        msg_id = _add_message(self.Session, start=now + timedelta(hours=1))
        resp = self.client.get("/api/admin/messages?active=true")
        assert resp.status_code == 200
        assert all(m["id"] != msg_id for m in resp.json())

    def test_expired_message_excluded_when_active(self):
        now = datetime.now(timezone.utc)
        msg_id = _add_message(self.Session, end=now - timedelta(hours=1))
        resp = self.client.get("/api/admin/messages?active=true")
        assert resp.status_code == 200
        assert all(m["id"] != msg_id for m in resp.json())

    def test_inactive_false_returns_expired_messages(self):
        now = datetime.now(timezone.utc)
        msg_id = _add_message(self.Session, end=now - timedelta(hours=1), title="OldMsg")
        resp = self.client.get("/api/admin/messages?active=false")
        assert resp.status_code == 200
        assert any(m["id"] == msg_id for m in resp.json())

    def test_placement_filter_banner(self):
        banner_id = _add_message(self.Session, placement="banner", title="BannerMsg")
        front_id = _add_message(self.Session, placement="frontpage", title="FrontMsg")
        resp = self.client.get("/api/admin/messages?active=false&placement=banner")
        assert resp.status_code == 200
        ids = [m["id"] for m in resp.json()]
        assert banner_id in ids
        assert front_id not in ids

    def test_placement_filter_frontpage(self):
        front_id = _add_message(self.Session, placement="frontpage", title="FP2")
        resp = self.client.get("/api/admin/messages?active=false&placement=frontpage")
        assert resp.status_code == 200
        ids = [m["id"] for m in resp.json()]
        assert front_id in ids
