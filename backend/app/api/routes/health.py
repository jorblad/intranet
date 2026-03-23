from typing import Any
import os
import socket
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
        except Exception as e:  # pragma: no cover - network conditions vary
            checks["frontend"] = {"ok": False, "error": str(e)}
    else:
        checks["frontend"] = {"ok": None, "reason": "no_frontend_url_configured"}

    # Valkey check (optional): try to detect configured valkey service and test connectivity.
    valkey_url = os.getenv("VALKEY_URL")
    valkey_host = os.getenv("VALKEY_HOST")
    valkey_port = os.getenv("VALKEY_PORT")
    if valkey_url or valkey_host:
        try:
            # If a URL is provided and it's HTTP(S), try a GET.
            if valkey_url and (valkey_url.startswith("http://") or valkey_url.startswith("https://")):
                try:
                    r = requests.get(valkey_url, timeout=2)
                    checks["valkey"] = {"ok": r.status_code < 400, "status_code": r.status_code}
                except Exception as e:  # pragma: no cover - network variations
                    checks["valkey"] = {"ok": False, "error": str(e)}
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
                else:
                    # No valkey host info available — mark as not configured
                    checks["valkey"] = {"ok": None, "reason": "no_valkey_configured"}
        except Exception as e:
            checks["valkey"] = {"ok": False, "error": str(e)}
    else:
        checks["valkey"] = {"ok": None, "reason": "no_valkey_configured"}

    # overall_ok: only count checks that are actually configured (ok is not None).
    # all([]) returns True by design — if no optional checks are configured, only db matters.
    configured = [v["ok"] for v in checks.values() if v.get("ok") is not None]
    overall_ok = db_ok and all(configured)
    return overall_ok, checks


@router.get("/health")
def health() -> Any:
    """Health endpoint returning JSON for quick HTTP probes or human inspection."""
    overall_ok, checks = _perform_checks()
    status = "ok" if overall_ok else "degraded"
    return JSONResponse(status_code=200 if overall_ok else 503, content={"status": status, "checks": checks})


@router.get("/metrics")
def metrics() -> Response:
    """Prometheus metrics endpoint exposing process metrics only.

    Dependency health gauges are intentionally omitted here to avoid
    triggering DB queries and outbound network requests on every Prometheus
    scrape.  Use the /health endpoint for dependency status.
    """
    # Build a dedicated registry per scrape to avoid double-registration
    registry = CollectorRegistry()
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

    data = generate_latest(registry)
    return Response(content=data, media_type=CONTENT_TYPE_LATEST)
