from __future__ import annotations

import re
import unicodedata
from functools import lru_cache
from typing import Any, Dict, List, Optional

from nba_api.stats.static import players as nba_players


_SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}
_NON_WORD_RE = re.compile(r"[^\w\s]", re.UNICODE)
_SPACE_RE = re.compile(r"\s+")


def _strip_accents(s: str) -> str:
    # e.g., "Bojan Bogdanović" -> "Bojan Bogdanovic"
    return "".join(
        ch for ch in unicodedata.normalize("NFKD", s) if not unicodedata.combining(ch)
    )


def _normalize_name(full_name: str) -> str:
    """
    Normalize names across providers.
    ESPN often includes punctuation/suffixes that differ from nba_api static names.
    """
    s = _strip_accents((full_name or "").strip()).lower()
    s = _NON_WORD_RE.sub(" ", s)  # drop punctuation/apostrophes/dots
    s = _SPACE_RE.sub(" ", s).strip()
    if not s:
        return ""
    parts = s.split(" ")
    # Drop common suffixes (only if trailing).
    while parts and parts[-1] in _SUFFIXES:
        parts = parts[:-1]
    return " ".join(parts)


@lru_cache(maxsize=1)
def _player_index() -> Dict[str, List[Dict[str, Any]]]:
    """
    Map normalized full_name -> list of nba_api player dicts.
    We keep a list because duplicates exist (e.g., "Gary Payton").
    """
    idx: Dict[str, List[Dict[str, Any]]] = {}
    for p in nba_players.get_players() or []:
        if not isinstance(p, dict):
            continue
        full = str(p.get("full_name") or "").strip()
        key = _normalize_name(full)
        if not key:
            continue
        idx.setdefault(key, []).append(p)
    return idx


def _pick_best_candidate(candidates: List[Dict[str, Any]]) -> Optional[int]:
    if not candidates:
        return None
    # Prefer active players if available.
    active = [c for c in candidates if isinstance(c, dict) and c.get("is_active")]
    pick = active[0] if active else candidates[0]
    try:
        return int(pick["id"])
    except Exception:
        return None


@lru_cache(maxsize=4096)
def find_nba_player_id_by_name(full_name: str) -> Optional[int]:
    """
    Best-effort mapping from a full name string to an NBA Stats player_id.
    Uses nba_api static player list (no network).
    """
    name = (full_name or "").strip()
    if not name:
        return None

    # First try nba_api's built-in matcher (fast path).
    matches = nba_players.find_players_by_full_name(name)
    if matches:
        pid = _pick_best_candidate([m for m in matches if isinstance(m, dict)])
        if pid:
            return pid

    # Fallback: normalize punctuation/suffixes (common with ESPN rosters).
    key = _normalize_name(name)
    if not key:
        return None
    idx = _player_index()
    if key in idx:
        pid = _pick_best_candidate(idx[key])
        if pid:
            return pid

    # Fallback: try to recover from common cases like "First M. Last" vs "First Last".
    # We remove any single-letter middle token and re-check.
    parts = key.split(" ")
    if len(parts) >= 3:
        compact = [parts[0]] + [p for p in parts[1:-1] if len(p) > 1] + [parts[-1]]
        compact_key = " ".join(compact).strip()
        if compact_key and compact_key in idx:
            pid = _pick_best_candidate(idx[compact_key])
            if pid:
                return pid

    return None

