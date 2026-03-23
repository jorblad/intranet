from typing import Any
import os
import socket
import importlib
import urllib.parse
import requests

from fastapi import APIRouter
from fastapi.responses import JSONResponse, Response
from sqlalchemy import text

from prometheus_client import CollectorRegistry, Gauge, generate_latest, CONTENT_TYPE_LATEST
try:
    # Prefer top-level collectors when available
    from prometheus_client import ProcessCollector, PlatformCollector
except Exception:
    ProcessCollector = None
    PlatformCollector = None
try:
    from prometheus_client import GCCollector
except Exception:
    GCCollector = None

from app.db.session import engine

router = APIRouter()


def _tcp_connect_ok(host: str, port: int, timeout: float = 2.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception:
        return False


def _perform_checks() -> tuple[bool, dict[str, Any]]:
    checks: dict[str, Any] = {}

    # Database check
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        checks["database"] = {"ok": True}
        db_ok = True
    except Exception as e:  # pragma: no cover - best-effort runtime check
        checks["database"] = {"ok": False, "error": str(e)}
        db_ok = False

    # Frontend check (optional)
    frontend_url = os.getenv("FRONTEND_HEALTH_URL") or os.getenv("FRONTEND_URL")
    if frontend_url:
        try:
            r = requests.get(frontend_url, timeout=2)
            checks["frontend"] = {"ok": r.status_code < 400, "status_code": r.status_code}
            frontend_ok = r.status_code < 400
        except Exception as e:  # pragma: no cover - network conditions vary
            checks["frontend"] = {"ok": False, "error": str(e)}
            frontend_ok = False
    else:
        checks["frontend"] = {"ok": None, "reason": "no_frontend_url_configured"}
        frontend_ok = True

    # Valkey check (optional): try to detect configured valkey service and test connectivity.
    valkey_url = os.getenv("VALKEY_URL")
    valkey_host = os.getenv("VALKEY_HOST")
    valkey_port = os.getenv("VALKEY_PORT")
    valkey_ok = True
    if valkey_url or valkey_host:
        try:
            # If a URL is provided and it's HTTP(S), try a GET.
            if valkey_url and (valkey_url.startswith("http://") or valkey_url.startswith("https://")):
                try:
                    r = requests.get(valkey_url, timeout=2)
                    valkey_ok = r.status_code < 400
                    checks["valkey"] = {"ok": valkey_ok, "status_code": r.status_code}
                except Exception as e:  # pragma: no cover - network variations
                    checks["valkey"] = {"ok": False, "error": str(e)}
                    valkey_ok = False
            else:
                # Try to extract host/port from URL or use VALKEY_HOST/VALKEY_PORT.
                host = None
                port = None
                if valkey_url:
                    try:
                        parsed = urllib.parse.urlparse(valkey_url)
                        host = parsed.hostname
                        port = parsed.port
                    except Exception:
                        host = None
                if not host and valkey_host:
                    host = valkey_host
                if not port:
                    try:
                        port = int(valkey_port) if valkey_port else 6379
                    except Exception:
                        port = 6379

                if host:
                    ok = _tcp_connect_ok(host, port, timeout=2)
                    checks["valkey"] = {"ok": ok, "host": host, "port": port}
                    valkey_ok = ok
                else:
                    # No valkey host info available — mark as not configured
                    checks["valkey"] = {"ok": None, "reason": "no_valkey_configured"}
                    valkey_ok = True
        except Exception as e:
            checks["valkey"] = {"ok": False, "error": str(e)}
            valkey_ok = False
    else:
        checks["valkey"] = {"ok": None, "reason": "no_valkey_configured"}
        valkey_ok = True

    overall_ok = db_ok and frontend_ok and valkey_ok
    return overall_ok, checks


@router.get("/health")
def health() -> Any:
    """Health endpoint returning JSON for quick HTTP probes or human inspection."""
    overall_ok, checks = _perform_checks()
    status = "ok" if overall_ok else "degraded"
    return JSONResponse(status_code=200 if overall_ok else 503, content={"status": status, "checks": checks})


@router.get("/metrics")
def metrics() -> Response:
    """Prometheus metrics endpoint exposing basic health gauges and process metrics."""
    overall_ok, checks = _perform_checks()

    # Build a dedicated registry per scrape so we avoid double-registration problems
    registry = CollectorRegistry()
    # register standard process/platform collectors for useful defaults
    # Register standard collectors where available
    try:
        if ProcessCollector is not None:
            ProcessCollector(registry=registry)
    except Exception:
        pass
    try:
        if PlatformCollector is not None:
            PlatformCollector(registry=registry)
    except Exception:
        pass
    try:
        if GCCollector is not None:
            GCCollector(registry=registry)
    except Exception:
        pass

    # Health gauges
    Gauge("intranet_health_up", "Overall intranet health (1=up,0=down)", registry=registry).set(1 if overall_ok else 0)
    db_ok = bool(checks.get("database", {}).get("ok"))
    fv = checks.get("frontend", {}).get("ok")
    frontend_ok = True if fv is None else bool(fv)
    valkey_ok = True if checks.get("valkey", {}).get("ok") is None else bool(checks.get("valkey", {}).get("ok"))

    Gauge("intranet_database_up", "Database connectivity (1=up,0=down)", registry=registry).set(1 if db_ok else 0)
    Gauge("intranet_frontend_up", "Frontend reachable (1=up,0=down, -1=not_configured)", registry=registry).set(1 if frontend_ok is True else 0 if frontend_ok is False else -1)
    Gauge("intranet_valkey_up", "Valkey reachable (1=up,0=down, -1=not_configured)", registry=registry).set(1 if valkey_ok is True else 0 if valkey_ok is False else -1)

    data = generate_latest(registry)
    return Response(content=data, media_type=CONTENT_TYPE_LATEST)
