import pytest

from app.main import app


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
