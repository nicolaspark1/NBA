from __future__ import annotations

import logging
import random
import string
from datetime import date, datetime, time
from pathlib import Path
from typing import List
from zoneinfo import ZoneInfo

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.responses import JSONResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from .db import Base, SessionLocal, engine
from .models import (
    Group,
    GroupMember,
    Pick,
    PickResult,
    PickStatus,
    PlayerExpectedStat,
    PlayerGameStat,
    User,
)
from .nba import get_box_score_for_player, get_games_by_date, get_players_for_game
from .scoring import compute_expected_stats, score_pick
from .schemas import (
    GameOut,
    GroupCreate,
    GroupJoin,
    GroupMemberOut,
    GroupResponse,
    LeaderboardResponse,
    LeaderboardRow,
    PickCreate,
    PickResultOut,
    PickWithUser,
    PlayerOut,
    GroupOut,
    UserOut,
)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


logger = logging.getLogger("uvicorn.error")


@app.exception_handler(Exception)
async def _unhandled_exception_handler(request: Request, exc: Exception):
    # Render sometimes strips 500 bodies from upstream errors; always return JSON here
    # so the frontend can show the real error message.
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal Server Error",
            "error_type": exc.__class__.__name__,
            "error": str(exc),
        },
    )


@app.on_event("startup")
def _startup() -> None:
    # Simple schema creation for this project (no separate migration step required).
    Base.metadata.create_all(bind=engine)


@app.get("/healthz")
def healthz():
    return {"ok": True}


def generate_code() -> str:
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=6))


def enforce_pick_lock(pick_date: date):
    tz = ZoneInfo("America/Chicago")
    cutoff = datetime.combine(pick_date, time(18, 0), tzinfo=tz)
    now = datetime.now(tz)
    if now >= cutoff:
        raise HTTPException(status_code=400, detail="picks locked")


@app.post("/api/groups", response_model=GroupResponse)
def create_group(payload: GroupCreate, db: Session = Depends(get_db)):
    code = generate_code()
    while db.query(Group).filter_by(code=code).first():
        code = generate_code()

    group = Group(name=payload.group_name, code=code)
    user = User(display_name=payload.display_name)
    db.add_all([group, user])
    db.flush()
    membership = GroupMember(group_id=group.id, user_id=user.id)
    db.add(membership)
    db.commit()
    db.refresh(group)
    db.refresh(user)
    return GroupResponse(
        group=GroupOut(id=group.id, name=group.name, code=group.code),
        user=UserOut(id=user.id, display_name=user.display_name),
    )


@app.post("/api/groups/join", response_model=GroupResponse)
def join_group(payload: GroupJoin, db: Session = Depends(get_db)):
    group = db.query(Group).filter_by(code=payload.group_code.upper()).first()
    if not group:
        raise HTTPException(status_code=404, detail="group not found")
    user = User(display_name=payload.display_name)
    db.add(user)
    db.flush()
    membership = GroupMember(group_id=group.id, user_id=user.id)
    db.add(membership)
    db.commit()
    db.refresh(group)
    db.refresh(user)
    return GroupResponse(
        group=GroupOut(id=group.id, name=group.name, code=group.code),
        user=UserOut(id=user.id, display_name=user.display_name),
    )


@app.get("/api/groups/{code}/members", response_model=List[GroupMemberOut])
def list_members(code: str, db: Session = Depends(get_db)):
    group = db.query(Group).filter_by(code=code.upper()).first()
    if not group:
        raise HTTPException(status_code=404, detail="group not found")
    members = (
        db.query(User.id, User.display_name, GroupMember.joined_at)
        .join(GroupMember, GroupMember.user_id == User.id)
        .filter(GroupMember.group_id == group.id)
        .all()
    )
    return [
        GroupMemberOut(id=row.id, display_name=row.display_name, joined_at=row.joined_at)
        for row in members
    ]


@app.get("/api/nba/games", response_model=List[GameOut])
def list_games(date: str):
    games = get_games_by_date(date)
    return [GameOut(**game) for game in games]


