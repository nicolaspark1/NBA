from __future__ import annotations

from functools import lru_cache
from typing import Optional

from nba_api.stats.static import players as nba_players


@lru_cache(maxsize=4096)
def find_nba_player_id_by_name(full_name: str) -> Optional[int]:
    """
    Best-effort mapping from a full name string to an NBA Stats player_id.
    Uses nba_api static player list (no network).
    """
    name = (full_name or "").strip()
    if not name:
        return None

    matches = nba_players.find_players_by_full_name(name)
    if not matches:
        return None

    # Prefer active players if available.
    active = [m for m in matches if isinstance(m, dict) and m.get("is_active")]
    pick = active[0] if active else matches[0]
    try:
        return int(pick["id"])
    except Exception:
        return None

