"""
Tests for the /health and /metrics endpoints.

These tests use an in-memory SQLite database so no external services are
required.  Frontend URL and Valkey environment variables are intentionally
left unset, so those checks report "not_configured".
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.db.base import Base
from app.db.session import get_db


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="function")
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


# ---------------------------------------------------------------------------
# Route registration
# ---------------------------------------------------------------------------


def test_health_route_registered():
    paths = [r.path for r in app.router.routes]
    assert "/health" in paths


def test_metrics_route_registered():
    paths = [r.path for r in app.router.routes]
    assert "/metrics" in paths


# ---------------------------------------------------------------------------
# /health
# ---------------------------------------------------------------------------


def test_health_returns_200_with_sqlite_db(client):
    """/health should return 200 when DB is reachable (sqlite in tests)."""
    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert data["checks"]["database"]["ok"] is True


def test_health_response_structure(client):
    """/health response contains 'status' and 'checks' keys."""
    res = client.get("/health")
    assert "status" in res.json()
    assert "checks" in res.json()


def test_health_frontend_not_configured(client, monkeypatch):
    """When FRONTEND_HEALTH_URL and FRONTEND_URL are unset, frontend check is not_configured."""
    monkeypatch.delenv("FRONTEND_HEALTH_URL", raising=False)
    monkeypatch.delenv("FRONTEND_URL", raising=False)

    res = client.get("/health")
    assert res.status_code == 200
    frontend_check = res.json()["checks"].get("frontend", {})
    assert frontend_check.get("ok") is None


def test_health_valkey_not_configured(client, monkeypatch):
    """When VALKEY_URL and VALKEY_HOST are unset, valkey check is not_configured."""
    monkeypatch.delenv("VALKEY_URL", raising=False)
    monkeypatch.delenv("VALKEY_HOST", raising=False)

    res = client.get("/health")
    assert res.status_code == 200
    valkey_check = res.json()["checks"].get("valkey", {})
    assert valkey_check.get("ok") is None


# ---------------------------------------------------------------------------
# /metrics
# ---------------------------------------------------------------------------


def test_metrics_returns_200(client):
    """/metrics should return 200."""
    res = client.get("/metrics")
    assert res.status_code == 200


def test_metrics_content_type_is_prometheus(client):
    """/metrics content-type should be the Prometheus text format."""
    res = client.get("/metrics")
    assert "text/plain" in res.headers["content-type"]


def test_metrics_does_not_include_health_gauges(client):
    """/metrics should not include intranet dependency gauges (no per-scrape DB queries)."""
    res = client.get("/metrics")
    body = res.text
    assert "intranet_database_up" not in body
    assert "intranet_frontend_up" not in body
    assert "intranet_valkey_up" not in body