@app.get("/api/nba/players", response_model=List[PlayerOut])
def list_players(date: str, query: str = ""):
    games = get_games_by_date(date)
    players = []
    for game in games:
        players.extend(get_players_for_game(game["game_id"]))
    if query:
        players = [p for p in players if query.lower() in p["player_name"].lower()]
    return [PlayerOut(**player) for player in players]


@app.post("/api/groups/{code}/picks", response_model=PickWithUser)
def create_pick(code: str, payload: PickCreate, db: Session = Depends(get_db)):
    group = db.query(Group).filter_by(code=code.upper()).first()
    if not group:
        raise HTTPException(status_code=404, detail="group not found")
    enforce_pick_lock(payload.date)
    existing = (
        db.query(Pick)
        .filter_by(group_id=group.id, user_id=payload.user_id, date=payload.date)
        .first()
    )
    if existing:
        raise HTTPException(status_code=400, detail="pick already exists")
    pick = Pick(
        group_id=group.id,
        user_id=payload.user_id,
        date=payload.date,
        player_id=payload.player_id,
        player_name=payload.player_name,
        status=PickStatus.picked,
    )
    db.add(pick)
    db.commit()
    db.refresh(pick)
    user = db.query(User).get(payload.user_id)
    return PickWithUser(
        id=pick.id,
        user_id=pick.user_id,
        user_name=user.display_name,
        player_name=pick.player_name,
        status=pick.status.value,
    )


@app.get("/api/groups/{code}/picks", response_model=List[PickWithUser])
def list_picks(code: str, date: str, db: Session = Depends(get_db)):
    group = db.query(Group).filter_by(code=code.upper()).first()
    if not group:
        raise HTTPException(status_code=404, detail="group not found")
    pick_date = datetime.strptime(date, "%Y-%m-%d").date()
    picks = (
        db.query(Pick, User.display_name)
        .join(User, User.id == Pick.user_id)
        .filter(Pick.group_id == group.id, Pick.date == pick_date)
        .all()
    )
    return [
        PickWithUser(
            id=pick.id,
            user_id=pick.user_id,
            user_name=user_name,
            player_name=pick.player_name,
            status=pick.status.value,
        )
        for pick, user_name in picks
    ]


@app.post("/api/groups/{code}/score", response_model=LeaderboardResponse)
def score_day(code: str, date: str, db: Session = Depends(get_db)):
    group = db.query(Group).filter_by(code=code.upper()).first()
    if not group:
        raise HTTPException(status_code=404, detail="group not found")
    pick_date = datetime.strptime(date, "%Y-%m-%d").date()
    picks = (
        db.query(Pick)
        .filter(Pick.group_id == group.id, Pick.date == pick_date)
        .all()
    )
    results: List[PickResultOut] = []
    for pick in picks:
        if pick.status == PickStatus.scored:
            if pick.result:
                results.append(
                    PickResultOut(
                        pick_id=pick.id,
                        score=pick.result.score,
                        breakdown=pick.result.breakdown_json,
                    )
                )
            continue
        actual = None
        if pick.game_id:
            stat = (
                db.query(PlayerGameStat)
                .filter_by(player_id=pick.player_id, game_id=pick.game_id)
                .first()
            )
            if stat:
                actual = {
                    "points": stat.points,
                    "assists": stat.assists,
                    "rebounds": stat.rebounds,
                    "steals": stat.steals,
                    "blocks": stat.blocks,
                    "turnovers": stat.turnovers,
                    "personal_fouls": stat.personal_fouls,
                    "minutes": stat.minutes,
                }
        if not actual:
            games = get_games_by_date(date)
            for game in games:
                stat = get_box_score_for_player(game["game_id"], pick.player_id)
                if stat:
                    pick.game_id = game["game_id"]
                    actual = stat
                    cached = PlayerGameStat(
                        date=pick_date,
                        player_id=pick.player_id,
                        game_id=game["game_id"],
                        points=stat["points"],
                        assists=stat["assists"],
                        rebounds=stat["rebounds"],
                        steals=stat["steals"],
                        blocks=stat["blocks"],
                        turnovers=stat["turnovers"],
                        personal_fouls=stat["personal_fouls"],
                        minutes=stat["minutes"],
                    )
                    db.add(cached)
                    break
        if not actual:
            continue
        expected = (
            db.query(PlayerExpectedStat)
            .filter_by(player_id=pick.player_id, date=pick_date)
            .first()
        )
        if not expected:
            expected = compute_expected_stats(pick.player_id, pick_date)
            db.add(expected)
            db.flush()
        scored = score_pick(actual, expected)
        pick.status = PickStatus.scored
        result = PickResult(
            pick_id=pick.id,
            score=scored["score"],
            breakdown_json={
                "expected": {
                    "points": expected.exp_points,
                    "assists": expected.exp_assists,
                    "rebounds": expected.exp_rebounds,
                    "steals": expected.exp_steals,
                    "blocks": expected.exp_blocks,
                    "turnovers": expected.exp_turnovers,
                    "personal_fouls": expected.exp_personal_fouls,
                },
                "actual": {k: actual[k] for k in scored["breakdown"]},
                "contributions": scored["breakdown"],
            },
        )
        db.add(result)
        db.commit()
        db.refresh(result)
        results.append(
            PickResultOut(
                pick_id=pick.id, score=result.score, breakdown=result.breakdown_json
            )
        )

    leaderboard = (
        db.query(User.id, User.display_name, func.coalesce(func.sum(PickResult.score), 0.0))
        .join(Pick, Pick.user_id == User.id)
        .join(PickResult, PickResult.pick_id == Pick.id)
        .filter(Pick.group_id == group.id, Pick.date == pick_date)
        .group_by(User.id)
        .order_by(func.sum(PickResult.score).desc())
        .all()
    )
    return LeaderboardResponse(
        leaderboard=[
            LeaderboardRow(user_id=row[0], user_name=row[1], score=row[2])
            for row in leaderboard
        ],
        picks_with_results=results,
    )


