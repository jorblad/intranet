 # Intranät för kyrkor

Detta projekt är ett schemaläggningssystem riktat mot församlingars ungdomsverksamhet. Målet är att kunna planera möten, tilldela ansvariga och generera delade och personliga kalenderflöden (ICS) som kan användas i Google Calendar, Apple Calendar m.fl.

Kort översikt
 - Backend: FastAPI (Python) med SQLAlchemy och Alembic för migreringar
 - Frontend: Vue 3 + Quasar (SPA)
 - Databas: PostgreSQL
 - Realtime sync: WebSockets (Orbit-like client adapter) för att synka ändringar mellan klienter
 - CI / CD: GitHub Actions bygger och publicerar Docker-images till GHCR (valfritt Docker Hub) och skapar en release

Arkitektur
 - `backend/` innehåller FastAPI-applikationen och Alembic-migrationer
 - `intranet-frontend/` innehåller Quasar/Vue-koden och en liten Orbit-adapter för lokal IndexedDB + WebSocket sync
 - `docker-compose.yml` (produktion) refererar till byggda images; `docker-compose.dev.yml` används för local development with bind mounts

Local utveckling
1. Starta alla service lokalt (dev):
```bash
docker compose -f docker-compose.dev.yml up --build
```
2. Backend: lyssnar på port 8000 i containern (mappar till 8200 i dev-compose i tidigare setup)
3. Frontend: Quasar dev-server på port 9000

Databas och migreringar
 - Kör Alembic-migreringar i backend-containern vid behov:
```bash
docker compose -f docker-compose.dev.yml exec backend alembic upgrade heads
```

CI / Release workflow
 - När en PR med label `major`, `minor` eller `patch` mergas, en GitHub Action beräknar nästa semver-tag, bygger och pushar Docker-image till GHCR, skapar en `release/<tag>`-gren med uppdaterad `docker-compose.yml` och öppnar en PR mot `main`. När status-checks passerar så auto-mergas PR:en.

Automatiska beroendeuppdateringar
 - Renovate är konfigurerat för att öppna PRs för major/ minor/patch uppdateringar; patch/minor automerges.

Contributing
 - Öppna PRs mot `main`; följ PR-mallar och ange semver-label (`major|minor|patch`) för release-bump automation.

License

[MIT](https://choosealicense.com/licenses/mit/)
