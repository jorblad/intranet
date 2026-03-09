from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.api.routes import auth, schedules, taxonomy, users, ws, rbac, calendars, admin_messages
from app.core.config import ALLOWED_ORIGINS, STATIC_DIR
from app.db.init_db import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    # perform synchronous DB initialization at startup (kept simple here)
    init_db()
    yield


app = FastAPI(title="Intranet API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(users.router, prefix="/api")
app.include_router(taxonomy.router, prefix="/api")
app.include_router(schedules.router, prefix="/api")
app.include_router(ws.router, prefix="/api")
app.include_router(rbac.router, prefix="/api")
app.include_router(calendars.router, prefix="/api")
app.include_router(admin_messages.router, prefix="/api")


static_dir = Path(STATIC_DIR)

if static_dir.exists() and (static_dir / "index.html").is_file():
    index_file = static_dir / "index.html"

    @app.get("/")
    def serve_root():
        return FileResponse(index_file)

    @app.get("/{full_path:path}")
    def serve_spa(full_path: str):
        if full_path.startswith(("api", "oauth", "ws")):
            raise HTTPException(status_code=404, detail="Not Found")
        file_path = static_dir / full_path
        if file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(index_file)
else:
    @app.get("/")
    def root():
        return {
            "status": "ok",
            "message": "Frontend build not found. Build the Quasar app to enable SPA serving.",
        }