@app.get("/api/groups/{code}/leaderboard", response_model=List[LeaderboardRow])
def leaderboard(code: str, date: str, db: Session = Depends(get_db)):
    group = db.query(Group).filter_by(code=code.upper()).first()
    if not group:
        raise HTTPException(status_code=404, detail="group not found")
    pick_date = datetime.strptime(date, "%Y-%m-%d").date()
    rows = (
        db.query(User.id, User.display_name, func.coalesce(func.sum(PickResult.score), 0.0))
        .join(Pick, Pick.user_id == User.id)
        .join(PickResult, PickResult.pick_id == Pick.id)
        .filter(Pick.group_id == group.id, Pick.date == pick_date)
        .group_by(User.id)
        .order_by(func.sum(PickResult.score).desc())
        .all()
    )
    return [LeaderboardRow(user_id=row[0], user_name=row[1], score=row[2]) for row in rows]


@app.get("/api/groups/{code}/leaderboard/alltime", response_model=List[LeaderboardRow])
def leaderboard_all_time(code: str, db: Session = Depends(get_db)):
    group = db.query(Group).filter_by(code=code.upper()).first()
    if not group:
        raise HTTPException(status_code=404, detail="group not found")
    rows = (
        db.query(User.id, User.display_name, func.coalesce(func.sum(PickResult.score), 0.0))
        .join(Pick, Pick.user_id == User.id)
        .join(PickResult, PickResult.pick_id == Pick.id)
        .filter(Pick.group_id == group.id)
        .group_by(User.id)
        .order_by(func.sum(PickResult.score).desc())
        .all()
    )
    return [LeaderboardRow(user_id=row[0], user_name=row[1], score=row[2]) for row in rows]


# --- Frontend static serving (for Docker/Render) ---
#
# When we build the Vite app in Docker, we copy the output into `backend/app/static/`.
# If it exists, we serve it at `/` and keep all API routes under `/api`.
STATIC_DIR = Path(__file__).resolve().parent / "static"
INDEX_FILE = STATIC_DIR / "index.html"

if INDEX_FILE.is_file():
    _static_root = STATIC_DIR.resolve()

    @app.get("/{full_path:path}", include_in_schema=False)
    def serve_frontend(full_path: str):
        candidate = (STATIC_DIR / full_path).resolve()
        if candidate.is_file() and candidate.is_relative_to(_static_root):
            return FileResponse(candidate)
        return FileResponse(INDEX_FILE)
