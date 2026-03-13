"""
Tests for the admin messages API endpoints.

Covers:
- org-scoped vs global messages (list/create behaviour)
- org member read access
- org_admin vs superadmin write access
- pubsub publish payload shape for create / update / delete
"""
import json
import uuid
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from unittest.mock import patch

from app.main import app
from app.db.base import Base
from app.db.session import get_db
from app.api.routes.auth import get_current_user
from app.models import Organization, AdminMessage


# ---------------------------------------------------------------------------
# Helpers for building fake user namespaces
# ---------------------------------------------------------------------------

def _role_ns(name, is_global=False):
    return SimpleNamespace(name=name, is_global=is_global)


def _uor_ns(role, organization_id=None):
    return SimpleNamespace(role=role, organization_id=organization_id)


def _make_user(roles_and_orgs):
    """Return a SimpleNamespace user with given list of (role_ns, organization_id) tuples."""
    return SimpleNamespace(
        id=str(uuid.uuid4()),
        organization_roles=[_uor_ns(r, oid) for r, oid in roles_and_orgs],
    )


def _superadmin():
    return _make_user([(_role_ns("superadmin", is_global=True), None)])


def _global_org_admin():
    return _make_user([(_role_ns("org_admin", is_global=True), None)])


def _org_admin(org_id):
    return _make_user([(_role_ns("org_admin", is_global=False), org_id)])


def _org_member(org_id):
    return _make_user([(_role_ns("member", is_global=False), org_id)])


def _plain_user():
    return _make_user([])


# ---------------------------------------------------------------------------
# Database fixture
# ---------------------------------------------------------------------------

@pytest.fixture
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


@pytest.fixture
def client(test_db):
    return TestClient(app)


@pytest.fixture
def orgs(test_db):
    """Seed two organizations and return their IDs."""
    db = test_db()
    try:
        org1 = Organization(id=str(uuid.uuid4()), name="OrgOne")
        org2 = Organization(id=str(uuid.uuid4()), name="OrgTwo")
        db.add_all([org1, org2])
        db.commit()
        return {"org1_id": org1.id, "org2_id": org2.id}
    finally:
        db.close()


@pytest.fixture(autouse=True)
def clear_user_override():
    """Ensure the get_current_user override is cleared after each test."""
    yield
    app.dependency_overrides.pop(get_current_user, None)


# ---------------------------------------------------------------------------
# Helper: seed an AdminMessage directly in the test DB
# ---------------------------------------------------------------------------

def _create_message(Session, title="Test Message", organization_id=None, placement="banner"):
    db = Session()
    try:
        msg = AdminMessage(
            id=str(uuid.uuid4()),
            title=title,
            organization_id=organization_id,
            placement=placement,
            priority=0,
        )
        db.add(msg)
        db.commit()
        return msg.id
    finally:
        db.close()


def _set_user(user):
    app.dependency_overrides[get_current_user] = lambda: user


# ===========================================================================
# 1. org-scoped vs global messages
# ===========================================================================

