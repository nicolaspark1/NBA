from __future__ import annotations

import os
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Optional, Tuple

import requests


@dataclass(frozen=True)
class SportsbookResult:
    provider: str
    last_updated: datetime
    lines: Dict[str, float]


class SportsbookProvider:
    provider_name: str

    def get_player_lines(
        self, *, player_id: int, player_name: str, date_str: str, game_id: str | None
    ) -> Optional[SportsbookResult]:
        raise NotImplementedError


_SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}
_NON_WORD_RE = re.compile(r"[^\w\s]", re.UNICODE)
_SPACE_RE = re.compile(r"\s+")


def _strip_accents(s: str) -> str:
    return "".join(
        ch for ch in unicodedata.normalize("NFKD", s) if not unicodedata.combining(ch)
    )


def _normalize_name(name: str) -> str:
    s = _strip_accents((name or "").strip()).lower()
    s = _NON_WORD_RE.sub(" ", s)
    s = _SPACE_RE.sub(" ", s).strip()
    if not s:
        return ""
    parts = s.split(" ")
    while parts and parts[-1] in _SUFFIXES:
        parts = parts[:-1]
    return " ".join(parts)


def _name_match(haystack: str, needle: str) -> bool:
    """
    Best-effort player name match.
    - Substring match on normalized names
    - Token-based fallback: last name must match + first initial match if present
    """
    h = _normalize_name(haystack)
    n = _normalize_name(needle)
    if not h or not n:
        return False
    if n in h or h in n:
        return True
    ht = h.split(" ")
    nt = n.split(" ")
    if len(nt) >= 2 and len(ht) >= 2:
        # last-name match
        if ht[-1] != nt[-1]:
            return False
        # first initial match (if both have first token)
        return ht[0][:1] == nt[0][:1]
    return False


def _iter_dicts(node: Any) -> Iterable[Dict[str, Any]]:
    """
    Yield all dict nodes in a JSON-like structure (dict/list scalars).
    """
    if isinstance(node, dict):
        yield node
        for v in node.values():
            yield from _iter_dicts(v)
    elif isinstance(node, list):
        for v in node:
            yield from _iter_dicts(v)


def _stat_from_label(label: str) -> str | None:
    s = (label or "").lower()
    # Avoid combos (we only want single stat lines for now)
    if "points+rebounds+assists" in s or "points rebounds assists" in s or "pra" in s:
        return None
    if "points" in s:
        return "points"
    if "rebounds" in s:
        return "rebounds"
    if "assists" in s:
        return "assists"
    return None


def _extract_market_outcomes(d: Dict[str, Any]) -> Tuple[str | None, list] | None:
    """
    Try to interpret a dict as a market container with a label/name and outcomes list.
    Returns (market_label, outcomes_list) if it looks like a market.
    """
    outcomes = d.get("outcomes")
    if not isinstance(outcomes, list) or not outcomes:
        return None
    label = d.get("label") or d.get("name") or d.get("marketName") or d.get("title")
    if not isinstance(label, str) or not label.strip():
        return None
    return label, outcomes


def _extract_outcome_line(outcome: Any) -> Tuple[str | None, float | None]:
    """
    Try to interpret a JSON node as a player-outcome with a numeric line.
    Returns (player_label, line_value).
    """
    if not isinstance(outcome, dict):
        return None, None
    player = (
        outcome.get("participant")
        or outcome.get("description")
        or outcome.get("name")
        or outcome.get("label")
    )
    if not isinstance(player, str):
        player = None
    line = outcome.get("line")
    if line is None:
        line = outcome.get("point")
    if line is None:
        line = outcome.get("handicap")
    try:
        line_f = float(line) if line is not None else None
    except Exception:
        line_f = None
    return player, line_f


