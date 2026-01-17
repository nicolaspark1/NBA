from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Tuple

import requests


def _normalize_yyyymmdd(date_str: str) -> str:
    s = (date_str or "").strip()
    if not s:
        raise ValueError("date is required")
    if "-" in s:
        return datetime.strptime(s, "%Y-%m-%d").strftime("%Y%m%d")
    if "/" in s:
        return datetime.strptime(s, "%m/%d/%Y").strftime("%Y%m%d")
    return s


def fetch_scoreboard(date_str: str) -> List[Dict[str, Any]]:
    """
    ESPN public JSON scoreboard feed (server-side). Not HTML scraping.
    """
    yyyymmdd = _normalize_yyyymmdd(date_str)
    url = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard"
    resp = requests.get(url, params={"dates": yyyymmdd}, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    events = data.get("events", []) if isinstance(data, dict) else []
    return events if isinstance(events, list) else []


def parse_schedule_from_events(events: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    """
    Returns list of games:
      { game_id, home_team, away_team, start_time, home_team_id, away_team_id }
    `game_id` is ESPN event id (string).
    """
    results: List[Dict[str, str]] = []
    for event in events:
        if not isinstance(event, dict):
            continue
        game_id = str(event.get("id") or "").strip()
        start_time = str(event.get("date") or "").strip()
        competitions = event.get("competitions")
        comp0 = competitions[0] if isinstance(competitions, list) and competitions else None
        competitors = comp0.get("competitors") if isinstance(comp0, dict) else None

        home_team = ""
        away_team = ""
        home_team_id = ""
        away_team_id = ""

        for c in competitors if isinstance(competitors, list) else []:
            if not isinstance(c, dict):
                continue
            side = c.get("homeAway")
            team = c.get("team") if isinstance(c.get("team"), dict) else {}
            abbr = team.get("abbreviation") or ""
            name = team.get("displayName") or ""
            team_id = str(team.get("id") or "")
            label = str(abbr or name or "").strip()
            if side == "home":
                home_team = label
                home_team_id = team_id
            elif side == "away":
                away_team = label
                away_team_id = team_id

        if game_id:
            results.append(
                {
                    "game_id": game_id,
                    "home_team": home_team,
                    "away_team": away_team,
                    "start_time": start_time,
                    "home_team_id": home_team_id,
                    "away_team_id": away_team_id,
                }
            )
    return results


def fetch_team_roster(team_id: str) -> Tuple[str, str, List[Dict[str, Any]]]:
    """
    ESPN public JSON roster for a team.
    Returns (team_name, team_abbr, athletes[])
    """
    url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams/{team_id}/roster"
    resp = requests.get(url, timeout=10)
    resp.raise_for_status()
    data = resp.json()

    team = data.get("team") if isinstance(data, dict) else None
    team_name = ""
    team_abbr = ""
    if isinstance(team, dict):
        team_name = str(team.get("displayName") or "")
        team_abbr = str(team.get("abbreviation") or "")

    athletes = data.get("athletes") if isinstance(data, dict) else None
    # ESPN may return athletes as groups by position; normalize to flat list.
    flat: List[Dict[str, Any]] = []
    if isinstance(athletes, list):
        for group in athletes:
            if isinstance(group, dict) and isinstance(group.get("items"), list):
                flat.extend([x for x in group["items"] if isinstance(x, dict)])
            elif isinstance(group, dict):
                flat.append(group)
    elif isinstance(athletes, dict) and isinstance(athletes.get("items"), list):
        flat.extend([x for x in athletes["items"] if isinstance(x, dict)])

    return team_name, team_abbr, flat

