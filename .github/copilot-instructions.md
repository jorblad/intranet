# Copilot Instructions

This repository contains an intranet scheduling system for church youth organizations. It is a full-stack application with:

- **Backend**: FastAPI (Python 3.14) with SQLAlchemy 2.0 and Alembic migrations
- **Frontend**: Vue 3 + Quasar (SPA), bundled with Vite / `@quasar/app-vite`
- **Database**: PostgreSQL in production; SQLite is used in CI tests
- **Real-time sync**: WebSockets with an Orbit-like client adapter (IndexedDB + WebSocket)
- **CI/CD**: GitHub Actions builds and publishes Docker images to GHCR; releases are automated by [release-please](https://github.com/googleapis/release-please) from Conventional Commit messages (no manual labels needed)

## Repository layout

```
backend/          FastAPI application, Alembic migrations, pytest tests
intranet-frontend/  Quasar/Vue SPA, Vitest unit tests
docker-compose.yml          Production compose file
docker-compose.dev.yml      Development compose file (bind mounts, hot reload)
```

## Development

Start the full dev stack with:

```bash
docker compose -f docker-compose.dev.yml up --build
```

- Backend: http://localhost:8200
- Frontend: http://localhost:9000
- Admin login: username `admin` (configurable via `ADMIN_USERNAME`), password from `ADMIN_PASSWORD`; if unset, a random temporary password is generated on first run and printed to the backend logs.

Run Alembic migrations inside the backend container when needed:

```bash
docker compose -f docker-compose.dev.yml exec backend alembic upgrade heads
```

## Backend conventions (Python)

- **Python version**: 3.14
- **Framework**: FastAPI; routers live in `backend/app/api/routes/`
- **ORM**: SQLAlchemy 2.0 (use `Session` from `sqlalchemy.orm`). Compare nullable columns with `.is_(None)` / `.isnot(None)`.
- **Schemas**: Pydantic v2 in `backend/app/schemas/`
- **CRUD helpers**: `backend/app/crud/`; add new CRUD modules there
- **Models**: `backend/app/models/`
- **Logging**: define `logger = logging.getLogger(__name__)` at module level; never use the root `logging` module directly
- **DB seeding**: use `Session.begin_nested()` savepoints for default-data inserts to avoid rolling back the outer transaction on `IntegrityError`
- **RBAC**: `is_superadmin(user)` returns `True` only when the user has a role named `superadmin` with `role.is_global == True`
- **Tests**: use `pytest` + `httpx`; run with `pytest -q` from `backend/`. Tests use SQLite (in CI: `DATABASE_URL=sqlite:///./backend/test_app.db`; when running locally from `backend/`, typically `DATABASE_URL=sqlite:///./test_app.db` as shown below)
- **Linting/formatting**: no dedicated Python linter is configured; keep style consistent with the surrounding code

### Running backend tests

```bash
cd backend
PYTHONPATH=. DATABASE_URL=sqlite:///./test_app.db SECRET_KEY=test-secret pytest -q
```

## Frontend conventions (JavaScript / Vue)

- **Node version**: 24
- **Framework**: Vue 3 (Composition API preferred) + Quasar 2
- **Bundler**: `@quasar/app-vite` (Vite 8)
- **State / data sync**: Orbit.js (`@orbit/memory`, `@orbit/indexeddb`) with a custom WebSocket adapter
- **API calls**: Axios-based service modules in `intranet-frontend/src/services/`. The API base URL defaults to `/api` but can be overridden via `window.__API_PROXY_TARGET__` at runtime
- **i18n**: `vue-i18n`; message bundles are in `intranet-frontend/src/i18n/`; both full locale keys (`en-US`, `sv-SE`) and short keys (`en`, `sv`) are exported
- **Markdown**: use `intranet-frontend/src/utils/markdown.js` (`sanitizeUrl`, `renderToHtml`) for any markdown rendering; do **not** bypass DOMPurify sanitization
- **Linting**: ESLint with `plugin:vue/vue3-essential` + `prettier`; run `npm run lint` from `intranet-frontend/`
- **Unit tests**: Vitest; run `npm test` from `intranet-frontend/`
- **Build**: `npm run build` (Quasar build → `dist/spa`)

### Running frontend checks

```bash
cd intranet-frontend
npm run lint
npm test
npm run build
```

## CI

- **Backend tests** run on every PR and push to `main` (Python 3.14, SQLite)
- **Frontend build** runs after backend tests pass (Node 24, `npm ci && npm run build`)

## Releases & Semantic Versioning (release-please)

Releases are automated with [release-please](https://github.com/googleapis/release-please), which is **driven entirely by Conventional Commit messages**. Follow these rules so releases and version bumps happen correctly:

- Every PR merged to `main` must use a Conventional Commit message (or be squashed with one). The commit type determines the SemVer bump:
  - `fix:` → PATCH release
  - `feat:` → MINOR release
  - `feat!:` or a `BREAKING CHANGE:` footer → MAJOR release
  - `chore:`, `docs:`, `ci:`, `refactor:`, `test:`, `style:` → no release (use these for changes that should not trigger a release, e.g. CI/config changes)
- Use a scope where helpful, e.g. `fix(deps):`, `feat(auth):`.
- release-please automatically opens a `chore(main): release X.Y.Z` PR that summarizes the pending changes. **Merge that PR** to cut the release (it creates the Git tag + GitHub release). Never create releases or tags manually.
- Merging the release PR triggers the `publish` job, which builds and pushes the `intranet-backend` and `intranet-frontend` Docker images to GHCR (and Docker Hub if credentials are configured), tagged with the release version and `latest`.
- Do **not** edit the release PR title/body — it is generated.
- Renovate is configured to emit Conventional Commit messages (`fix(deps)`, `feat(deps)`, `feat(deps)!` with a `BREAKING CHANGE` footer) so dependency updates drive the correct SemVer bump automatically. Major dependency updates are not auto-merged and require manual review.

## Docker / deployment

- `docker-compose.yml` references pre-built images; update image tags there for production deploys
- The production Nginx image uses `docker-entrypoint.sh` to generate `runtime-config.js` (sets `window.__API_PROXY_TARGET__`) before serving the SPA
- Key deployment environment variables: `ALLOWED_ORIGINS`, `FRONTEND_URL`, `ALLOWED_ORIGIN_REGEX`, `CORS_ALLOW_CREDENTIALS`, `STATIC_DIR`, `DATABASE_URL`, `SECRET_KEY`, `VALKEY_HOST`, `VALKEY_PORT`, `BACKEND_URL`, `ADMIN_USERNAME`, `ADMIN_PASSWORD`
