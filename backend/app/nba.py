from __future__ import annotations

import logging
from datetime import datetime
import os
from typing import Dict, List

from nba_api.stats.endpoints import BoxScoreTraditionalV2, PlayerGameLog, ScoreboardV2
from nba_api.stats.static import players as nba_players

logger = logging.getLogger("uvicorn.error")

try:
    # Optional: not all nba_api versions expose this path the same way.
    from nba_api.library.http import NBAStatsHTTP  # type: ignore
except Exception:  # pragma: no cover
    NBAStatsHTTP = None  # type: ignore


_HEADERS_CONFIGURED = False


def _ensure_nba_stats_headers() -> None:
    """
    stats.nba.com often blocks non-browser clients (common on Render).
    nba_api uses NBAStatsHTTP.headers for requests; set browser-like defaults.
    """
    global _HEADERS_CONFIGURED
    if _HEADERS_CONFIGURED:
        return
    _HEADERS_CONFIGURED = True

    if NBAStatsHTTP is None or not hasattr(NBAStatsHTTP, "headers"):
        # Avoid crashing the app if nba_api internals differ; endpoints may still work.
        logger.warning("nba_api NBAStatsHTTP not available; skipping custom stats.nba.com headers")
        return

    user_agent = os.getenv(
        "NBA_API_USER_AGENT",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36",
    )
    try:
        NBAStatsHTTP.headers.update(  # type: ignore[union-attr]
            {
                "User-Agent": user_agent,
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "en-US,en;q=0.9",
                "Origin": "https://stats.nba.com",
                "Referer": "https://stats.nba.com/",
                "Connection": "keep-alive",
                "x-nba-stats-origin": "stats",
                "x-nba-stats-token": "true",
            }
        )
    except Exception:
        logger.warning("Failed to configure nba_api NBAStatsHTTP headers; continuing without custom headers")


def _normalize_scoreboard_date(date_str: str) -> str:
    """
    ScoreboardV2 expects MM/DD/YYYY.
    Our API accepts YYYY-MM-DD (from <input type="date">) and MM/DD/YYYY.
    """
    s = (date_str or "").strip()
    if not s:
        raise ValueError("date is required")
    if "-" in s:
        # YYYY-MM-DD
        return datetime.strptime(s, "%Y-%m-%d").strftime("%m/%d/%Y")
    # Assume already MM/DD/YYYY
    return s


def get_games_by_date(date_str: str) -> List[Dict[str, str]]:
    _ensure_nba_stats_headers()
    scoreboard_date = _normalize_scoreboard_date(date_str)
    scoreboard = ScoreboardV2(game_date=scoreboard_date, league_id="00", day_offset=0)
    games = scoreboard.game_header.get_dict()["data"]
    teams = scoreboard.line_score.get_dict()["data"]
    team_map = {}
    for team in teams:
        game_id = team[2]
        team_map.setdefault(game_id, {})
        if team[4] == "HOME":
            team_map[game_id]["home_team"] = team[5]
        else:
            team_map[game_id]["away_team"] = team[5]

    results = []
    for game in games:
        game_id = game[2]
        start_time = game[8]
        teams = team_map.get(game_id, {})
        results.append(
            {
                "game_id": game_id,
                "home_team": teams.get("home_team", ""),
                "away_team": teams.get("away_team", ""),
                "start_time": start_time,
            }
        )
    return results


def get_players_for_game(game_id: str) -> List[Dict[str, str]]:
    _ensure_nba_stats_headers()
    box = BoxScoreTraditionalV2(game_id=game_id)
    players = box.player_stats.get_dict()["data"]
    results = []
    for row in players:
        results.append(
            {
                "player_id": row[4],
                "player_name": row[5],
                "team": row[7],
                "game_id": game_id,
            }
        )
    return results


def get_box_score_for_player(game_id: str, player_id: int) -> Dict[str, float] | None:
    _ensure_nba_stats_headers()
    box = BoxScoreTraditionalV2(game_id=game_id)
    players = box.player_stats.get_dict()["data"]
    for row in players:
        if row[4] == player_id:
            return {
                "points": float(row[26] or 0),
                "assists": float(row[21] or 0),
                "rebounds": float(row[20] or 0),
                "steals": float(row[22] or 0),
                "blocks": float(row[23] or 0),
                "turnovers": float(row[24] or 0),
                "personal_fouls": float(row[25] or 0),
                "minutes": row[9],
            }
    return None


def get_recent_games(player_id: int, end_date: str, n_games: int) -> List[Dict[str, float]]:
    _ensure_nba_stats_headers()
    log = PlayerGameLog(player_id=player_id, date_from_nullable="", date_to_nullable=end_date)
    games = log.get_dict()["resultSets"][0]["rowSet"]
    results = []
    for row in games:
        game_date = datetime.strptime(row[3], "%b %d, %Y")
        if game_date.strftime("%Y-%m-%d") >= end_date:
            continue
        results.append(
            {
                "points": float(row[24] or 0),
                "assists": float(row[19] or 0),
                "rebounds": float(row[18] or 0),
                "steals": float(row[20] or 0),
                "blocks": float(row[21] or 0),
                "turnovers": float(row[22] or 0),
                "personal_fouls": float(row[23] or 0),
            }
        )
        if len(results) >= n_games:
            break
    return results


def get_player_name(player_id: int) -> str:
    info = nba_players.find_player_by_id(player_id)
    if info and isinstance(info, dict):
        name = info.get("full_name")
        if isinstance(name, str) and name.strip():
            return name.strip()
    return str(player_id)
