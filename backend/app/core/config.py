import os
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]

DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{BACKEND_DIR / 'app.db'}")
SECRET_KEY = os.getenv("SECRET_KEY", "change-me")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))


def _parse_list(env_value: str | None) -> list[str]:
    if not env_value:
        return []
    return [v.strip() for v in env_value.split(",") if v.strip()]


# Primary CORS origins can be provided as a comma-separated list in ALLOWED_ORIGINS.
# If not provided, you may set FRONTEND_URL or FRONTEND_URLS (comma-separated)
# which will be used as the allowed origins. When nothing is provided, the
# default remains permissive to avoid breaking local dev setups.
_raw_origins = os.getenv("ALLOWED_ORIGINS", "")
ALLOWED_ORIGINS = _parse_list(_raw_origins)
if not ALLOWED_ORIGINS:
    frontend_env = os.getenv("FRONTEND_URLS", "") or os.getenv("FRONTEND_URL", "")
    ALLOWED_ORIGINS = _parse_list(frontend_env)
if not ALLOWED_ORIGINS:
    ALLOWED_ORIGINS = ["*"]


# Optional regex to match origins (example: '^https?://(.+\\.)?example\\.com$')
_raw_regex = os.getenv("ALLOWED_ORIGIN_REGEX", "")
ALLOWED_ORIGIN_REGEX = _raw_regex or None


def _parse_bool(val: str | None) -> bool:
    if val is None:
        return False
    return str(val).lower() in ("1", "true", "yes", "y")


# Whether to set Access-Control-Allow-Credentials. If you use cookies for auth
# across origins, set this to a truthy value (true/1/yes).
CORS_ALLOW_CREDENTIALS = _parse_bool(os.getenv("CORS_ALLOW_CREDENTIALS", "false"))


STATIC_DIR = os.getenv(
    "STATIC_DIR",
    str(BACKEND_DIR.parent / "intranet-frontend" / "dist" / "spa"),
)
