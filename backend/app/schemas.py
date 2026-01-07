from datetime import date, datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class GroupCreate(BaseModel):
    group_name: str
    display_name: str


class GroupJoin(BaseModel):
    group_code: str
    display_name: str


class GroupOut(BaseModel):
    id: int
    name: str
    code: str

    class Config:
        orm_mode = True


class UserOut(BaseModel):
    id: int
    display_name: str

    class Config:
        orm_mode = True


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


class PickCreate(BaseModel):
    user_id: int
    date: date
    player_id: int
    player_name: str


class PickOut(BaseModel):
    id: int
    group_id: int
    user_id: int
    date: date
    player_id: int
    player_name: str
    game_id: Optional[str]
    status: str

    class Config:
        orm_mode = True


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
