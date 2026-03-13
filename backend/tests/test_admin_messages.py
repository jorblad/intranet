"""Tests for admin-message endpoint permission logic and filtering.

Covers:
  (1) member can list org and global messages
  (2) member cannot create/update/delete
  (3) org_admin can manage org-scoped messages only
  (4) global org_admin / superadmin can manage global messages
  (5) start/end active-window filtering and placement filtering
  (6) pubsub publish payload shape for create / update / delete
"""
import json
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest
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


# ── (6) pubsub publish payload shape ─────────────────────────────────────────

def test_create_publishes_envelope_with_correct_shape(client, test_db):
    _as_user(_make_superadmin_user())
    try:
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
    finally:
        _clear_user()


def test_update_publishes_envelope_with_correct_shape(client, test_db):
    msg_id = _seed_message(test_db, title="Original")
    _as_user(_make_superadmin_user())
    try:
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
    finally:
        _clear_user()


def test_delete_publishes_envelope_with_correct_shape(client, test_db):
    org_id = _seed_org(test_db)
    msg_id = _seed_message(test_db, org_id=org_id, title="To Delete")
    _as_user(_make_superadmin_user())
    try:
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
        assert msg["organization_id"] == org_id
        assert "placement" in msg
    finally:
        _clear_user()


def test_delete_global_message_publishes_null_organization_id(client, test_db):
    msg_id = _seed_message(test_db, org_id=None, title="Global To Delete")
    _as_user(_make_superadmin_user())
    try:
        with patch("app.api.routes.admin_messages._pubsub") as mock_pubsub:
            res = client.delete(f"/api/admin/messages/{msg_id}")
            assert res.status_code == 204

        envelope = json.loads(mock_pubsub.schedule_publish.call_args[0][0])
        payload = envelope["payload"]
        assert payload["message"]["organization_id"] is None
    finally:
        _clear_user()
