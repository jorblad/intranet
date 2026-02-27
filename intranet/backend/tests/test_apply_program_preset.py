import uuid
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.db.base import Base
from app.db.session import get_db
from app.models import Role, Permission, RolePermissionResource


@pytest.fixture
def test_db():
    # in-memory sqlite for tests
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)

    def _get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    # override dependency
    app.dependency_overrides[get_db] = _get_db
    yield TestingSessionLocal
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def client(test_db):
    return TestClient(app)


@pytest.fixture
def superadmin_user_override():
    # return a simple object that satisfies require_superadmin
    def _override():
        return SimpleNamespace(organization_roles=[SimpleNamespace(role=SimpleNamespace(name='superadmin', is_global=True))])
    from app.api.routes.auth import get_current_user
    app.dependency_overrides[get_current_user] = lambda: _override()
    yield
    from app.api.routes.auth import get_current_user as _g
    app.dependency_overrides.pop(_g, None)


def seed_role_and_programs(test_db):
    Session = test_db
    db = Session()
    try:
        role = Role(id=str(uuid.uuid4()), name='tester', description='test role')
        db.add(role)
        from app.models import Activity
        p1 = Activity(id=str(uuid.uuid4()), name='A1')
        p2 = Activity(id=str(uuid.uuid4()), name='A2')
        db.add_all([p1, p2])
        db.commit()
        return role, [p1, p2]
    finally:
        db.close()


def test_apply_preset_to_selected_programs(client, test_db, superadmin_user_override):
    Session = test_db
    role, programs = seed_role_and_programs(test_db)

    payload = {"preset": "read", "activity_ids": [programs[0].id], "resource_type": "activity"}
    res = client.post(f"/api/rbac/roles/{role.id}/apply-program-preset", json=payload)
    assert res.status_code == 200, res.text
    data = res.json()
    assert "applied_permission_ids" in data

    # verify RolePermissionResource entry exists for selected program
    db = Session()
    try:
        rows = db.query(RolePermissionResource).filter(RolePermissionResource.role_id == role.id, RolePermissionResource.resource_type == 'program', RolePermissionResource.resource_id == programs[0].id).all()
        assert len(rows) >= 1
    finally:
        db.close()


def test_apply_preset_to_all_programs_and_default(client, test_db, superadmin_user_override):
    Session = test_db
    role, programs = seed_role_and_programs(test_db)

    payload = {"preset": "read", "apply_to_existing": True, "resource_type": "activity"}
    res = client.post(f"/api/rbac/roles/{role.id}/apply-program-preset", json=payload)
    assert res.status_code == 200, res.text
    data = res.json()
    assert "applied_permission_ids" in data

    # verify default (resource_id is null) exists and per-program entries created
    db = Session()
    try:
        default_rows = db.query(RolePermissionResource).filter(RolePermissionResource.role_id == role.id, RolePermissionResource.resource_type == 'program', RolePermissionResource.resource_id.is_(None)).all()
        assert len(default_rows) >= 1
        for prog in programs:
            rows = db.query(RolePermissionResource).filter(RolePermissionResource.role_id == role.id, RolePermissionResource.resource_type == 'program', RolePermissionResource.resource_id == prog.id).all()
            assert len(rows) >= 1
    finally:
        db.close()
