"""
Tests for the admin_messages API routes.

Covers:
- Org member read access
- Org admin create/update/delete scoping
- Global message restrictions
- Active window filtering
"""
import uuid
import datetime

import pytest
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
# In-memory DB helpers
# ---------------------------------------------------------------------------

def _make_engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return engine


def _session_factory(engine):
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


# ---------------------------------------------------------------------------
# Fixture factories: build users/orgs/roles in the DB
# ---------------------------------------------------------------------------

def _create_org(db, name=None):
    org = Organization(id=str(uuid.uuid4()), name=name or f"Org-{uuid.uuid4().hex[:6]}")
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


def _create_user(db, username=None):
    user = User(
        id=str(uuid.uuid4()),
        username=username or f"user_{uuid.uuid4().hex[:6]}",
        display_name="Test User",
        hashed_password="x",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _create_role(db, name, is_global=False):
    role = Role(id=str(uuid.uuid4()), name=name, is_global=is_global)
    db.add(role)
    db.commit()
    db.refresh(role)
    return role


def _assign_role(db, user, role, org=None):
    assignment = UserOrganizationRole(
        id=str(uuid.uuid4()),
        user_id=user.id,
        role_id=role.id,
        organization_id=org.id if org else None,
    )
    db.add(assignment)
    db.commit()


def _create_message(db, title="Test", org_id=None, start=None, end=None, priority=0, placement="banner"):
    msg = AdminMessage(
        id=str(uuid.uuid4()),
        title=title,
        organization_id=org_id,
        start=start,
        end=end,
        priority=priority,
        placement=placement,
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return msg


# ---------------------------------------------------------------------------
# TestClient factory – allows injecting a specific "current user"
# ---------------------------------------------------------------------------

def _make_client(engine, current_user):
    Session = _session_factory(engine)

    def override_get_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    def override_get_current_user():
        # Re-fetch from DB so relationships are populated
        db = Session()
        try:
            from sqlalchemy.orm import joinedload
            u = (
                db.query(User)
                .options(
                    joinedload(User.organization_roles)
                    .joinedload(UserOrganizationRole.role)
                )
                .filter(User.id == current_user.id)
                .first()
            )
            return u
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    client = TestClient(app, raise_server_exceptions=True)
    return client


def _clear_overrides():
    app.dependency_overrides.clear()


# ===========================================================================
# Tests: org member read access
# ===========================================================================

class TestOrgMemberReadAccess:
    def setup_method(self):
        self.engine = _make_engine()
        Session = _session_factory(self.engine)
        self.db = Session()

        self.org = _create_org(self.db, "OrgA")
        self.other_org = _create_org(self.db, "OrgB")

        # Regular member of OrgA
        self.member_role = _create_role(self.db, "member")
        self.member = _create_user(self.db)
        _assign_role(self.db, self.member, self.member_role, self.org)

        # A user with no org membership
        self.outsider = _create_user(self.db)

        # Org message
        self.org_msg = _create_message(self.db, "OrgA message", org_id=self.org.id)
        # Global message
        self.global_msg = _create_message(self.db, "Global message", org_id=None)

    def teardown_method(self):
        self.db.close()
        _clear_overrides()

    def test_org_member_can_list_org_messages(self):
        client = _make_client(self.engine, self.member)
        resp = client.get(f"/api/admin/messages?organization_id={self.org.id}&active=false")
        assert resp.status_code == 200
        ids = [m["id"] for m in resp.json()]
        assert self.org_msg.id in ids

    def test_org_member_can_list_global_messages(self):
        client = _make_client(self.engine, self.member)
        resp = client.get("/api/admin/messages?active=false")
        assert resp.status_code == 200
        ids = [m["id"] for m in resp.json()]
        assert self.global_msg.id in ids

    def test_non_member_cannot_list_other_org_messages(self):
        client = _make_client(self.engine, self.outsider)
        resp = client.get(f"/api/admin/messages?organization_id={self.other_org.id}&active=false")
        assert resp.status_code == 403

    def test_org_member_cannot_list_other_org_messages(self):
        client = _make_client(self.engine, self.member)
        resp = client.get(f"/api/admin/messages?organization_id={self.other_org.id}&active=false")
        assert resp.status_code == 403

    def test_org_member_can_view_detail_of_org_message(self):
        client = _make_client(self.engine, self.member)
        resp = client.get(f"/api/admin/messages/{self.org_msg.id}")
        assert resp.status_code == 200
        assert resp.json()["id"] == self.org_msg.id

    def test_non_member_cannot_view_detail_of_org_message(self):
        client = _make_client(self.engine, self.outsider)
        resp = client.get(f"/api/admin/messages/{self.org_msg.id}")
        assert resp.status_code == 403


# ===========================================================================
# Tests: org_admin create/update/delete scoping
# ===========================================================================

class TestOrgAdminScoping:
    def setup_method(self):
        self.engine = _make_engine()
        Session = _session_factory(self.engine)
        self.db = Session()

        self.org1 = _create_org(self.db, "Org1")
        self.org2 = _create_org(self.db, "Org2")

        self.org_admin_role = _create_role(self.db, "org_admin")
        self.admin = _create_user(self.db)
        _assign_role(self.db, self.admin, self.org_admin_role, self.org1)

        # existing message in org1 for update/delete tests
        self.msg_org1 = _create_message(self.db, "Org1 msg", org_id=self.org1.id)
        # existing message in org2 – admin should not be able to modify
        self.msg_org2 = _create_message(self.db, "Org2 msg", org_id=self.org2.id)

    def teardown_method(self):
        self.db.close()
        _clear_overrides()

    def test_org_admin_can_create_message_for_own_org(self):
        client = _make_client(self.engine, self.admin)
        resp = client.post("/api/admin/messages", json={
            "title": "New msg",
            "organization_id": self.org1.id,
        })
        assert resp.status_code == 201
        assert resp.json()["organization_id"] == self.org1.id

    def test_org_admin_cannot_create_message_for_other_org(self):
        client = _make_client(self.engine, self.admin)
        resp = client.post("/api/admin/messages", json={
            "title": "Sneaky msg",
            "organization_id": self.org2.id,
        })
        assert resp.status_code == 403

    def test_org_admin_can_update_message_in_own_org(self):
        client = _make_client(self.engine, self.admin)
        resp = client.patch(f"/api/admin/messages/{self.msg_org1.id}", json={"title": "Updated"})
        assert resp.status_code == 200
        assert resp.json()["title"] == "Updated"

    def test_org_admin_cannot_update_message_in_other_org(self):
        client = _make_client(self.engine, self.admin)
        resp = client.patch(f"/api/admin/messages/{self.msg_org2.id}", json={"title": "Hacked"})
        assert resp.status_code == 403

    def test_org_admin_can_delete_message_in_own_org(self):
        client = _make_client(self.engine, self.admin)
        resp = client.delete(f"/api/admin/messages/{self.msg_org1.id}")
        assert resp.status_code == 204

    def test_org_admin_cannot_delete_message_in_other_org(self):
        client = _make_client(self.engine, self.admin)
        resp = client.delete(f"/api/admin/messages/{self.msg_org2.id}")
        assert resp.status_code == 403


# ===========================================================================
# Tests: global message restrictions
# ===========================================================================

class TestGlobalMessageRestrictions:
    def setup_method(self):
        self.engine = _make_engine()
        Session = _session_factory(self.engine)
        self.db = Session()

        self.org = _create_org(self.db, "SomeOrg")

        # Regular org_admin (non-global)
        self.org_admin_role = _create_role(self.db, "org_admin_local")
        # Global org_admin role
        self.global_admin_role = _create_role(self.db, "org_admin", is_global=True)
        # Superadmin role (global)
        self.superadmin_role = _create_role(self.db, "superadmin", is_global=True)

        self.regular_admin = _create_user(self.db)
        _assign_role(self.db, self.regular_admin, self.org_admin_role, self.org)

        self.global_admin = _create_user(self.db)
        _assign_role(self.db, self.global_admin, self.global_admin_role)

        self.superadmin = _create_user(self.db)
        _assign_role(self.db, self.superadmin, self.superadmin_role)

        self.global_msg = _create_message(self.db, "Global msg", org_id=None)

    def teardown_method(self):
        self.db.close()
        _clear_overrides()

    def test_regular_org_admin_cannot_create_global_message(self):
        client = _make_client(self.engine, self.regular_admin)
        resp = client.post("/api/admin/messages", json={"title": "Global attempt"})
        assert resp.status_code == 403

    def test_global_org_admin_can_create_global_message(self):
        client = _make_client(self.engine, self.global_admin)
        resp = client.post("/api/admin/messages", json={"title": "Global from admin"})
        assert resp.status_code == 201
        assert resp.json()["organization_id"] is None

    def test_superadmin_can_create_global_message(self):
        client = _make_client(self.engine, self.superadmin)
        resp = client.post("/api/admin/messages", json={"title": "Global from superadmin"})
        assert resp.status_code == 201

    def test_regular_org_admin_cannot_update_global_message(self):
        client = _make_client(self.engine, self.regular_admin)
        resp = client.patch(f"/api/admin/messages/{self.global_msg.id}", json={"title": "Nope"})
        assert resp.status_code == 403

    def test_global_org_admin_can_update_global_message(self):
        client = _make_client(self.engine, self.global_admin)
        resp = client.patch(f"/api/admin/messages/{self.global_msg.id}", json={"title": "Updated global"})
        assert resp.status_code == 200

    def test_regular_org_admin_cannot_delete_global_message(self):
        client = _make_client(self.engine, self.regular_admin)
        resp = client.delete(f"/api/admin/messages/{self.global_msg.id}")
        assert resp.status_code == 403

    def test_superadmin_can_delete_global_message(self):
        client = _make_client(self.engine, self.superadmin)
        resp = client.delete(f"/api/admin/messages/{self.global_msg.id}")
        assert resp.status_code == 204


# ===========================================================================
# Tests: active window filtering
# ===========================================================================

class TestActiveWindowFiltering:
    def setup_method(self):
        self.engine = _make_engine()
        Session = _session_factory(self.engine)
        self.db = Session()

        self.org = _create_org(self.db, "FilterOrg")
        self.member_role = _create_role(self.db, "viewer")
        self.user = _create_user(self.db)
        _assign_role(self.db, self.user, self.member_role, self.org)

        now = datetime.datetime.now(datetime.timezone.utc)
        past = now - datetime.timedelta(hours=1)
        future = now + datetime.timedelta(hours=1)
        far_future = now + datetime.timedelta(days=7)
        long_past = now - datetime.timedelta(days=7)

        # Currently active: started in past, ends in future
        self.active_msg = _create_message(
            self.db, "Active", org_id=self.org.id, start=past, end=far_future
        )
        # Not yet started: starts in the future
        self.future_msg = _create_message(
            self.db, "Future", org_id=self.org.id, start=future, end=far_future
        )
        # Already ended: ended in the past
        self.expired_msg = _create_message(
            self.db, "Expired", org_id=self.org.id, start=long_past, end=past
        )
        # No start/end: always active
        self.always_msg = _create_message(self.db, "Always", org_id=self.org.id)

    def teardown_method(self):
        self.db.close()
        _clear_overrides()

    def test_active_filter_returns_only_active_messages(self):
        client = _make_client(self.engine, self.user)
        resp = client.get(f"/api/admin/messages?organization_id={self.org.id}&active=true")
        assert resp.status_code == 200
        ids = [m["id"] for m in resp.json()]
        assert self.active_msg.id in ids
        assert self.always_msg.id in ids
        assert self.future_msg.id not in ids
        assert self.expired_msg.id not in ids

    def test_inactive_filter_returns_all_messages(self):
        client = _make_client(self.engine, self.user)
        resp = client.get(f"/api/admin/messages?organization_id={self.org.id}&active=false")
        assert resp.status_code == 200
        ids = [m["id"] for m in resp.json()]
        assert self.active_msg.id in ids
        assert self.always_msg.id in ids
        assert self.future_msg.id in ids
        assert self.expired_msg.id in ids

    def test_default_active_parameter_filters_inactive_messages(self):
        # Default is active=True; expired messages should not appear
        client = _make_client(self.engine, self.user)
        resp = client.get(f"/api/admin/messages?organization_id={self.org.id}")
        assert resp.status_code == 200
        ids = [m["id"] for m in resp.json()]
        assert self.expired_msg.id not in ids
        assert self.future_msg.id not in ids
        assert self.active_msg.id in ids
