import pytest
from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.db.base import Base
from app.db.session import get_db
from app.api.routes.auth import get_current_user


# ---------------------------------------------------------------------------
# Shared fixtures for request-level permission tests
# ---------------------------------------------------------------------------

@pytest.fixture
def perm_test_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
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
def perm_client(perm_test_db):
    return TestClient(app)


@pytest.fixture
def superadmin_override():
    user = SimpleNamespace(
        organization_roles=[
            SimpleNamespace(role=SimpleNamespace(name="superadmin", is_global=True))
        ]
    )
    app.dependency_overrides[get_current_user] = lambda: user
    yield
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def regular_user_override():
    user = SimpleNamespace(organization_roles=[])
    app.dependency_overrides[get_current_user] = lambda: user
    yield
    app.dependency_overrides.pop(get_current_user, None)


# ---------------------------------------------------------------------------
# Existing tests
# ---------------------------------------------------------------------------

def test_apply_program_preset_route_exists():
    paths = [r.path for r in app.router.routes]
    assert "/api/rbac/roles/{role_id}/apply-program-preset" in paths


def test_init_db_seeds_default_permissions():
    """init_db() must create the four standard Permission rows on a fresh database."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    import app.db.init_db as init_db_module
    from app.db.base import Base
    from app.models import Permission

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)

    # Patch the module-level names used inside init_db()
    original_session_local = init_db_module.SessionLocal
    original_engine = init_db_module.engine
    init_db_module.SessionLocal = TestingSessionLocal
    init_db_module.engine = engine

    try:
        init_db_module.init_db()
        db = TestingSessionLocal()
        try:
            codenames = {p.codename for p in db.query(Permission).all()}
            for expected_codename, _ in init_db_module.DEFAULT_PERMISSIONS:
                assert expected_codename in codenames, (
                    f"Expected permission '{expected_codename}' to be seeded by init_db()"
                )
        finally:
            db.close()
    finally:
        init_db_module.SessionLocal = original_session_local
        init_db_module.engine = original_engine


def test_init_db_does_not_reseed_permissions_after_admin_deletes_all():
    """init_db() must not resurrect permissions on a restart if an admin deleted them all.

    Scenario: init_db() ran once (fresh install → roles + permissions seeded),
    then an admin deleted every Permission row.  On the next startup init_db()
    must leave the permissions table empty.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    import app.db.init_db as init_db_module
    from app.db.base import Base
    from app.models import Permission

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)

    original_session_local = init_db_module.SessionLocal
    original_engine = init_db_module.engine
    init_db_module.SessionLocal = TestingSessionLocal
    init_db_module.engine = engine

    try:
        # First run: fresh install seeds roles + permissions
        init_db_module.init_db()

        # Simulate admin deleting all permissions
        db = TestingSessionLocal()
        try:
            db.query(Permission).delete()
            db.commit()
            assert db.query(Permission).count() == 0, "Setup: all permissions should be deleted"
        finally:
            db.close()

        # Second run: restart — permissions must NOT be reseeded
        init_db_module.init_db()

        db = TestingSessionLocal()
        try:
            count = db.query(Permission).count()
            assert count == 0, (
                f"init_db() must not reseed permissions on restart after admin deleted them; "
                f"found {count} permission(s)"
            )
        finally:
            db.close()
    finally:
        init_db_module.SessionLocal = original_session_local
        init_db_module.engine = original_engine

def test_init_db_does_not_reseed_permissions_after_admin_deletes_role_and_permissions():
    """init_db() must not reseed permissions when a role was re-created on restart.

    Scenario: init_db() ran once (fresh install → roles + permissions seeded),
    then an admin deleted a default role (e.g. 'member') AND all permissions.
    On the next startup init_db() will re-insert the missing 'member' role, but
    must still leave the permissions table empty.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    import app.db.init_db as init_db_module
    from app.db.base import Base
    from app.models import Permission, Role

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)

    original_session_local = init_db_module.SessionLocal
    original_engine = init_db_module.engine
    init_db_module.SessionLocal = TestingSessionLocal
    init_db_module.engine = engine

    try:
        # First run: fresh install seeds roles + permissions
        init_db_module.init_db()

        # Admin deletes the 'member' role and all permissions
        db = TestingSessionLocal()
        try:
            db.query(Permission).delete()
            db.query(Role).filter(Role.name == "member").delete()
            db.commit()
            assert db.query(Permission).count() == 0, "Setup: all permissions should be deleted"
            assert db.query(Role).filter(Role.name == "member").first() is None, (
                "Setup: 'member' role should be deleted"
            )
        finally:
            db.close()

        # Second run: restart re-creates 'member' role but must NOT reseed permissions
        init_db_module.init_db()

        db = TestingSessionLocal()
        try:
            perm_count = db.query(Permission).count()
            assert perm_count == 0, (
                f"init_db() must not reseed permissions when a missing role is re-created; "
                f"found {perm_count} permission(s)"
            )
        finally:
            db.close()
    finally:
        init_db_module.SessionLocal = original_session_local
        init_db_module.engine = original_engine


def test_init_db_does_not_reseed_permissions_after_admin_deletes_users_and_permissions():
    """init_db() must not reseed permissions when the last user AND all permissions were deleted.

    Scenario: init_db() ran once (fresh install → admin user + roles + permissions seeded),
    then an admin deleted all users AND all permissions.  On the next startup roles still
    exist, so previously_initialized must be True and no permissions must be reseeded.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    import app.db.init_db as init_db_module
    from app.db.base import Base
    from app.models import Permission, User

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)

    original_session_local = init_db_module.SessionLocal
    original_engine = init_db_module.engine
    init_db_module.SessionLocal = TestingSessionLocal
    init_db_module.engine = engine

    try:
        # First run: fresh install seeds admin user, roles + permissions
        init_db_module.init_db()

        # Admin deletes all users AND all permissions (roles still remain)
        db = TestingSessionLocal()
        try:
            db.query(Permission).delete()
            db.query(User).delete()
            db.commit()
            assert db.query(Permission).count() == 0, "Setup: all permissions should be deleted"
            assert db.query(User).count() == 0, "Setup: all users should be deleted"
        finally:
            db.close()

        # Second run: restart — roles still exist → previously_initialized=True
        # → permissions must NOT be reseeded even though users are gone
        init_db_module.init_db()

        db = TestingSessionLocal()
        try:
            perm_count = db.query(Permission).count()
            assert perm_count == 0, (
                f"init_db() must not reseed permissions when last user was deleted; "
                f"found {perm_count} permission(s)"
            )
        finally:
            db.close()
    finally:
        init_db_module.SessionLocal = original_session_local
        init_db_module.engine = original_engine


def test_create_permission_as_superadmin(perm_client, perm_test_db, superadmin_override):
    """Superadmin can create a new permission via POST /rbac/permissions."""
    res = perm_client.post(
        "/api/rbac/permissions",
        json={"codename": "custom.action", "description": "A custom permission"},
    )
    assert res.status_code == 201, res.text
    data = res.json()
    assert data["codename"] == "custom.action"
    assert data["description"] == "A custom permission"
    assert "id" in data


def test_create_permission_requires_superadmin(perm_client, perm_test_db, regular_user_override):
    """Non-superadmin user must receive 403 when attempting to create a permission."""
    res = perm_client.post(
        "/api/rbac/permissions",
        json={"codename": "should.fail", "description": "Should not be created"},
    )
    assert res.status_code == 403, res.text
