# Dev Environment Guide

This guide starts a full dev stack with FastAPI, Postgres, and the Quasar dev server.

## Prerequisites

- Docker Desktop
- Node.js 18+ (optional, only needed if you run the frontend outside Docker)

## One-command dev stack (Docker)

From the intranet folder:

```bash
cd intranet
docker compose -f docker-compose.dev.yml up --build
```

Services:

- Backend: http://localhost:8000
- Frontend: http://localhost:9000
- Postgres: localhost:5432

Default login:

- Username: admin
- Password: password

## Local (non-Docker) dev

### 1) Start Postgres

Use your local Postgres and create a DB named `intranet_db`.

### 2) Start backend

```bash
cd intranet/backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export DATABASE_URL=postgresql+psycopg2://intranet:intranet_password@localhost:5432/intranet_db
export SECRET_KEY=dev-secret
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 3) Start frontend

```bash
cd intranet/intranet-frontend
npm install
API_PROXY_TARGET=http://localhost:8000 npm run dev
```

The Quasar dev server proxies `/api`, `/oauth`, and `/ws` to the backend.

## Common tasks

- Rebuild database data (Docker):

```bash
docker compose -f docker-compose.dev.yml down -v
docker compose -f docker-compose.dev.yml up --build
```

- Backend logs:

```bash
docker compose -f docker-compose.dev.yml logs -f backend
```

## Notes

- The backend auto-creates tables and seed data on startup.
- For production-like static serving, build the frontend and use docker-compose.yml instead.
