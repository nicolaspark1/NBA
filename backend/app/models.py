import enum
from datetime import datetime

from sqlalchemy import (
    JSON,
    Column,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from .db import Base


class PickStatus(enum.Enum):
    picked = "picked"
    scored = "scored"


class Group(Base):
    __tablename__ = "groups"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    code = Column(String, unique=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    members = relationship("GroupMember", back_populates="group")


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    display_name = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class GroupMember(Base):
    __tablename__ = "group_members"
    __table_args__ = (UniqueConstraint("group_id", "user_id"),)

    id = Column(Integer, primary_key=True)
    group_id = Column(Integer, ForeignKey("groups.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    joined_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    group = relationship("Group", back_populates="members")
    user = relationship("User")


class Pick(Base):
    __tablename__ = "picks"
    __table_args__ = (UniqueConstraint("group_id", "user_id", "date"),)

    id = Column(Integer, primary_key=True)
    group_id = Column(Integer, ForeignKey("groups.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    date = Column(Date, nullable=False)
    player_id = Column(Integer, nullable=False)
    player_name = Column(String, nullable=False)
    game_id = Column(String, nullable=True)
    status = Column(Enum(PickStatus), default=PickStatus.picked, nullable=False)
    locked_at = Column(DateTime, nullable=True)

    user = relationship("User")
    group = relationship("Group")
    result = relationship("PickResult", back_populates="pick", uselist=False)


class PlayerGameStat(Base):
    __tablename__ = "player_game_stats"
    __table_args__ = (UniqueConstraint("player_id", "game_id"),)

    id = Column(Integer, primary_key=True)
    date = Column(Date, nullable=False)
    player_id = Column(Integer, nullable=False)
    game_id = Column(String, nullable=False)
    points = Column(Float, default=0)
    assists = Column(Float, default=0)
    rebounds = Column(Float, default=0)
    steals = Column(Float, default=0)
    blocks = Column(Float, default=0)
    turnovers = Column(Float, default=0)
    personal_fouls = Column(Float, default=0)
    minutes = Column(String, nullable=True)
    fetched_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class PlayerExpectedStat(Base):
    __tablename__ = "player_expected_stats"
    __table_args__ = (UniqueConstraint("player_id", "date"),)

    id = Column(Integer, primary_key=True)
    date = Column(Date, nullable=False)
    player_id = Column(Integer, nullable=False)
    n_games_used = Column(Integer, nullable=False)
    exp_points = Column(Float, default=0)
    exp_assists = Column(Float, default=0)
    exp_rebounds = Column(Float, default=0)
    exp_steals = Column(Float, default=0)
    exp_blocks = Column(Float, default=0)
    exp_turnovers = Column(Float, default=0)
    exp_personal_fouls = Column(Float, default=0)
    computed_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class PlayerSportsbookLine(Base):
    __tablename__ = "player_sportsbook_lines"
    __table_args__ = (UniqueConstraint("player_id", "date", "provider"),)

    id = Column(Integer, primary_key=True)
    date = Column(Date, nullable=False)
    game_id = Column(String, nullable=True)
    player_id = Column(Integer, nullable=False)
    player_name = Column(String, nullable=True)
    provider = Column(String, nullable=False)
    lines_json = Column(JSON, nullable=False)
    fetched_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class PickResult(Base):
    __tablename__ = "pick_results"

    id = Column(Integer, primary_key=True)
    pick_id = Column(Integer, ForeignKey("picks.id"), unique=True, nullable=False)
    score = Column(Float, nullable=False)
    breakdown_json = Column(JSON, nullable=False)
    computed_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    pick = relationship("Pick", back_populates="result")


class DailyLeaderboard(Base):
    __tablename__ = "daily_leaderboards"

    id = Column(Integer, primary_key=True)
    group_id = Column(Integer, ForeignKey("groups.id"), nullable=False)
    date = Column(Date, nullable=False)
    computed_at = Column(DateTime, default=datetime.utcnow, nullable=False)
