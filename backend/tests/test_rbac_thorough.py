"""Thorough RBAC tests covering core helpers, all CRUD routes, and access control."""
import uuid
from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.db.base import Base
from app.db.session import get_db
from app.api.routes.auth import get_current_user
from app.core.rbac import (
    is_superadmin,
    user_has_role,
    user_has_permission,
    require_superadmin,
    require_org_admin_or_superadmin,
)
from app.models import Organization, Role, Permission, User


# ---------------------------------------------------------------------------
# Helpers – build lightweight user SimpleNamespace objects
# ---------------------------------------------------------------------------

def _make_role(name: str, is_global: bool = False):
    return SimpleNamespace(name=name, is_global=is_global, permissions=[])


def _make_user(roles=None, org_id: str | None = None):
    """Return a SimpleNamespace user with optional role assignments."""
    if roles is None:
        roles = []
    org_roles = [
        SimpleNamespace(role=r, organization_id=org_id)
        for r in roles
    ]
    return SimpleNamespace(id=str(uuid.uuid4()), organization_roles=org_roles)


def _superadmin_user():
    return _make_user(roles=[_make_role("superadmin", is_global=True)])


def _org_admin_user(org_id: str):
    return _make_user(roles=[_make_role("org_admin", is_global=False)], org_id=org_id)


def _regular_user():
    return _make_user(roles=[])