class TestOrgScopedVsGlobal:

    def test_list_without_org_id_returns_only_global_messages(self, client, test_db, orgs):
        org1_id = orgs["org1_id"]
        _create_message(test_db, title="Global Msg", organization_id=None)
        _create_message(test_db, title="Org1 Msg", organization_id=org1_id)

        _set_user(_superadmin())
        res = client.get("/api/admin/messages")

        assert res.status_code == 200
        titles = [m["title"] for m in res.json()]
        assert "Global Msg" in titles
        assert "Org1 Msg" not in titles

    def test_list_with_org_id_returns_org_and_global_messages(self, client, test_db, orgs):
        org1_id = orgs["org1_id"]
        org2_id = orgs["org2_id"]
        _create_message(test_db, title="Global Msg", organization_id=None)
        _create_message(test_db, title="Org1 Msg", organization_id=org1_id)
        _create_message(test_db, title="Org2 Msg", organization_id=org2_id)

        _set_user(_superadmin())
        res = client.get(f"/api/admin/messages?organization_id={org1_id}")

        assert res.status_code == 200
        titles = [m["title"] for m in res.json()]
        assert "Global Msg" in titles
        assert "Org1 Msg" in titles
        assert "Org2 Msg" not in titles

    def test_list_with_org2_id_does_not_return_org1_message(self, client, test_db, orgs):
        org1_id = orgs["org1_id"]
        org2_id = orgs["org2_id"]
        _create_message(test_db, title="Org1 Msg", organization_id=org1_id)

        _set_user(_superadmin())
        res = client.get(f"/api/admin/messages?organization_id={org2_id}")

        assert res.status_code == 200
        titles = [m["title"] for m in res.json()]
        assert "Org1 Msg" not in titles

    def test_create_global_message_has_null_organization_id(self, client, test_db):
        _set_user(_superadmin())
        res = client.post(
            "/api/admin/messages", json={"title": "Global", "placement": "banner"}
        )

        assert res.status_code == 201
        assert res.json()["organization_id"] is None

    def test_create_org_message_stores_organization_id(self, client, test_db, orgs):
        org1_id = orgs["org1_id"]
        _set_user(_superadmin())
        res = client.post(
            "/api/admin/messages",
            json={"title": "Org Msg", "organization_id": org1_id, "placement": "banner"},
        )

        assert res.status_code == 201
        assert res.json()["organization_id"] == org1_id


# ===========================================================================
# 2. org member read access
# ===========================================================================

class TestOrgMemberReadAccess:

    def test_org_member_can_list_messages_for_their_org(self, client, test_db, orgs):
        org1_id = orgs["org1_id"]
        _create_message(test_db, title="Org1 Msg", organization_id=org1_id)

        _set_user(_org_member(org1_id))
        res = client.get(f"/api/admin/messages?organization_id={org1_id}")

        assert res.status_code == 200
        titles = [m["title"] for m in res.json()]
        assert "Org1 Msg" in titles

    def test_non_member_cannot_list_messages_for_org(self, client, test_db, orgs):
        org1_id = orgs["org1_id"]
        _set_user(_plain_user())
        res = client.get(f"/api/admin/messages?organization_id={org1_id}")

        assert res.status_code == 403

    def test_org_member_can_view_message_detail(self, client, test_db, orgs):
        org1_id = orgs["org1_id"]
        msg_id = _create_message(test_db, title="Org1 Msg", organization_id=org1_id)

        _set_user(_org_member(org1_id))
        res = client.get(f"/api/admin/messages/{msg_id}")

        assert res.status_code == 200

    def test_non_member_cannot_view_org_message_detail(self, client, test_db, orgs):
        org1_id = orgs["org1_id"]
        msg_id = _create_message(test_db, title="Org1 Msg", organization_id=org1_id)

        _set_user(_plain_user())
        res = client.get(f"/api/admin/messages/{msg_id}")

        assert res.status_code == 403

    def test_org_member_cannot_create_messages(self, client, test_db, orgs):
        org1_id = orgs["org1_id"]
        _set_user(_org_member(org1_id))
        res = client.post(
            "/api/admin/messages",
            json={"title": "Attempt", "organization_id": org1_id, "placement": "banner"},
        )

        assert res.status_code == 403

    def test_org_member_cannot_update_messages(self, client, test_db, orgs):
        org1_id = orgs["org1_id"]
        msg_id = _create_message(test_db, title="Org1 Msg", organization_id=org1_id)

        _set_user(_org_member(org1_id))
        res = client.patch(f"/api/admin/messages/{msg_id}", json={"title": "Updated"})

        assert res.status_code == 403

    def test_org_member_cannot_delete_messages(self, client, test_db, orgs):
        org1_id = orgs["org1_id"]
        msg_id = _create_message(test_db, title="Org1 Msg", organization_id=org1_id)

        _set_user(_org_member(org1_id))
        res = client.delete(f"/api/admin/messages/{msg_id}")

        assert res.status_code == 403

    def test_global_message_accessible_without_org_assignment(self, client, test_db):
        msg_id = _create_message(test_db, title="Global Msg", organization_id=None)

        _set_user(_plain_user())
        res = client.get(f"/api/admin/messages/{msg_id}")

        assert res.status_code == 200


