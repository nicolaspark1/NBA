"""
NBA Service Module

This module provides functions to fetch NBA data including games, players, and box scores
using the nba_api library.

Created: 2026-01-08 05:34:12 UTC
"""

from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from nba_api.client import Client
import pandas as pd


class NBAService:
    """Service class for interacting with NBA API"""

    def __init__(self):
        """Initialize NBA Service with nba_api client"""
        self.client = Client()

    def fetch_games_by_date(self, date: str) -> List[Dict[str, Any]]:
        """
        Fetch all NBA games for a specific date.

        Args:
            date (str): Date in format 'YYYY-MM-DD'

        Returns:
            List[Dict[str, Any]]: List of games with details (game_id, teams, time, etc.)

        Raises:
            ValueError: If date format is invalid
        """
        try:
            # Validate date format
            datetime.strptime(date, '%Y-%m-%d')
        except ValueError:
            raise ValueError("Date must be in format 'YYYY-MM-DD'")

        try:
            games_data = self.client.scoreboard_v2(date_string=date)
            games = games_data.get_data_frames()[0]

            if games.empty:
                return []

            # Extract relevant game information
            games_list = []
            for _, game in games.iterrows():
                game_info = {
                    'game_id': game['GAME_ID'],
                    'game_datetime': game['GAME_DATETIME_EST'],
                    'home_team_id': game['HOME_TEAM_ID'],
                    'home_team_name': game['HOME_TEAM_NAME'],
                    'away_team_id': game['VISITOR_TEAM_ID'],
                    'away_team_name': game['VISITOR_TEAM_NAME'],
                    'home_team_score': game['HOME_TEAM_WINS'],
                    'away_team_score': game['VISITOR_TEAM_WINS'],
                    'game_status': game['GAME_STATUS_TEXT']
                }
                games_list.append(game_info)

            return games_list

        except Exception as e:
            raise Exception(f"Error fetching games for date {date}: {str(e)}")

    def fetch_todays_games(self) -> List[Dict[str, Any]]:
        """
        Fetch all NBA games for today.

        Returns:
            List[Dict[str, Any]]: List of today's games
        """
        today = datetime.utcnow().strftime('%Y-%m-%d')
        return self.fetch_games_by_date(today)

    def fetch_player_info(self, player_name: str) -> Optional[Dict[str, Any]]:
        """
        Fetch detailed information about a specific player.

        Args:
            player_name (str): Name of the player

        Returns:
            Optional[Dict[str, Any]]: Player information including ID, team, stats, etc.
        """
        try:
            # Get all players
            all_players = self.client.find_player_by_name(player_name)

            if not all_players:
                return None

            player = all_players[0]

            player_info = {
                'player_id': player['id'],
                'player_name': player['full_name'],
                'team_id': player.get('team_id'),
                'jersey_number': player.get('jersey_number'),
                'position': player.get('position'),
                'height': player.get('height'),
                'weight': player.get('weight'),
                'draft_year': player.get('draft_year'),
                'draft_round': player.get('draft_round'),
                'draft_number': player.get('draft_number')
            }

            return player_info

        except Exception as e:
            raise Exception(f"Error fetching player info for {player_name}: {str(e)}")

    def fetch_player_season_stats(self, player_id: int, season: str = None) -> Optional[Dict[str, Any]]:
        """
        Fetch season statistics for a specific player.

        Args:
            player_id (int): The NBA player ID
            season (str, optional): Season in format 'YYYY-YY' (e.g., '2024-25'). 
                                   Defaults to current season.

        Returns:
            Optional[Dict[str, Any]]: Player season statistics
        """
        if season is None:
            current_year = datetime.utcnow().year
            season = f"{current_year}-{str(current_year + 1)[-2:]}"

        try:
            player_stats = self.client.player_stat_data(
                player_id=player_id,
                season=season
            )

            stats_df = player_stats.get_data_frames()[0]

            if stats_df.empty:
                return None

            stats_row = stats_df.iloc[0]
            season_stats = {
                'player_id': player_id,
                'season': season,
                'games_played': int(stats_row.get('GP', 0)),
                'minutes': float(stats_row.get('MIN', 0)),
                'points_per_game': float(stats_row.get('PTS', 0)),
                'assists_per_game': float(stats_row.get('AST', 0)),
                'rebounds_per_game': float(stats_row.get('REB', 0)),
                'field_goal_percentage': float(stats_row.get('FG%', 0)),
                'three_point_percentage': float(stats_row.get('3P%', 0)),
                'free_throw_percentage': float(stats_row.get('FT%', 0)),
                'steals_per_game': float(stats_row.get('STL', 0)),
                'blocks_per_game': float(stats_row.get('BLK', 0)),
                'turnovers_per_game': float(stats_row.get('TOV', 0))
            }

            return season_stats

        except Exception as e:
            raise Exception(f"Error fetching player stats for player_id {player_id}: {str(e)}")

    def fetch_box_score(self, game_id: str) -> Dict[str, Any]:
        """
        Fetch detailed box score for a specific game.

        Args:
            game_id (str): The game ID

        Returns:
            Dict[str, Any]: Box score data including player stats and team stats
        """
        try:
            box_score = self.client.box_score_v2(game_id=game_id)
            data_frames = box_score.get_data_frames()

            # Player box score data
            player_stats_df = data_frames[0]

            # Team box score data
            team_stats_df = data_frames[1]

            # Extract player statistics
            players_stats = []
            for _, player in player_stats_df.iterrows():
                player_stat = {
                    'player_id': player['PLAYER_ID'],
                    'player_name': player['PLAYER_NAME'],
                    'team_id': player['TEAM_ID'],
                    'team_name': player['TEAM_ABBREVIATION'],
                    'minutes': player['MIN'],
                    'field_goals_made': player['FGM'],
                    'field_goals_attempted': player['FGA'],
                    'field_goal_percentage': player['FG%'],
                    'three_pointers_made': player['FG3M'],
                    'three_pointers_attempted': player['FG3A'],
                    'three_point_percentage': player['FG3%'],
                    'free_throws_made': player['FTM'],
                    'free_throws_attempted': player['FTA'],
                    'free_throw_percentage': player['FT%'],
                    'offensive_rebounds': player['OREB'],
                    'defensive_rebounds': player['DREB'],
                    'total_rebounds': player['REB'],
                    'assists': player['AST'],
                    'steals': player['STL'],
                    'blocks': player['BLK'],
                    'turnovers': player['TOV'],
                    'personal_fouls': player['PF'],
                    'points': player['PTS'],
                    'plus_minus': player['+/-']
                }
                players_stats.append(player_stat)

            # Extract team statistics
            team_stats = []
            for _, team in team_stats_df.iterrows():
                team_stat = {
                    'team_id': team['TEAM_ID'],
                    'team_name': team['TEAM_NAME'],
                    'minutes': team['MIN'],
                    'field_goals_made': team['FGM'],
                    'field_goals_attempted': team['FGA'],
                    'field_goal_percentage': team['FG%'],
                    'three_pointers_made': team['FG3M'],
                    'three_pointers_attempted': team['FG3A'],
                    'three_point_percentage': team['FG3%'],
                    'free_throws_made': team['FTM'],
                    'free_throws_attempted': team['FTA'],
                    'free_throw_percentage': team['FT%'],
                    'offensive_rebounds': team['OREB'],
                    'defensive_rebounds': team['DREB'],
                    'total_rebounds': team['REB'],
                    'assists': team['AST'],
                    'steals': team['STL'],
                    'blocks': team['BLK'],
                    'turnovers': team['TOV'],
                    'personal_fouls': team['PF'],
                    'points': team['PTS']
                }
                team_stats.append(team_stat)

            box_score_data = {
                'game_id': game_id,
                'player_stats': players_stats,
                'team_stats': team_stats
            }

            return box_score_data

        except Exception as e:
            raise Exception(f"Error fetching box score for game_id {game_id}: {str(e)}")

    def fetch_team_roster(self, team_id: int) -> List[Dict[str, Any]]:
        """
        Fetch roster information for a specific team.

        Args:
            team_id (int): The NBA team ID

        Returns:
            List[Dict[str, Any]]: List of players on the team with their information
        """
        try:
            common_team_roster = self.client.commonteamroster(team_id=team_id)
            roster_df = common_team_roster.get_data_frames()[0]

            if roster_df.empty:
                return []

            roster = []
            for _, player in roster_df.iterrows():
                player_info = {
                    'player_id': player['PLAYER_ID'],
                    'player_name': player['PLAYER_NAME'],
                    'jersey_number': player['NUM'],
                    'position': player['POSITION'],
                    'height': player['HEIGHT'],
                    'weight': player['WEIGHT'],
                    'birth_date': player['BIRTHDATE'],
                    'years_in_league': player['EXP']
                }
                roster.append(player_info)

            return roster

        except Exception as e:
            raise Exception(f"Error fetching roster for team_id {team_id}: {str(e)}")

    def get_game_date_range(self, start_date: str, end_date: str) -> List[Dict[str, Any]]:
        """
        Fetch all games within a date range.

        Args:
            start_date (str): Start date in format 'YYYY-MM-DD'
            end_date (str): End date in format 'YYYY-MM-DD'

        Returns:
            List[Dict[str, Any]]: List of all games in the date range
        """
        try:
            start = datetime.strptime(start_date, '%Y-%m-%d')
            end = datetime.strptime(end_date, '%Y-%m-%d')
        except ValueError:
            raise ValueError("Dates must be in format 'YYYY-MM-DD'")

        all_games = []
        current_date = start

        while current_date <= end:
            date_str = current_date.strftime('%Y-%m-%d')
            try:
                games = self.fetch_games_by_date(date_str)
                all_games.extend(games)
            except Exception as e:
                print(f"Warning: Could not fetch games for {date_str}: {str(e)}")

            current_date += timedelta(days=1)

        return all_games


# Module-level functions for convenience
def fetch_games_by_date(date: str) -> List[Dict[str, Any]]:
    """Convenience function to fetch games by date"""
    service = NBAService()
    return service.fetch_games_by_date(date)


def fetch_todays_games() -> List[Dict[str, Any]]:
    """Convenience function to fetch today's games"""
    service = NBAService()
    return service.fetch_todays_games()


def fetch_player_info(player_name: str) -> Optional[Dict[str, Any]]:
    """Convenience function to fetch player information"""
    service = NBAService()
    return service.fetch_player_info(player_name)


def fetch_box_score(game_id: str) -> Dict[str, Any]:
    """Convenience function to fetch box score"""
    service = NBAService()
    return service.fetch_box_score(game_id)


def fetch_team_roster(team_id: int) -> List[Dict[str, Any]]:
    """Convenience function to fetch team roster"""
    service = NBAService()
    return service.fetch_team_roster(team_id)
