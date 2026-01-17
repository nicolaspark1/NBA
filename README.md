# Beat the Line (NBA Over/Under Performer Group Game)

MVP web app where friends create a group, pick one NBA player per day, and score points based on performance versus expected stats (last N games average).

## Stack
- Backend: FastAPI + SQLAlchemy (SQLite)
- Frontend: React + Vite + TypeScript
- Data: `nba_api`

## Setup

### Backend
```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

The API runs on `http://localhost:8000`.

Optional (dev/tests only):
```bash
pip install -r requirements-dev.txt
```

### Frontend
```bash
cd frontend
npm install
npm run dev
```

The UI runs on `http://localhost:5173`.
API requests to `/api` are proxied to `http://localhost:8000` by Vite during development.

## Deploy on Render (recommended: single Docker service)

This repo includes a root `Dockerfile` that builds the Vite frontend and serves it from the FastAPI backend.

- **Frontend**: served at `/`
- **API**: served at `/api`

### Steps
- Push this repo to GitHub/GitLab.
- In Render: **New → Web Service**
- Connect your repo
- Environment: **Docker**
- Deploy

### Persistence (pick one)
- **Postgres (recommended)**:
  - Create a Render Postgres database
  - Set the backend env var **`DATABASE_URL`** to the database connection string
- **SQLite on a persistent disk**:
  - Add a Render Disk (e.g. mount at `/var/data`)
  - Set **`SQLITE_PATH=/var/data/nba.db`**

### Optional env vars
- `WEB_CONCURRENCY`: number of Gunicorn workers (default `1`; keep `1` if using SQLite, bump to `2+` if using Postgres)

## Deploy on Render (alternative: separate frontend + backend)
If you deploy the frontend as a Render **Static Site** and the backend as a Render **Web Service**, set this on the frontend service (build-time env var):
- `VITE_API_BASE=https://YOUR-BACKEND.onrender.com/api` (must include the trailing `/api`)

## Usage
1. Create a group with your display name and a group name.
2. Share the group code with friends so they can join.
3. Pick one player per date. Picks lock at 6:00pm America/Chicago.
4. Use “Score Day” to compute results and see leaderboards.

## API Overview
- `POST /api/groups`
- `POST /api/groups/join`
- `GET /api/groups/{code}/members`
- `GET /api/groups/search?query=...&limit=...`
- `GET /api/nba/games?date=YYYY-MM-DD`
- `GET /api/nba/games/{game_id}/players`
- `GET /api/nba/games/{game_id}/rosters`
- `GET /api/nba/players?date=YYYY-MM-DD&query=...` (legacy convenience endpoint)
- `GET /api/nba/players/{player_id}/projection?date=YYYY-MM-DD&game_id=...`
- `POST /api/groups/{code}/picks`
- `GET /api/groups/{code}/picks?date=YYYY-MM-DD`
- `POST /api/groups/{code}/score?date=YYYY-MM-DD`
- `GET /api/groups/{code}/leaderboard?date=YYYY-MM-DD`
- `GET /api/groups/{code}/leaderboard/alltime`

## Optional sportsbook lines (no scraping)
By default, projections prefer **sportsbook player prop lines** (separate **Points / Rebounds / Assists**).

You can configure a provider:
- **DraftKings (recommended)**: set **`DRAFTKINGS_PROPS_URL`** to a DraftKings **JSON** endpoint (no HTML scraping).
- **Odds API**: set **`ODDS_API_KEY`** (plan/markets must include NBA player props).

Optional provider selector:
- `PROJECTIONS_PROVIDER=draftkings` (or `odds_api`)

Caching:
- `SPORTSBOOK_CACHE_TTL_SECONDS` (default `1800`)

Optional fallback (disabled by default because `nba_api` can timeout / be blocked):
- `ENABLE_RECENT_GAMES_FALLBACK=1` to allow falling back to last-N-games averages when sportsbook lines are unavailable.

## NBA data providers (production)
- **Schedule + rosters**: uses ESPN public JSON endpoints server-side (no HTML scraping) and caches results in the DB.
- **Recent-games projections**: uses `nba_api` (calls `stats.nba.com`), which can be blocked in some hosting environments.

If you see projection errors in production, you can set:
- `NBA_API_USER_AGENT`: override the User-Agent sent to `stats.nba.com` (defaults to a modern Chrome UA).
