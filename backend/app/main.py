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
from nba_api.stats.static import players as nba_players
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from .db import Base, SessionLocal, engine
from .models import (
    EspnGameMeta,
    EspnScheduleCache,
    EspnTeamRosterCache,
    Group,
    GroupMember,
    Pick,
    PickResult,
    PickStatus,
    PlayerExpectedStat,
    PlayerGameStat,
    PlayerSportsbookLine,
    User,
)
from .nba import (
    get_box_score_for_player,
    get_games_by_date,
    get_player_name,
    get_players_for_game,
)
from .scoring import compute_expected_stats, score_pick
from .schemas import (
    GameOut,
    GameRostersResponse,
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
    PlayerProjectionResponse,
    RosterPlayerOut,
    TeamRosterOut,
    RecentGamesProjectionOut,
    SportsbookLinesOut,
    GroupOut,
    UserOut,
)
from .sportsbook import get_sportsbook_provider
from .espn import fetch_scoreboard, fetch_team_roster, parse_schedule_from_events
from .nba_static import find_nba_player_id_by_name

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


@app.get("/api/healthz")
def api_healthz():
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
        .order_by(GroupMember.joined_at.asc())
        .all()
    )
    return [
        GroupMemberOut(id=row.id, display_name=row.display_name, joined_at=row.joined_at)
        for row in members
    ]


@app.get("/api/groups/search", response_model=List[GroupOut])
def search_groups(query: str = "", limit: int = 10, db: Session = Depends(get_db)):
    q = query.strip()
    if not q:
        return []

    limit = max(1, min(int(limit), 25))
    pattern = f"%{q.lower()}%"

    groups = (
        db.query(Group)
        .filter(
            or_(
                func.lower(Group.name).like(pattern),
                func.lower(Group.code).like(pattern),
            )
        )
        .order_by(Group.created_at.desc())
        .limit(limit)
        .all()
    )
    return [GroupOut(id=g.id, name=g.name, code=g.code) for g in groups]


@app.get("/api/nba/games", response_model=List[GameOut])
def list_games(date: str, db: Session = Depends(get_db)):
    """
    Robust schedule provider:
    - Primary: ESPN public JSON scoreboard feed (server-side, no HTML scraping)
    - Cached in DB to avoid calling upstream on every page load
    """
    try:
        target_date = datetime.strptime(date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD.")

    now = datetime.utcnow()
    ttl_seconds = 10 * 60

    cached = db.query(EspnScheduleCache).filter_by(date=target_date).first()
    if cached and (now - cached.fetched_at).total_seconds() < ttl_seconds:
        games = cached.games_json if isinstance(cached.games_json, list) else []
        return [
            GameOut(
                game_id=str(g.get("game_id", "")),
                home_team=str(g.get("home_team", "")),
                away_team=str(g.get("away_team", "")),
                start_time=str(g.get("start_time", "")),
            )
            for g in games
            if isinstance(g, dict) and g.get("game_id")
        ]

    try:
        events = fetch_scoreboard(date)
        parsed = parse_schedule_from_events(events)
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"NBA schedule unavailable right now ({exc.__class__.__name__}). Try again shortly.",
        )

    if cached:
        cached.games_json = parsed
        cached.fetched_at = now
    else:
        db.add(EspnScheduleCache(date=target_date, games_json=parsed, fetched_at=now))

    # Store per-game metadata so /rosters can look up team ids from game_id alone.
    for g in parsed:
        if not isinstance(g, dict):
            continue
        gid = str(g.get("game_id") or "")
        if not gid:
            continue
        meta = db.query(EspnGameMeta).filter_by(game_id=gid).first()
        if meta:
            meta.date = target_date
            meta.start_time = str(g.get("start_time") or "")
            meta.home_team = str(g.get("home_team") or "")
            meta.away_team = str(g.get("away_team") or "")
            meta.home_team_id = str(g.get("home_team_id") or "")
            meta.away_team_id = str(g.get("away_team_id") or "")
            meta.fetched_at = now
        else:
            db.add(
                EspnGameMeta(
                    game_id=gid,
                    date=target_date,
                    start_time=str(g.get("start_time") or ""),
                    home_team=str(g.get("home_team") or ""),
                    away_team=str(g.get("away_team") or ""),
                    home_team_id=str(g.get("home_team_id") or ""),
                    away_team_id=str(g.get("away_team_id") or ""),
                    fetched_at=now,
                )
            )

    db.commit()

    return [
        GameOut(
            game_id=str(g.get("game_id", "")),
            home_team=str(g.get("home_team", "")),
            away_team=str(g.get("away_team", "")),
            start_time=str(g.get("start_time", "")),
        )
        for g in parsed
        if isinstance(g, dict) and g.get("game_id")
    ]


