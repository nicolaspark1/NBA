"""
Scoring module for NBA pick calculations and stats analysis.
"""

from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum


class StatType(Enum):
    """Enumeration of available stat types."""
    POINTS = "points"
    REBOUNDS = "rebounds"
    ASSISTS = "assists"
    STEALS = "steals"
    BLOCKS = "blocks"
    FIELD_GOAL_PERCENTAGE = "fg_percentage"
    THREE_POINT_PERCENTAGE = "three_pt_percentage"
    FREE_THROW_PERCENTAGE = "ft_percentage"


@dataclass
class PlayerStats:
    """Data class representing player statistics."""
    player_name: str
    player_id: str
    game_id: str
    points: float = 0.0
    rebounds: float = 0.0
    assists: float = 0.0
    steals: float = 0.0
    blocks: float = 0.0
    fg_percentage: float = 0.0
    three_pt_percentage: float = 0.0
    ft_percentage: float = 0.0

    def get_stat(self, stat_type: StatType) -> float:
        """Get a specific stat by type."""
        stat_mapping = {
            StatType.POINTS: self.points,
            StatType.REBOUNDS: self.rebounds,
            StatType.ASSISTS: self.assists,
            StatType.STEALS: self.steals,
            StatType.BLOCKS: self.blocks,
            StatType.FIELD_GOAL_PERCENTAGE: self.fg_percentage,
            StatType.THREE_POINT_PERCENTAGE: self.three_pt_percentage,
            StatType.FREE_THROW_PERCENTAGE: self.ft_percentage,
        }
        return stat_mapping.get(stat_type, 0.0)


@dataclass
class Pick:
    """Data class representing a player pick."""
    player_name: str
    player_id: str
    stat_type: StatType
    line: float
    pick_type: str  # "over" or "under"
    game_id: str


class ScoringEngine:
    """Engine for computing expected stats, actual stats, and pick scores."""

    def __init__(self):
        """Initialize the scoring engine."""
        self.player_history: Dict[str, List[PlayerStats]] = {}
        self.picks: List[Pick] = []

    def compute_expected_stats(
        self,
        player_id: str,
        stat_type: StatType,
        games_lookback: int = 10,
        weight_recent: bool = True
    ) -> float:
        """
        Compute expected stats for a player based on historical data.

        Args:
            player_id: The player's ID
            stat_type: The type of stat to compute
            games_lookback: Number of previous games to consider
            weight_recent: Whether to weight recent games more heavily

        Returns:
            Expected stat value as a float
        """
        if player_id not in self.player_history:
            return 0.0

        history = self.player_history[player_id][-games_lookback:]

        if not history:
            return 0.0

        if weight_recent:
            # Weight recent games more heavily using a linear weighting scheme
            weights = [i + 1 for i in range(len(history))]
            total_weight = sum(weights)
            weighted_sum = sum(
                stat.get_stat(stat_type) * weight
                for stat, weight in zip(history, weights)
            )
            return weighted_sum / total_weight
        else:
            # Simple average
            total = sum(stat.get_stat(stat_type) for stat in history)
            return total / len(history)

    def compute_actual_stats(
        self,
        player_id: str,
        game_id: str
    ) -> Optional[PlayerStats]:
        """
        Retrieve actual stats for a player in a specific game.

        Args:
            player_id: The player's ID
            game_id: The game's ID

        Returns:
            PlayerStats object if found, None otherwise
        """
        if player_id not in self.player_history:
            return None

        for stats in self.player_history[player_id]:
            if stats.game_id == game_id:
                return stats

        return None

    def compute_pick_score(
        self,
        pick: Pick,
        expected_stat: float,
        actual_stat: float
    ) -> Tuple[float, bool]:
        """
        Compute the score for a pick based on expected vs actual stats.

        Args:
            pick: The Pick object
            expected_stat: The expected stat value
            actual_stat: The actual stat value

        Returns:
            Tuple of (score, is_correct) where:
            - score is a float between 0 and 1 indicating confidence
            - is_correct is a boolean indicating if the pick won
        """
        is_correct = False

        if pick.pick_type.lower() == "over":
            is_correct = actual_stat > pick.line
        elif pick.pick_type.lower() == "under":
            is_correct = actual_stat < pick.line
        else:
            raise ValueError(f"Invalid pick type: {pick.pick_type}")

        # Calculate confidence score based on how far the actual stat is from the line
        diff = abs(actual_stat - pick.line)
        # Normalize the difference to a 0-1 scale
        # Using a sigmoid-like approach for smoother scoring
        confidence = min(1.0, diff / max(pick.line, 1.0))

        # Adjust confidence based on whether the pick was correct
        score = confidence if is_correct else (1.0 - confidence)

        return score, is_correct

    def add_player_game_stats(self, stats: PlayerStats) -> None:
        """
        Add game statistics for a player.

        Args:
            stats: PlayerStats object containing game statistics
        """
        if stats.player_id not in self.player_history:
            self.player_history[stats.player_id] = []
        self.player_history[stats.player_id].append(stats)

    def add_pick(self, pick: Pick) -> None:
        """
        Add a pick for evaluation.

        Args:
            pick: Pick object to add
        """
        self.picks.append(pick)

    def evaluate_pick(self, pick: Pick) -> Dict[str, any]:
        """
        Fully evaluate a pick including expected, actual, and score.

        Args:
            pick: The Pick object to evaluate

        Returns:
            Dictionary containing evaluation results
        """
        expected = self.compute_expected_stats(
            pick.player_id,
            pick.stat_type,
            games_lookback=10
        )
        actual = self.compute_actual_stats(pick.player_id, pick.game_id)

        if actual is None:
            return {
                "pick": pick,
                "expected_stat": expected,
                "actual_stat": None,
                "score": None,
                "is_correct": None,
                "status": "pending"
            }

        actual_stat = actual.get_stat(pick.stat_type)
        score, is_correct = self.compute_pick_score(pick, expected, actual_stat)

        return {
            "pick": pick,
            "expected_stat": expected,
            "actual_stat": actual_stat,
            "score": score,
            "is_correct": is_correct,
            "status": "completed"
        }

    def evaluate_all_picks(self) -> List[Dict[str, any]]:
        """
        Evaluate all picks.

        Returns:
            List of evaluation results for each pick
        """
        return [self.evaluate_pick(pick) for pick in self.picks]

    def get_player_stats_summary(
        self,
        player_id: str,
        games_lookback: int = 10
    ) -> Dict[str, float]:
        """
        Get a summary of all stats for a player.

        Args:
            player_id: The player's ID
            games_lookback: Number of previous games to consider

        Returns:
            Dictionary with stat types as keys and averages as values
        """
        summary = {}
        for stat_type in StatType:
            summary[stat_type.value] = self.compute_expected_stats(
                player_id,
                stat_type,
                games_lookback=games_lookback
            )
        return summary

    def clear_history(self) -> None:
        """Clear all player history and picks."""
        self.player_history.clear()
        self.picks.clear()