# ===========================================================================
# 3. org_admin vs superadmin write access
# ===========================================================================

class TestWriteAccess:

    def test_org_admin_can_create_message_for_their_org(self, client, test_db, orgs):
        org1_id = orgs["org1_id"]
        _set_user(_org_admin(org1_id))
        res = client.post(
            "/api/admin/messages",
            json={"title": "Org1 Msg", "organization_id": org1_id, "placement": "banner"},
        )

        assert res.status_code == 201

    def test_org_admin_cannot_create_global_message(self, client, test_db, orgs):
        org1_id = orgs["org1_id"]
        _set_user(_org_admin(org1_id))
        res = client.post(
            "/api/admin/messages", json={"title": "Global Msg", "placement": "banner"}
        )

        assert res.status_code == 403

    def test_org_admin_cannot_create_message_for_other_org(self, client, test_db, orgs):
        org1_id = orgs["org1_id"]
        org2_id = orgs["org2_id"]
        _set_user(_org_admin(org1_id))
        res = client.post(
            "/api/admin/messages",
            json={"title": "Org2 Msg", "organization_id": org2_id, "placement": "banner"},
        )

        assert res.status_code == 403

    def test_global_org_admin_can_create_global_message(self, client, test_db):
        _set_user(_global_org_admin())
        res = client.post(
            "/api/admin/messages", json={"title": "Global Msg", "placement": "banner"}
        )

        assert res.status_code == 201

    def test_superadmin_can_create_global_message(self, client, test_db):
        _set_user(_superadmin())
        res = client.post(
            "/api/admin/messages", json={"title": "Global Msg", "placement": "banner"}
        )

        assert res.status_code == 201

    def test_superadmin_can_create_org_message(self, client, test_db, orgs):
        org1_id = orgs["org1_id"]
        _set_user(_superadmin())
        res = client.post(
            "/api/admin/messages",
            json={"title": "Org Msg", "organization_id": org1_id, "placement": "banner"},
        )

        assert res.status_code == 201

    def test_org_admin_can_update_message_for_their_org(self, client, test_db, orgs):
        org1_id = orgs["org1_id"]
        msg_id = _create_message(test_db, organization_id=org1_id)

        _set_user(_org_admin(org1_id))
        res = client.patch(f"/api/admin/messages/{msg_id}", json={"title": "Updated"})

        assert res.status_code == 200
        assert res.json()["title"] == "Updated"

    def test_org_admin_cannot_update_message_for_other_org(self, client, test_db, orgs):
        org1_id = orgs["org1_id"]
        org2_id = orgs["org2_id"]
        msg_id = _create_message(test_db, organization_id=org2_id)

        _set_user(_org_admin(org1_id))
        res = client.patch(f"/api/admin/messages/{msg_id}", json={"title": "Updated"})

        assert res.status_code == 403

    def test_org_admin_cannot_update_global_message(self, client, test_db):
        msg_id = _create_message(test_db, organization_id=None)
        some_org_id = str(uuid.uuid4())

        _set_user(_org_admin(some_org_id))
        res = client.patch(f"/api/admin/messages/{msg_id}", json={"title": "Updated"})

        assert res.status_code == 403

    def test_superadmin_can_update_any_message(self, client, test_db, orgs):
        org1_id = orgs["org1_id"]
        msg_id = _create_message(test_db, organization_id=org1_id)

        _set_user(_superadmin())
        res = client.patch(f"/api/admin/messages/{msg_id}", json={"title": "Updated"})

        assert res.status_code == 200

    def test_org_admin_can_delete_message_for_their_org(self, client, test_db, orgs):
        org1_id = orgs["org1_id"]
        msg_id = _create_message(test_db, organization_id=org1_id)

        _set_user(_org_admin(org1_id))
        res = client.delete(f"/api/admin/messages/{msg_id}")

        assert res.status_code == 204

    def test_org_admin_cannot_delete_message_for_other_org(self, client, test_db, orgs):
        org1_id = orgs["org1_id"]
        org2_id = orgs["org2_id"]
        msg_id = _create_message(test_db, organization_id=org2_id)

        _set_user(_org_admin(org1_id))
        res = client.delete(f"/api/admin/messages/{msg_id}")

        assert res.status_code == 403

    def test_org_admin_cannot_delete_global_message(self, client, test_db):
        msg_id = _create_message(test_db, organization_id=None)
        some_org_id = str(uuid.uuid4())

        _set_user(_org_admin(some_org_id))
        res = client.delete(f"/api/admin/messages/{msg_id}")

        assert res.status_code == 403

    def test_superadmin_can_delete_any_message(self, client, test_db, orgs):
        org1_id = orgs["org1_id"]
        msg_id = _create_message(test_db, organization_id=org1_id)

        _set_user(_superadmin())
        res = client.delete(f"/api/admin/messages/{msg_id}")

        assert res.status_code == 204