# ---------------------------------------------------------------------------
# Shared DB / client fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db_session():
    """In-memory SQLite session factory; overrides the app's get_db dependency."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)

    def _get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _get_db
    yield SessionLocal
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def client(db_session):
    with TestClient(app) as c:
        yield c


@pytest.fixture
def as_superadmin():
    user = _superadmin_user()
    app.dependency_overrides[get_current_user] = lambda: user
    yield user
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def as_regular_user():
    user = _regular_user()
    app.dependency_overrides[get_current_user] = lambda: user
    yield user
    app.dependency_overrides.pop(get_current_user, None)


@contextmanager
def _as_org_admin_for(org_id: str):
    """Context manager that sets the current user to an org_admin for the given org."""
    user = _org_admin_user(org_id)
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        yield user
    finally:
        app.dependency_overrides.pop(get_current_user, None)

# ---------------------------------------------------------------------------
# RBAC core unit tests
# ---------------------------------------------------------------------------

class TestIsSuperadmin:
    def test_true_when_global_superadmin_role(self):
        user = _superadmin_user()
        assert is_superadmin(user) is True

    def test_false_when_superadmin_not_global(self):
        user = _make_user(roles=[_make_role("superadmin", is_global=False)])
        assert is_superadmin(user) is False

    def test_false_when_global_but_wrong_name(self):
        user = _make_user(roles=[_make_role("admin", is_global=True)])
        assert is_superadmin(user) is False

    def test_false_with_no_roles(self):
        user = _regular_user()
        assert is_superadmin(user) is False

    def test_false_with_empty_organization_roles(self):
        user = SimpleNamespace(organization_roles=[])
        assert is_superadmin(user) is False

    def test_false_with_none_organization_roles(self):
        user = SimpleNamespace(organization_roles=None)
        assert is_superadmin(user) is False


class TestUserHasRole:
    def test_match_any_org(self):
        user = _make_user(roles=[_make_role("member")], org_id="org-1")
        assert user_has_role(user, "member") is True

    def test_match_specific_org(self):
        user = _make_user(roles=[_make_role("org_admin")], org_id="org-1")
        assert user_has_role(user, "org_admin", "org-1") is True

    def test_no_match_different_org(self):
        user = _make_user(roles=[_make_role("org_admin")], org_id="org-1")
        assert user_has_role(user, "org_admin", "org-2") is False

    def test_no_match_wrong_role_name(self):
        user = _make_user(roles=[_make_role("member")], org_id="org-1")
        assert user_has_role(user, "org_admin") is False

    def test_no_match_empty_roles(self):
        user = _regular_user()
        assert user_has_role(user, "member") is False


class TestUserHasPermission:
    def _perm_role(self, codename: str, is_global: bool = True):
        perm = SimpleNamespace(codename=codename)
        rp = SimpleNamespace(permission=perm)
        return SimpleNamespace(name="some_role", is_global=is_global, permissions=[rp])

    def test_match_via_global_role(self):
        role = self._perm_role("activity.read", is_global=True)
        user = _make_user(roles=[role])
        assert user_has_permission(user, "activity.read") is True

    def test_no_match_wrong_codename(self):
        role = self._perm_role("activity.read", is_global=True)
        user = _make_user(roles=[role])
        assert user_has_permission(user, "activity.write") is False

    def test_no_match_no_permissions(self):
        user = _regular_user()
        assert user_has_permission(user, "activity.read") is False


class TestRequireSuperadmin:
    def test_passes_for_superadmin(self):
        # Should not raise
        require_superadmin(_superadmin_user())

    def test_raises_403_for_regular_user(self):
        with pytest.raises(HTTPException) as exc_info:
            require_superadmin(_regular_user())
        assert exc_info.value.status_code == 403


class TestRequireOrgAdminOrSuperadmin:
    def test_passes_for_superadmin(self):
        require_org_admin_or_superadmin(_superadmin_user(), "org-1")

    def test_passes_for_org_admin(self):
        user = _org_admin_user("org-1")
        require_org_admin_or_superadmin(user, "org-1")

    def test_raises_for_regular_user(self):
        with pytest.raises(HTTPException) as exc_info:
            require_org_admin_or_superadmin(_regular_user(), "org-1")
        assert exc_info.value.status_code == 403

    def test_raises_for_org_admin_wrong_org(self):
        user = _org_admin_user("org-1")
        with pytest.raises(HTTPException) as exc_info:
            require_org_admin_or_superadmin(user, "org-2")
        assert exc_info.value.status_code == 403


# ---------------------------------------------------------------------------
# Organization routes
# ---------------------------------------------------------------------------

class TestOrganizationRoutes:
    def test_list_organizations_as_superadmin(self, client, db_session, as_superadmin):
        # create an org directly in DB
        db = db_session()
        org = Organization(id=str(uuid.uuid4()), name="Org Alpha")
        db.add(org)
        db.commit()
        db.close()

        res = client.get("/api/rbac/organizations")
        assert res.status_code == 200
        names = [o["name"] for o in res.json()]
        assert "Org Alpha" in names

    def test_list_organizations_as_regular_user_returns_empty(self, client, db_session, as_regular_user):
        db = db_session()
        org = Organization(id=str(uuid.uuid4()), name="Org Beta")
        db.add(org)
        db.commit()
        db.close()

        res = client.get("/api/rbac/organizations")
        assert res.status_code == 200
        # Regular user has no assignments so should see an empty list
        assert res.json() == []

    def test_create_organization_as_superadmin(self, client, db_session, as_superadmin):
        res = client.post("/api/rbac/organizations", json={"name": "New Org", "language": "en"})
        assert res.status_code == 201
        data = res.json()
        assert data["name"] == "New Org"
        assert data["language"] == "en"
        assert "id" in data

    def test_create_organization_as_regular_user_is_forbidden(self, client, db_session, as_regular_user):
        res = client.post("/api/rbac/organizations", json={"name": "Forbidden Org"})
        assert res.status_code == 403

    def test_update_organization_as_superadmin(self, client, db_session, as_superadmin):
        db = db_session()
        org = Organization(id=str(uuid.uuid4()), name="Original Name")
        db.add(org)
        db.commit()
        org_id = org.id
        db.close()

        res = client.patch(f"/api/rbac/organizations/{org_id}", json={"name": "Updated Name"})
        assert res.status_code == 200
        assert res.json()["name"] == "Updated Name"

    def test_update_organization_as_regular_user_is_forbidden(self, client, db_session, as_regular_user):
        db = db_session()
        org = Organization(id=str(uuid.uuid4()), name="Some Org")
        db.add(org)
        db.commit()
        org_id = org.id
        db.close()

        res = client.patch(f"/api/rbac/organizations/{org_id}", json={"name": "Hacked"})
        assert res.status_code == 403

    def test_update_organization_as_org_admin_of_that_org(self, client, db_session):
        db = db_session()
        org = Organization(id=str(uuid.uuid4()), name="Org Admin Org")
        db.add(org)
        db.commit()
        org_id = org.id
        db.close()

        with _as_org_admin_for(org_id):
            res = client.patch(f"/api/rbac/organizations/{org_id}", json={"name": "Org Admin Updated"})
            assert res.status_code == 200
            assert res.json()["name"] == "Org Admin Updated"

    def test_update_organization_as_org_admin_of_different_org_is_forbidden(self, client, db_session):
        db = db_session()
        org_a = Organization(id=str(uuid.uuid4()), name="Org A")
        org_b = Organization(id=str(uuid.uuid4()), name="Org B")
        db.add_all([org_a, org_b])
        db.commit()
        org_a_id, org_b_id = org_a.id, org_b.id
        db.close()

        # org_admin of org_a tries to update org_b — must be forbidden
        with _as_org_admin_for(org_a_id):
            res = client.patch(f"/api/rbac/organizations/{org_b_id}", json={"name": "Should Fail"})
            assert res.status_code == 403

    def test_update_organization_not_found(self, client, db_session, as_superadmin):
        res = client.patch("/api/rbac/organizations/nonexistent-id", json={"name": "X"})
        assert res.status_code == 404

    def test_delete_organization_as_superadmin(self, client, db_session, as_superadmin):
        db = db_session()
        org = Organization(id=str(uuid.uuid4()), name="To Delete")
        db.add(org)
        db.commit()
        org_id = org.id
        db.close()

        res = client.delete(f"/api/rbac/organizations/{org_id}")
        assert res.status_code == 204

    def test_delete_organization_as_regular_user_is_forbidden(self, client, db_session, as_regular_user):
        db = db_session()
        org = Organization(id=str(uuid.uuid4()), name="Protected Org")
        db.add(org)
        db.commit()
        org_id = org.id
        db.close()

        res = client.delete(f"/api/rbac/organizations/{org_id}")
        assert res.status_code == 403

    def test_delete_organization_not_found(self, client, db_session, as_superadmin):
        res = client.delete("/api/rbac/organizations/nonexistent-id")
        assert res.status_code == 404

    def test_get_organization_detail(self, client, db_session, as_superadmin):
        db = db_session()
        org = Organization(id=str(uuid.uuid4()), name="Detail Org")
        db.add(org)
        db.commit()
        org_id = org.id
        db.close()

        res = client.get(f"/api/rbac/organizations/{org_id}")
        assert res.status_code == 200
        assert res.json()["name"] == "Detail Org"

    def test_get_organization_detail_not_found(self, client, db_session, as_superadmin):
        res = client.get("/api/rbac/organizations/nonexistent-id")
        assert res.status_code == 404


# ---------------------------------------------------------------------------
# Role routes
# ---------------------------------------------------------------------------

class TestRoleRoutes:
    def test_list_roles_returns_list(self, client, db_session, as_superadmin):
        db = db_session()
        role = Role(id=str(uuid.uuid4()), name="viewer", description="Read only")
        db.add(role)
        db.commit()
        db.close()

        res = client.get("/api/rbac/roles")
        assert res.status_code == 200
        names = [r["name"] for r in res.json()]
        assert "viewer" in names

    def test_create_role_as_superadmin(self, client, db_session, as_superadmin):
        res = client.post("/api/rbac/roles", json={"name": "editor", "description": "Can edit", "is_global": False})
        assert res.status_code == 201
        data = res.json()
        assert data["name"] == "editor"
        assert "id" in data

    def test_create_role_as_regular_user_is_forbidden(self, client, db_session, as_regular_user):
        res = client.post("/api/rbac/roles", json={"name": "hacker"})
        assert res.status_code == 403

    def test_get_role_detail(self, client, db_session, as_superadmin):
        db = db_session()
        role = Role(id=str(uuid.uuid4()), name="moderator")
        db.add(role)
        db.commit()
        role_id = role.id
        db.close()

        res = client.get(f"/api/rbac/roles/{role_id}")
        assert res.status_code == 200
        assert res.json()["name"] == "moderator"

    def test_get_role_detail_not_found(self, client, db_session, as_superadmin):
        res = client.get("/api/rbac/roles/nonexistent-id")
        assert res.status_code == 404

    def test_update_role_as_superadmin(self, client, db_session, as_superadmin):
        db = db_session()
        role = Role(id=str(uuid.uuid4()), name="old_name")
        db.add(role)
        db.commit()
        role_id = role.id
        db.close()

        res = client.patch(f"/api/rbac/roles/{role_id}", json={"name": "new_name"})
        assert res.status_code == 200
        assert res.json()["name"] == "new_name"

    def test_update_role_as_regular_user_is_forbidden(self, client, db_session, as_regular_user):
        db = db_session()
        role = Role(id=str(uuid.uuid4()), name="some_role")
        db.add(role)
        db.commit()
        role_id = role.id
        db.close()

        res = client.patch(f"/api/rbac/roles/{role_id}", json={"name": "tampered"})
        assert res.status_code == 403

    def test_update_role_not_found(self, client, db_session, as_superadmin):
        res = client.patch("/api/rbac/roles/nonexistent-id", json={"name": "x"})
        assert res.status_code == 404

    def test_delete_role_as_superadmin(self, client, db_session, as_superadmin):
        db = db_session()
        role = Role(id=str(uuid.uuid4()), name="temp_role")
        db.add(role)
        db.commit()
        role_id = role.id
        db.close()

        res = client.delete(f"/api/rbac/roles/{role_id}")
        assert res.status_code == 204

    def test_delete_role_as_regular_user_is_forbidden(self, client, db_session, as_regular_user):
        db = db_session()
        role = Role(id=str(uuid.uuid4()), name="protected_role")
        db.add(role)
        db.commit()
        role_id = role.id
        db.close()

        res = client.delete(f"/api/rbac/roles/{role_id}")
        assert res.status_code == 403

    def test_delete_role_not_found(self, client, db_session, as_superadmin):
        res = client.delete("/api/rbac/roles/nonexistent-id")
        assert res.status_code == 404


# ---------------------------------------------------------------------------
# Permission routes (supplementing existing tests)
# ---------------------------------------------------------------------------

class TestPermissionRoutes:
    def _seed_perm(self, db_session, codename: str = "test.perm") -> str:
        db = db_session()
        perm = Permission(id=str(uuid.uuid4()), codename=codename, description="test")
        db.add(perm)
        db.commit()
        perm_id = perm.id
        db.close()
        return perm_id

    def test_list_permissions(self, client, db_session, as_superadmin):
        self._seed_perm(db_session, "list.perm")
        res = client.get("/api/rbac/permissions")
        assert res.status_code == 200
        codenames = [p["codename"] for p in res.json()]
        assert "list.perm" in codenames

    def test_list_permissions_as_regular_user(self, client, db_session, as_regular_user):
        # listing permissions is open to any authenticated user
        res = client.get("/api/rbac/permissions")
        assert res.status_code == 200

    def test_get_permission_detail(self, client, db_session, as_superadmin):
        perm_id = self._seed_perm(db_session, "detail.perm")
        res = client.get(f"/api/rbac/permissions/{perm_id}")
        assert res.status_code == 200
        assert res.json()["codename"] == "detail.perm"

    def test_get_permission_not_found(self, client, db_session, as_superadmin):
        res = client.get("/api/rbac/permissions/nonexistent-id")
        assert res.status_code == 404

    def test_update_permission_as_superadmin(self, client, db_session, as_superadmin):
        perm_id = self._seed_perm(db_session, "update.before")
        res = client.patch(f"/api/rbac/permissions/{perm_id}", json={"codename": "update.after"})
        assert res.status_code == 200
        assert res.json()["codename"] == "update.after"

    def test_update_permission_as_regular_user_is_forbidden(self, client, db_session, as_regular_user):
        perm_id = self._seed_perm(db_session, "forbidden.update")
        res = client.patch(f"/api/rbac/permissions/{perm_id}", json={"codename": "hacked"})
        assert res.status_code == 403

    def test_update_permission_not_found(self, client, db_session, as_superadmin):
        res = client.patch("/api/rbac/permissions/nonexistent-id", json={"codename": "x"})
        assert res.status_code == 404

    def test_delete_permission_as_superadmin(self, client, db_session, as_superadmin):
        perm_id = self._seed_perm(db_session, "delete.perm")
        res = client.delete(f"/api/rbac/permissions/{perm_id}")
        assert res.status_code == 204

    def test_delete_permission_as_regular_user_is_forbidden(self, client, db_session, as_regular_user):
        perm_id = self._seed_perm(db_session, "forbidden.delete")
        res = client.delete(f"/api/rbac/permissions/{perm_id}")
        assert res.status_code == 403

    def test_delete_permission_not_found(self, client, db_session, as_superadmin):
        res = client.delete("/api/rbac/permissions/nonexistent-id")
        assert res.status_code == 404


# ---------------------------------------------------------------------------
# Role <-> Permission relationship routes
# ---------------------------------------------------------------------------

class TestRolePermissionRoutes:
    def _seed_role_and_perm(self, db_session):
        db = db_session()
        role = Role(id=str(uuid.uuid4()), name="perm_role")
        perm = Permission(id=str(uuid.uuid4()), codename="rp.test")
        db.add_all([role, perm])
        db.commit()
        role_id, perm_id = role.id, perm.id
        db.close()
        return role_id, perm_id

    def test_get_role_permissions_as_superadmin(self, client, db_session, as_superadmin):
        role_id, _ = self._seed_role_and_perm(db_session)
        res = client.get(f"/api/rbac/roles/{role_id}/permissions")
        assert res.status_code == 200
        data = res.json()
        assert "role_id" in data
        assert "permission_ids" in data

    def test_get_role_permissions_as_regular_user_is_forbidden(self, client, db_session, as_regular_user):
        role_id, _ = self._seed_role_and_perm(db_session)
        res = client.get(f"/api/rbac/roles/{role_id}/permissions")
        assert res.status_code == 403

    def test_get_role_permissions_not_found(self, client, db_session, as_superadmin):
        res = client.get("/api/rbac/roles/nonexistent-id/permissions")
        assert res.status_code == 404

    def test_set_role_permissions_as_superadmin(self, client, db_session, as_superadmin):
        role_id, perm_id = self._seed_role_and_perm(db_session)
        res = client.put(f"/api/rbac/roles/{role_id}/permissions", json={"permission_ids": [perm_id]})
        assert res.status_code == 200
        data = res.json()
        assert perm_id in data["permission_ids"]

    def test_set_role_permissions_as_regular_user_is_forbidden(self, client, db_session, as_regular_user):
        role_id, perm_id = self._seed_role_and_perm(db_session)
        res = client.put(f"/api/rbac/roles/{role_id}/permissions", json={"permission_ids": [perm_id]})
        assert res.status_code == 403

    def test_set_role_permissions_not_found(self, client, db_session, as_superadmin):
        res = client.put("/api/rbac/roles/nonexistent-id/permissions", json={"permission_ids": []})
        assert res.status_code == 404

    def test_clear_role_permissions(self, client, db_session, as_superadmin):
        """Setting an empty list should remove all permissions from the role."""
        role_id, perm_id = self._seed_role_and_perm(db_session)
        # First assign the permission
        client.put(f"/api/rbac/roles/{role_id}/permissions", json={"permission_ids": [perm_id]})
        # Now clear it
        res = client.put(f"/api/rbac/roles/{role_id}/permissions", json={"permission_ids": []})
        assert res.status_code == 200
        assert res.json()["permission_ids"] == []


# ---------------------------------------------------------------------------
# Role permission resources routes
# ---------------------------------------------------------------------------

class TestRolePermissionResourcesRoutes:
    def _seed_role(self, db_session):
        db = db_session()
        role = Role(id=str(uuid.uuid4()), name="res_role")
        db.add(role)
        db.commit()
        role_id = role.id
        db.close()
        return role_id

    def test_list_permission_resources_as_superadmin(self, client, db_session, as_superadmin):
        role_id = self._seed_role(db_session)
        res = client.get(f"/api/rbac/roles/{role_id}/permission-resources")
        assert res.status_code == 200

    def test_list_permission_resources_as_regular_user_is_forbidden(self, client, db_session, as_regular_user):
        role_id = self._seed_role(db_session)
        res = client.get(f"/api/rbac/roles/{role_id}/permission-resources")
        assert res.status_code == 403

    def test_list_permission_resources_role_not_found(self, client, db_session, as_superadmin):
        res = client.get("/api/rbac/roles/nonexistent-id/permission-resources")
        assert res.status_code == 404

    def test_delete_permission_resources_as_superadmin(self, client, db_session, as_superadmin):
        role_id = self._seed_role(db_session)
        res = client.delete(f"/api/rbac/roles/{role_id}/permission-resources?resource_type=activity")
        assert res.status_code == 200

    def test_delete_permission_resources_as_regular_user_is_forbidden(self, client, db_session, as_regular_user):
        role_id = self._seed_role(db_session)
        res = client.delete(f"/api/rbac/roles/{role_id}/permission-resources?resource_type=activity")
        assert res.status_code == 403

    def test_delete_permission_resources_role_not_found(self, client, db_session, as_superadmin):
        res = client.delete("/api/rbac/roles/nonexistent-id/permission-resources?resource_type=activity")
        assert res.status_code == 404


# ---------------------------------------------------------------------------
# Assignment routes
# ---------------------------------------------------------------------------

class TestAssignmentRoutes:
    def _seed_user_and_role(self, db_session):
        db = db_session()
        user = User(
            id=str(uuid.uuid4()),
            username=f"u_{uuid.uuid4().hex[:6]}",
            display_name="Test User",
            hashed_password="placeholder",
        )
        role = Role(id=str(uuid.uuid4()), name=f"r_{uuid.uuid4().hex[:6]}")
        db.add_all([user, role])
        db.commit()
        user_id, role_id = user.id, role.id
        db.close()
        return user_id, role_id

    def test_create_assignment_as_superadmin(self, client, db_session, as_superadmin):
        user_id, role_id = self._seed_user_and_role(db_session)
        res = client.post("/api/rbac/assignments", json={"user_id": user_id, "role_id": role_id})
        assert res.status_code == 201
        data = res.json()
        assert data["user_id"] == user_id
        assert data["role_id"] == role_id

    def test_create_global_assignment_as_regular_user_is_forbidden(self, client, db_session, as_regular_user):
        user_id, role_id = self._seed_user_and_role(db_session)
        # organization_id=None → global assignment → superadmin required
        res = client.post("/api/rbac/assignments", json={"user_id": user_id, "role_id": role_id})
        assert res.status_code == 403

    def test_list_all_assignments_as_superadmin(self, client, db_session, as_superadmin):
        res = client.get("/api/rbac/assignments")
        assert res.status_code == 200
        assert isinstance(res.json(), list)

    def test_list_all_assignments_as_regular_user_is_forbidden(self, client, db_session, as_regular_user):
        res = client.get("/api/rbac/assignments")
        assert res.status_code == 403

    def test_list_assignments_by_user_id(self, client, db_session, as_superadmin):
        user_id, role_id = self._seed_user_and_role(db_session)
        # create an assignment first
        client.post("/api/rbac/assignments", json={"user_id": user_id, "role_id": role_id})

        res = client.get(f"/api/rbac/assignments?user_id={user_id}")
        assert res.status_code == 200
        data = res.json()
        assert any(a["user_id"] == user_id for a in data)

    def test_delete_assignment_as_superadmin(self, client, db_session, as_superadmin):
        user_id, role_id = self._seed_user_and_role(db_session)
        create_res = client.post("/api/rbac/assignments", json={"user_id": user_id, "role_id": role_id})
        assignment_id = create_res.json()["id"]

        res = client.delete(f"/api/rbac/assignments/{assignment_id}")
        assert res.status_code == 204

    def test_delete_assignment_not_found(self, client, db_session, as_superadmin):
        res = client.delete("/api/rbac/assignments/nonexistent-id")
        assert res.status_code == 404

    def test_update_assignment_as_superadmin(self, client, db_session, as_superadmin):
        user_id, role_id = self._seed_user_and_role(db_session)
        create_res = client.post("/api/rbac/assignments", json={"user_id": user_id, "role_id": role_id})
        assignment_id = create_res.json()["id"]

        # Create a second role to reassign to
        db = db_session()
        new_role = Role(id=str(uuid.uuid4()), name=f"r2_{uuid.uuid4().hex[:6]}")
        db.add(new_role)
        db.commit()
        new_role_id = new_role.id
        db.close()

        res = client.patch(f"/api/rbac/assignments/{assignment_id}", json={"role_id": new_role_id})
        assert res.status_code == 200
        assert res.json()["role_id"] == new_role_id

    def test_update_assignment_not_found(self, client, db_session, as_superadmin):
        res = client.patch("/api/rbac/assignments/nonexistent-id", json={"role_id": "x"})
        assert res.status_code == 404

    def test_list_assignments_for_user_endpoint(self, client, db_session, as_superadmin):
        user_id, role_id = self._seed_user_and_role(db_session)
        client.post("/api/rbac/assignments", json={"user_id": user_id, "role_id": role_id})

        res = client.get(f"/api/rbac/users/{user_id}/assignments")
        assert res.status_code == 200
        data = res.json()
        assert any(a["user_id"] == user_id for a in data)

    def test_create_org_scoped_assignment_as_org_admin(self, client, db_session):
        """org_admin may create assignments scoped to their own org."""
        db = db_session()
        org = Organization(id=str(uuid.uuid4()), name="Assign Org")
        user = User(
            id=str(uuid.uuid4()),
            username=f"u_{uuid.uuid4().hex[:6]}",
            display_name="Target User",
            hashed_password="placeholder",
        )
        role = Role(id=str(uuid.uuid4()), name=f"r_{uuid.uuid4().hex[:6]}")
        db.add_all([org, user, role])
        db.commit()
        org_id, user_id, role_id = org.id, user.id, role.id
        db.close()

        with _as_org_admin_for(org_id):
            res = client.post(
                "/api/rbac/assignments",
                json={"user_id": user_id, "role_id": role_id, "organization_id": org_id},
            )
            assert res.status_code == 201
            assert res.json()["organization_id"] == org_id

    def test_create_org_scoped_assignment_as_org_admin_of_different_org_is_forbidden(self, client, db_session):
        """org_admin of org A cannot create assignments for org B."""
        db = db_session()
        org_a = Organization(id=str(uuid.uuid4()), name="Org A (admin)")
        org_b = Organization(id=str(uuid.uuid4()), name="Org B (target)")
        user = User(
            id=str(uuid.uuid4()),
            username=f"u_{uuid.uuid4().hex[:6]}",
            display_name="Target User",
            hashed_password="placeholder",
        )
        role = Role(id=str(uuid.uuid4()), name=f"r_{uuid.uuid4().hex[:6]}")
        db.add_all([org_a, org_b, user, role])
        db.commit()
        org_a_id, org_b_id, user_id, role_id = org_a.id, org_b.id, user.id, role.id
        db.close()

        # admin of org_a tries to create an assignment for org_b — must be forbidden
        with _as_org_admin_for(org_a_id):
            res = client.post(
                "/api/rbac/assignments",
                json={"user_id": user_id, "role_id": role_id, "organization_id": org_b_id},
            )
            assert res.status_code == 403


# ---------------------------------------------------------------------------
# apply-program-preset access control (supplemental)
# ---------------------------------------------------------------------------

class TestApplyProgramPresetAccessControl:
    def test_apply_preset_as_regular_user_is_forbidden(self, client, db_session, as_regular_user):
        db = db_session()
        role = Role(id=str(uuid.uuid4()), name="preset_role")
        db.add(role)
        db.commit()
        role_id = role.id
        db.close()

        res = client.post(
            f"/api/rbac/roles/{role_id}/apply-program-preset",
            json={"preset": "read", "resource_type": "activity"},
        )
        assert res.status_code == 403

    def test_apply_preset_with_unknown_preset_returns_400(self, client, db_session, as_superadmin):
        db = db_session()
        role = Role(id=str(uuid.uuid4()), name="preset_role2")
        db.add(role)
        db.commit()
        role_id = role.id
        db.close()

        res = client.post(
            f"/api/rbac/roles/{role_id}/apply-program-preset",
            json={"preset": "garbage_preset", "resource_type": "activity"},
        )
        assert res.status_code == 400

    def test_apply_preset_role_not_found(self, client, db_session, as_superadmin):
        res = client.post(
            "/api/rbac/roles/nonexistent-id/apply-program-preset",
            json={"preset": "read", "resource_type": "activity"},
        )
        assert res.status_code == 404
