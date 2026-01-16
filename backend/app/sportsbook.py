from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional

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
        # We attempt to pull player points/assists/rebounds/PRA if present.
        base = "https://api.the-odds-api.com/v4"
        params = {
            "apiKey": self.api_key,
            "regions": "us",
            # Common player prop market keys (may require a paid tier).
            "markets": "player_points,player_rebounds,player_assists,player_points_rebounds_assists",
            "oddsFormat": "american",
        }
        url = f"{base}/sports/basketball_nba/odds"
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        events = resp.json()

        # Best-effort parse: find outcomes matching player name.
        lines: Dict[str, float] = {}

        def _maybe_set(key: str, value: Any) -> None:
            try:
                if value is None:
                    return
                lines[key] = float(value)
            except Exception:
                return

        for event in events if isinstance(events, list) else []:
            bookmakers = event.get("bookmakers") if isinstance(event, dict) else None
            for book in bookmakers if isinstance(bookmakers, list) else []:
                markets = book.get("markets") if isinstance(book, dict) else None
                for market in markets if isinstance(markets, list) else []:
                    market_key = market.get("key")
                    outcomes = market.get("outcomes") if isinstance(market, dict) else None
                    for outcome in outcomes if isinstance(outcomes, list) else []:
                        name = outcome.get("description") or outcome.get("name")
                        if not isinstance(name, str):
                            continue
                        if player_name.lower() not in name.lower():
                            continue
                        # The "point" value is the line for many props.
                        point = outcome.get("point")
                        if market_key == "player_points":
                            _maybe_set("points", point)
                        elif market_key == "player_rebounds":
                            _maybe_set("rebounds", point)
                        elif market_key == "player_assists":
                            _maybe_set("assists", point)
                        elif market_key == "player_points_rebounds_assists":
                            _maybe_set("pra", point)

        if not lines:
            return None

        return SportsbookResult(
            provider=self.provider_name,
            last_updated=datetime.now(timezone.utc),
            lines=lines,
        )


def get_sportsbook_provider() -> Optional[SportsbookProvider]:
    api_key = os.getenv("ODDS_API_KEY")
    if api_key:
        return OddsApiProvider(api_key=api_key)
    return None