class DraftKingsProvider(SportsbookProvider):
    """
    DraftKings sportsbook JSON feed integration.
    We do NOT scrape HTML; you must provide a DK JSON URL via env var.
    This is best-effort because DK's schema can change; we scan the JSON for:
      - market labels containing Points/Rebounds/Assists
      - outcomes matching the player name with a numeric line
    """

    provider_name = "draftkings"

    def __init__(self, json_url: str):
        self.json_url = json_url

    def get_player_lines(
        self, *, player_id: int, player_name: str, date_str: str, game_id: str | None
    ) -> Optional[SportsbookResult]:
        resp = requests.get(self.json_url, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        wanted = _normalize_name(player_name)
        if not wanted:
            return None

        lines: Dict[str, float] = {}

        # Pass 1: try market containers with outcomes lists.
        for d in _iter_dicts(data):
            maybe = _extract_market_outcomes(d)
            if not maybe:
                continue
            market_label, outcomes = maybe
            stat = _stat_from_label(market_label)
            if not stat or stat in lines:
                continue
            for outcome in outcomes:
                pl, ln = _extract_outcome_line(outcome)
                if ln is None or not pl:
                    continue
                if _name_match(pl, wanted):
                    lines[stat] = ln
                    break

        # Pass 2 (fallback): scan for any outcome-like dicts that mention the player and a stat.
        if any(k not in lines for k in ("points", "rebounds", "assists")):
            for d in _iter_dicts(data):
                # Look for dicts that have a line and some label with stat words.
                pl, ln = _extract_outcome_line(d)
                if ln is None or not pl:
                    continue
                if not _name_match(pl, wanted):
                    continue
                label = str(d.get("market") or d.get("label") or d.get("name") or "")
                stat = _stat_from_label(label)
                if stat and stat not in lines:
                    lines[stat] = ln

        if not lines:
            return None

        return SportsbookResult(
            provider=self.provider_name,
            last_updated=datetime.now(timezone.utc),
            lines=lines,
        )


class OddsApiProvider(SportsbookProvider):
    """
    Optional integration with The Odds API (https://the-odds-api.com/).
    Notes:
    - We do NOT scrape sportsbooks.
    - Player props availability depends on your plan/markets.
    - If the API returns no usable lines, we fall back to recent-games projections.
    """

    provider_name = "odds_api"

    def __init__(self, api_key: str):
        self.api_key = api_key

    def get_player_lines(
        self, *, player_id: int, player_name: str, date_str: str, game_id: str | None
    ) -> Optional[SportsbookResult]:
        # This is a best-effort implementation. Odds API schemas vary by market/plan.
        # We attempt to pull separate player points / rebounds / assists (NOT PRA).
        base = "https://api.the-odds-api.com/v4"
        params = {
            "apiKey": self.api_key,
            "regions": "us",
            # Common player prop market keys (may require a paid tier).
            "markets": "player_points,player_rebounds,player_assists",
            "oddsFormat": "american",
        }
        url = f"{base}/sports/basketball_nba/odds"
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        events = resp.json()

        # Best-effort parse: find outcomes matching player name.
        lines: Dict[str, float] = {}
        wanted = _normalize_name(player_name)
        if not wanted:
            return None

        preferred_books = [
            b.strip().lower()
            for b in (os.getenv("ODDS_API_BOOKMAKERS") or "draftkings,fanduel").split(",")
            if b.strip()
        ]

        def _maybe_set(key: str, value: Any) -> None:
            try:
                if value is None:
                    return
                lines[key] = float(value)
            except Exception:
                return

        for event in events if isinstance(events, list) else []:
            bookmakers = event.get("bookmakers") if isinstance(event, dict) else None
            books = [b for b in bookmakers if isinstance(bookmakers, list) and isinstance(b, dict)]
            # Prefer a specific bookmaker if available (improves consistency).
            if preferred_books:
                preferred = [b for b in books if str(b.get("key") or "").lower() in preferred_books]
                books = preferred or books

            for book in books:
                markets = book.get("markets") if isinstance(book, dict) else None
                for market in markets if isinstance(markets, list) else []:
                    market_key = market.get("key")
                    outcomes = market.get("outcomes") if isinstance(market, dict) else None
                    for outcome in outcomes if isinstance(outcomes, list) else []:
                        # For player props, Odds API commonly uses:
                        # - outcome["name"] == "Over"/"Under"
                        # - outcome["description"] == "<Player Name>"
                        candidate = (
                            outcome.get("description")
                            or outcome.get("participant")
                            or outcome.get("name")
                        )
                        if not isinstance(candidate, str) or not candidate.strip():
                            continue
                        if not _name_match(candidate, wanted):
                            continue
                        # The "point" value is the line for many props.
                        point = outcome.get("point")
                        if market_key == "player_points":
                            _maybe_set("points", point)
                        elif market_key == "player_rebounds":
                            _maybe_set("rebounds", point)
                        elif market_key == "player_assists":
                            _maybe_set("assists", point)
                        # Stop early if we found all three.
                        if (
                            "points" in lines
                            and "rebounds" in lines
                            and "assists" in lines
                        ):
                            return SportsbookResult(
                                provider=self.provider_name,
                                last_updated=datetime.now(timezone.utc),
                                lines=lines,
                            )

        if not lines:
            return None

        return SportsbookResult(
            provider=self.provider_name,
            last_updated=datetime.now(timezone.utc),
            lines=lines,
        )


def get_sportsbook_provider() -> Optional[SportsbookProvider]:
    # Optional selector; if set, only use the requested provider.
    preferred = (os.getenv("PROJECTIONS_PROVIDER") or "").strip().lower()

    dk_url = (os.getenv("DRAFTKINGS_PROPS_URL") or "").strip()
    odds_key = (os.getenv("ODDS_API_KEY") or "").strip()

    if preferred:
        if preferred in {"dk", "draftkings"} and dk_url:
            return DraftKingsProvider(json_url=dk_url)
        if preferred in {"odds", "odds_api"} and odds_key:
            return OddsApiProvider(api_key=odds_key)
        return None

    # Default preference: DraftKings if configured, otherwise Odds API.
    if dk_url:
        return DraftKingsProvider(json_url=dk_url)
    if odds_key:
        return OddsApiProvider(api_key=odds_key)
    return None