@app.get("/api/nba/players", response_model=List[PlayerOut])
def list_players(date: str, query: str = ""):
    games = get_games_by_date(date)
    players = []
    for game in games:
        players.extend(get_players_for_game(game["game_id"]))
    if query:
        players = [p for p in players if query.lower() in p["player_name"].lower()]
    return [PlayerOut(**player) for player in players]


@app.get("/api/nba/games/{game_id}/players", response_model=List[PlayerOut])
def list_players_for_game(game_id: str):
    players = get_players_for_game(game_id)
    return [PlayerOut(**p) for p in players]


@app.get("/api/nba/games/{game_id}/rosters", response_model=GameRostersResponse)
def game_rosters(game_id: str, db: Session = Depends(get_db)):
    """
    Rosters for both teams for a game.
    Uses ESPN team roster JSON (server-side) and maps player names to NBA ids when possible.
    """
    meta = db.query(EspnGameMeta).filter_by(game_id=game_id).first()
    if not meta:
        raise HTTPException(status_code=404, detail="game not found")

    now = datetime.utcnow()
    ttl_seconds = 6 * 60 * 60

    def load_team(team_id: str, fallback_label: str) -> TeamRosterOut:
        cached = db.query(EspnTeamRosterCache).filter_by(team_id=team_id).first()
        athletes = None
        team_name = ""
        team_abbr = ""

        if cached and (now - cached.fetched_at).total_seconds() < ttl_seconds:
            team_name = cached.team_name or ""
            team_abbr = cached.team_abbr or ""
            athletes = cached.roster_json if isinstance(cached.roster_json, list) else []
        else:
            try:
                team_name, team_abbr, athletes = fetch_team_roster(team_id)
            except Exception as exc:
                raise HTTPException(
                    status_code=503,
                    detail=f"Roster unavailable right now ({exc.__class__.__name__}). Try again shortly.",
                )

            if cached:
                cached.team_name = team_name
                cached.team_abbr = team_abbr
                cached.roster_json = athletes
                cached.fetched_at = now
            else:
                db.add(
                    EspnTeamRosterCache(
                        team_id=team_id,
                        team_name=team_name,
                        team_abbr=team_abbr,
                        roster_json=athletes,
                        fetched_at=now,
                    )
                )
            db.commit()

        players_out: List[RosterPlayerOut] = []
        for item in athletes if isinstance(athletes, list) else []:
            if not isinstance(item, dict):
                continue
            name = str(item.get("fullName") or item.get("displayName") or "").strip()
            if not name:
                continue
            pos = None
            if isinstance(item.get("position"), dict):
                pos = str(item["position"].get("abbreviation") or item["position"].get("name") or "")
                pos = pos or None
            jersey = str(item.get("jersey") or "").strip() or None
            nba_id = find_nba_player_id_by_name(name)
            # ESPN roster includes a stable athlete id; use it as a deterministic fallback so
            # the UI can keep players selectable even if nba_api name matching fails.
            fallback_id: int | None = None
            raw_espn_id = item.get("id")
            try:
                espn_id_int = int(raw_espn_id) if raw_espn_id is not None else None
                if espn_id_int:
                    # Offset to avoid colliding with NBA Stats ids.
                    fallback_id = 10_000_000_000 + espn_id_int
            except Exception:
                fallback_id = None
            players_out.append(
                RosterPlayerOut(
                    player_id=nba_id if nba_id is not None else fallback_id,
                    player_name=name,
                    position=pos,
                    jersey=jersey,
                )
            )

        return TeamRosterOut(
            team_id=team_id,
            team_name=team_name or fallback_label,
            team_abbr=team_abbr or "",
            players=players_out,
        )

    home_id = (meta.home_team_id or "").strip()
    away_id = (meta.away_team_id or "").strip()
    if not home_id or not away_id:
        raise HTTPException(status_code=503, detail="Roster unavailable (missing team ids)")

    home = load_team(home_id, meta.home_team or "")
    away = load_team(away_id, meta.away_team or "")

    return GameRostersResponse(
        game_id=game_id,
        date=meta.date,
        source="espn",
        last_updated=meta.fetched_at,
        home=home,
        away=away,
    )


