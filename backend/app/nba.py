from __future__ import annotations

import os
from datetime import datetime
from typing import Dict, List

import requests
from nba_api.stats.endpoints import BoxScoreTraditionalV2, PlayerGameLog, ScoreboardV2
from nba_api.stats.static import players as nba_players

def _nba_headers() -> dict:
    """
    stats.nba.com often blocks non-browser clients (common on Render).
    Instead of relying on NBAStatsHTTP internals (which vary across nba_api versions),
    we pass headers directly into each endpoint call.
    """
    user_agent = os.getenv(
        "NBA_API_USER_AGENT",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36",
    )
    return {
        "User-Agent": user_agent,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Origin": "https://stats.nba.com",
        "Referer": "https://stats.nba.com/",
        "Connection": "keep-alive",
        "x-nba-stats-origin": "stats",
        "x-nba-stats-token": "true",
    }


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


def _normalize_yyyymmdd(date_str: str) -> str:
    s = (date_str or "").strip()
    if "-" in s:
        return datetime.strptime(s, "%Y-%m-%d").strftime("%Y%m%d")
    if "/" in s:
        return datetime.strptime(s, "%m/%d/%Y").strftime("%Y%m%d")
    # Assume already YYYYMMDD
    return s


def _get_games_by_date_espn(date_str: str) -> List[Dict[str, str]]:
    """
    Fallback schedule provider using ESPN's JSON scoreboard feed.
    This is NOT scraping HTML and avoids CORS (server-side request).
    """
    yyyymmdd = _normalize_yyyymmdd(date_str)
    url = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard"
    resp = requests.get(url, params={"dates": yyyymmdd}, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    events = data.get("events", []) if isinstance(data, dict) else []
    results: List[Dict[str, str]] = []
    for event in events if isinstance(events, list) else []:
        if not isinstance(event, dict):
            continue
        game_id = str(event.get("id") or "")
        start_time = str(event.get("date") or "")
        competitions = event.get("competitions")
        comp0 = competitions[0] if isinstance(competitions, list) and competitions else None
        competitors = comp0.get("competitors") if isinstance(comp0, dict) else None
        home_team = ""
        away_team = ""
        for c in competitors if isinstance(competitors, list) else []:
            if not isinstance(c, dict):
                continue
            side = c.get("homeAway")
            team = c.get("team") if isinstance(c.get("team"), dict) else {}
            name = team.get("abbreviation") or team.get("displayName") or ""
            if side == "home":
                home_team = str(name)
            elif side == "away":
                away_team = str(name)
        if game_id:
            results.append(
                {
                    "game_id": game_id,
                    "home_team": home_team,
                    "away_team": away_team,
                    "start_time": start_time,
                }
            )
    return results


def get_games_by_date(date_str: str) -> List[Dict[str, str]]:
    scoreboard_date = _normalize_scoreboard_date(date_str)
    try:
        scoreboard = ScoreboardV2(
            game_date=scoreboard_date,
            league_id="00",
            day_offset=0,
            headers=_nba_headers(),
        )
        games = scoreboard.game_header.get_dict()["data"]
        teams = scoreboard.line_score.get_dict()["data"]
    except Exception:
        # Primary provider failed; try ESPN fallback.
        return _get_games_by_date_espn(date_str)

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
    # If nba_api returns empty unexpectedly, try ESPN as a fallback.
    if not results:
        try:
            espn = _get_games_by_date_espn(date_str)
            return espn or results
        except Exception:
            return results
    return results


def get_players_for_game(game_id: str) -> List[Dict[str, str]]:
    box = BoxScoreTraditionalV2(game_id=game_id, headers=_nba_headers())
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
    box = BoxScoreTraditionalV2(game_id=game_id, headers=_nba_headers())
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
    log = PlayerGameLog(
        player_id=player_id,
        date_from_nullable="",
        date_to_nullable=end_date,
        headers=_nba_headers(),
    )
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
