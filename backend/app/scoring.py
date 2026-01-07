from __future__ import annotations

from datetime import date
from typing import Dict, List

from .models import PlayerExpectedStat
from .nba import get_recent_games

N_GAMES = 5
WEIGHTS = {
    "points": 1.0,
    "assists": 1.5,
    "rebounds": 1.2,
    "steals": 3.0,
    "blocks": 3.0,
    "turnovers": -1.5,
    "personal_fouls": -0.5,
}


def compute_expected_stats(player_id: int, target_date: date) -> PlayerExpectedStat:
    end_date = target_date.strftime("%Y-%m-%d")
    games = get_recent_games(player_id, end_date=end_date, n_games=N_GAMES)
    n_games_used = len(games)
    totals = {stat: 0.0 for stat in WEIGHTS}
    for game in games:
        for stat in totals:
            totals[stat] += game.get(stat, 0.0)
    if n_games_used > 0:
        averages = {stat: totals[stat] / n_games_used for stat in totals}
    else:
        averages = {stat: 0.0 for stat in totals}

    return PlayerExpectedStat(
        date=target_date,
        player_id=player_id,
        n_games_used=max(n_games_used, 1) if n_games_used == 0 else n_games_used,
        exp_points=averages["points"],
        exp_assists=averages["assists"],
        exp_rebounds=averages["rebounds"],
        exp_steals=averages["steals"],
        exp_blocks=averages["blocks"],
        exp_turnovers=averages["turnovers"],
        exp_personal_fouls=averages["personal_fouls"],
    )


def score_pick(actual: Dict[str, float], expected: PlayerExpectedStat) -> Dict[str, float]:
    breakdown: Dict[str, float] = {}
    total = 0.0
    for stat, weight in WEIGHTS.items():
        exp_value = getattr(expected, f"exp_{stat}")
        actual_value = actual.get(stat, 0.0)
        contribution = (actual_value - exp_value) * weight
        breakdown[stat] = round(contribution, 2)
        total += contribution
    return {"score": round(total, 1), "breakdown": breakdown}