@app.get("/api/nba/players/{player_id}/projection", response_model=PlayerProjectionResponse)
def player_projection(
    player_id: int,
    date: str,
    game_id: str | None = None,
    db: Session = Depends(get_db),
):
    target_date = datetime.strptime(date, "%Y-%m-%d").date()

    # Prefer player name from the requested game context if provided.
    player_name = None
    if game_id:
        try:
            game_players = get_players_for_game(game_id)
            for p in game_players:
                if int(p.get("player_id")) == int(player_id):
                    player_name = str(p.get("player_name"))
                    break
        except Exception:
            player_name = None
    if not player_name:
        player_name = get_player_name(player_id)

    recent: RecentGamesProjectionOut | None = None
    expected: PlayerExpectedStat | None = None
    # Only attempt NBA Stats projections for real NBA Stats player ids.
    if nba_players.find_player_by_id(int(player_id)):
        expected = (
            db.query(PlayerExpectedStat)
            .filter_by(player_id=player_id, date=target_date)
            .first()
        )
        if not expected:
            expected = compute_expected_stats(player_id, target_date)
            db.add(expected)
            db.commit()
            db.refresh(expected)

        recent = RecentGamesProjectionOut(
            n_games_used=expected.n_games_used,
            points=float(expected.exp_points),
            assists=float(expected.exp_assists),
            rebounds=float(expected.exp_rebounds),
            steals=float(expected.exp_steals),
            blocks=float(expected.exp_blocks),
            turnovers=float(expected.exp_turnovers),
            personal_fouls=float(expected.exp_personal_fouls),
        )

    sportsbook_out: SportsbookLinesOut | None = None
    source = "recent_games" if recent else "unavailable"
    last_updated = expected.computed_at if expected else datetime.utcnow()

    provider = get_sportsbook_provider()
    if provider:
        provider_name = getattr(provider, "provider_name", "sportsbook_provider")
        cached = (
            db.query(PlayerSportsbookLine)
            .filter_by(player_id=player_id, date=target_date, provider=provider_name)
            .first()
        )
        if cached and isinstance(cached.lines_json, dict) and cached.lines_json:
            sportsbook_out = SportsbookLinesOut(
                provider=provider_name,
                last_updated=cached.fetched_at,
                lines={k: float(v) for k, v in cached.lines_json.items()},
            )
            source = "sportsbook_provider"
            last_updated = cached.fetched_at
        else:
            try:
                result = provider.get_player_lines(
                    player_id=player_id,
                    player_name=player_name,
                    date_str=date,
                    game_id=game_id,
                )
            except Exception:
                result = None

            if result and result.lines:
                record = cached or PlayerSportsbookLine(
                    date=target_date,
                    game_id=game_id,
                    player_id=player_id,
                    player_name=player_name,
                    provider=provider_name,
                    lines_json={},
                )
                record.game_id = game_id
                record.player_name = player_name
                record.lines_json = result.lines
                record.fetched_at = result.last_updated
                db.add(record)
                db.commit()

                sportsbook_out = SportsbookLinesOut(
                    provider=provider_name,
                    last_updated=result.last_updated,
                    lines={k: float(v) for k, v in result.lines.items()},
                )
                source = "sportsbook_provider"
                last_updated = result.last_updated

    return PlayerProjectionResponse(
        player_id=player_id,
        player_name=player_name,
        date=target_date,
        game_id=game_id,
        source=source,
        last_updated=last_updated,
        recent_games=recent,
        sportsbook=sportsbook_out,
    )


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
