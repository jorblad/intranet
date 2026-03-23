"""
Tests for the /health and /metrics endpoints.

These tests use an in-memory SQLite database and explicitly clear all
VALKEY_* / FRONTEND_* environment variables so that optional dependency
checks always report "not_configured", making the suite deterministic
regardless of the CI environment.
"""
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from app.main import app
from app.db.base import Base
import app.api.routes.health as health_module


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def clear_optional_env_vars(monkeypatch):
    """Remove all optional-service env vars so health checks are deterministic."""
    for var in (
        "VALKEY_URL",
        "VALKEY_HOST",
        "VALKEY_PORT",
        "FRONTEND_URL",
        "FRONTEND_HEALTH_URL",
    ):
        monkeypatch.delenv(var, raising=False)


@pytest.fixture(scope="function")
def sqlite_engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return engine


@pytest.fixture
def client(sqlite_engine):
    """TestClient that patches health_module.engine with the in-memory SQLite engine."""
    with patch.object(health_module, "engine", sqlite_engine):
        yield TestClient(app)


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


def test_health_frontend_not_configured(client):
    """When FRONTEND_HEALTH_URL and FRONTEND_URL are unset, frontend check is not_configured."""
    res = client.get("/health")
    assert res.status_code == 200
    frontend_check = res.json()["checks"].get("frontend", {})
    assert frontend_check.get("ok") is None


def test_health_valkey_not_configured(client):
    """When VALKEY_URL and VALKEY_HOST are unset, valkey check is not_configured."""
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