# ===========================================================================
# 4. Publish payload shape for create / update / delete
# ===========================================================================

class TestPubSubPayload:

    def test_create_publishes_envelope_with_correct_shape(self, client, test_db):
        _set_user(_superadmin())

        with patch("app.api.routes.admin_messages._pubsub") as mock_pubsub:
            res = client.post(
                "/api/admin/messages",
                json={"title": "PubSub Test", "placement": "banner", "priority": 5},
            )
            assert res.status_code == 201
            assert mock_pubsub.schedule_publish.called

        envelope = json.loads(mock_pubsub.schedule_publish.call_args[0][0])
        assert "__origin_pid" in envelope
        payload = envelope["payload"]
        assert payload["type"] == "admin_message"
        assert payload["action"] == "create"
        msg = payload["message"]
        assert "id" in msg
        assert msg["title"] == "PubSub Test"
        assert "organization_id" in msg
        assert "placement" in msg
        assert "priority" in msg
        assert "created_at" in msg

    def test_update_publishes_envelope_with_correct_shape(self, client, test_db):
        msg_id = _create_message(test_db, title="Original")
        _set_user(_superadmin())

        with patch("app.api.routes.admin_messages._pubsub") as mock_pubsub:
            res = client.patch(
                f"/api/admin/messages/{msg_id}", json={"title": "Updated Title"}
            )
            assert res.status_code == 200
            assert mock_pubsub.schedule_publish.called

        envelope = json.loads(mock_pubsub.schedule_publish.call_args[0][0])
        assert "__origin_pid" in envelope
        payload = envelope["payload"]
        assert payload["type"] == "admin_message"
        assert payload["action"] == "update"
        msg = payload["message"]
        assert msg["id"] == msg_id
        assert msg["title"] == "Updated Title"
        assert "organization_id" in msg

    def test_delete_publishes_envelope_with_correct_shape(self, client, test_db, orgs):
        org1_id = orgs["org1_id"]
        msg_id = _create_message(test_db, title="To Delete", organization_id=org1_id)
        _set_user(_superadmin())

        with patch("app.api.routes.admin_messages._pubsub") as mock_pubsub:
            res = client.delete(f"/api/admin/messages/{msg_id}")
            assert res.status_code == 204
            assert mock_pubsub.schedule_publish.called

        envelope = json.loads(mock_pubsub.schedule_publish.call_args[0][0])
        assert "__origin_pid" in envelope
        payload = envelope["payload"]
        assert payload["type"] == "admin_message"
        assert payload["action"] == "delete"
        msg = payload["message"]
        assert msg["id"] == msg_id
        assert msg["organization_id"] == org1_id
        assert "placement" in msg

    def test_delete_global_message_publishes_null_organization_id(self, client, test_db):
        msg_id = _create_message(test_db, title="Global To Delete", organization_id=None)
        _set_user(_superadmin())

        with patch("app.api.routes.admin_messages._pubsub") as mock_pubsub:
            res = client.delete(f"/api/admin/messages/{msg_id}")
            assert res.status_code == 204

        envelope = json.loads(mock_pubsub.schedule_publish.call_args[0][0])
        payload = envelope["payload"]
        assert payload["message"]["organization_id"] is None
