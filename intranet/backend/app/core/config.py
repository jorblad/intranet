import os
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]

DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{BACKEND_DIR / 'app.db'}")
SECRET_KEY = os.getenv("SECRET_KEY", "change-me")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))

_raw_origins = os.getenv("ALLOWED_ORIGINS", "")
ALLOWED_ORIGINS = [o.strip() for o in _raw_origins.split(",") if o.strip()]
if not ALLOWED_ORIGINS:
    ALLOWED_ORIGINS = ["*"]

STATIC_DIR = os.getenv(
    "STATIC_DIR",
    str(BACKEND_DIR.parent / "intranet-frontend" / "dist" / "spa"),
)
