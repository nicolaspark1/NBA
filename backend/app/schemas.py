from datetime import date, datetime
from typing import Any, Dict, List

from pydantic import BaseModel, ConfigDict


class GroupCreate(BaseModel):
    group_name: str
    display_name: str


class GroupJoin(BaseModel):
    group_code: str
    display_name: str


class GroupOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    code: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    display_name: str


class GroupResponse(BaseModel):
    group: GroupOut
    user: UserOut


class GroupMemberOut(BaseModel):
    id: int
    display_name: str
    joined_at: datetime


class GameOut(BaseModel):
    game_id: str
    home_team: str
    away_team: str
    start_time: str


class PlayerOut(BaseModel):
    player_id: int
    player_name: str
    team: str
    game_id: str


class RosterPlayerOut(BaseModel):
    # NBA Stats player_id when we can map it from name; may be null for unknowns.
    player_id: int | None = None
    player_name: str
    position: str | None = None
    jersey: str | None = None


class TeamRosterOut(BaseModel):
    team_id: str
    team_name: str
    team_abbr: str
    players: List[RosterPlayerOut]


class GameRostersResponse(BaseModel):
    game_id: str
    date: date
    source: str
    last_updated: datetime
    home: TeamRosterOut
    away: TeamRosterOut


class RecentGamesProjectionOut(BaseModel):
    n_games_used: int
    points: float
    assists: float
    rebounds: float
    steals: float
    blocks: float
    turnovers: float
    personal_fouls: float


class SportsbookLinesOut(BaseModel):
    provider: str
    last_updated: datetime
    lines: Dict[str, float]


class PlayerProjectionResponse(BaseModel):
    player_id: int
    player_name: str
    date: date
    game_id: str | None = None
    source: str
    reason: str | None = None
    last_updated: datetime
    recent_games: RecentGamesProjectionOut | None = None
    sportsbook: SportsbookLinesOut | None = None


class PickCreate(BaseModel):
    user_id: int
    date: date
    player_id: int
    player_name: str


class PickWithUser(BaseModel):
    id: int
    user_id: int
    user_name: str
    player_name: str
    status: str


class PickResultOut(BaseModel):
    pick_id: int
    score: float
    breakdown: Dict[str, Any]


class LeaderboardRow(BaseModel):
    user_id: int
    user_name: str
    score: float


class LeaderboardResponse(BaseModel):
    leaderboard: List[LeaderboardRow]
    picks_with_results: List[PickResultOut]
