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

### Frontend
```bash
cd frontend
npm install
npm run dev
```

The UI runs on `http://localhost:5173`.

## Usage
1. Create a group with your display name and a group name.
2. Share the group code with friends so they can join.
3. Pick one player per date. Picks lock at 6:00pm America/Chicago.
4. Use “Score Day” to compute results and see leaderboards.

## API Overview
- `POST /api/groups`
- `POST /api/groups/join`
- `GET /api/groups/{code}/members`
- `GET /api/nba/games?date=YYYY-MM-DD`
- `GET /api/nba/players?date=YYYY-MM-DD&query=...`
- `POST /api/groups/{code}/picks`
- `GET /api/groups/{code}/picks?date=YYYY-MM-DD`
- `POST /api/groups/{code}/score?date=YYYY-MM-DD`
- `GET /api/groups/{code}/leaderboard?date=YYYY-MM-DD`
- `GET /api/groups/{code}/leaderboard/alltime`
