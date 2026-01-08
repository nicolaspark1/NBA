"""
SQLAlchemy ORM models for NBA application.

This module defines the data models for managing groups, users, picks, and player statistics.
"""

from datetime import datetime
from sqlalchemy import (
    Column, String, Integer, Float, DateTime, Boolean, ForeignKey, 
    Text, Enum, Numeric, DECIMAL
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
import enum

Base = declarative_base()


class Group(Base):
    """
    Represents a group of users participating in picks/predictions.
    """
    __tablename__ = "groups"
    
    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False, unique=True)
    description = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    members = relationship("GroupMember", back_populates="group", cascade="all, delete-orphan")
    picks = relationship("Pick", back_populates="group", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Group(id={self.id}, name='{self.name}')>"


class User(Base):
    """
    Represents a user in the application.
    """
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True)
    username = Column(String(128), nullable=False, unique=True)
    email = Column(String(255), nullable=False, unique=True)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(255))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_active = Column(Boolean, default=True)
    
    # Relationships
    group_memberships = relationship("GroupMember", back_populates="user", cascade="all, delete-orphan")
    picks = relationship("Pick", back_populates="user", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<User(id={self.id}, username='{self.username}', email='{self.email}')>"


class GroupMember(Base):
    """
    Represents the relationship between a User and a Group (many-to-many).
    """
    __tablename__ = "group_members"
    
    id = Column(Integer, primary_key=True)
    group_id = Column(Integer, ForeignKey("groups.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    joined_at = Column(DateTime, default=datetime.utcnow)
    role = Column(String(50), default="member")  # e.g., "admin", "member"
    
    # Relationships
    group = relationship("Group", back_populates="members")
    user = relationship("User", back_populates="group_memberships")
    
    def __repr__(self):
        return f"<GroupMember(group_id={self.group_id}, user_id={self.user_id}, role='{self.role}')>"


class Pick(Base):
    """
    Represents a user's prediction/pick for a player's performance in a game.
    """
    __tablename__ = "picks"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    group_id = Column(Integer, ForeignKey("groups.id"), nullable=False)
    player_id = Column(Integer, nullable=False)  # NBA player ID
    game_id = Column(Integer, nullable=False)    # NBA game ID
    stat_type = Column(String(50), nullable=False)  # e.g., "points", "rebounds", "assists"
    predicted_value = Column(DECIMAL(10, 2), nullable=False)
    pick_type = Column(String(20), nullable=False)  # e.g., "over", "under"
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_settled = Column(Boolean, default=False)
    
    # Relationships
    user = relationship("User", back_populates="picks")
    group = relationship("Group", back_populates="picks")
    result = relationship("PickResult", uselist=False, back_populates="pick", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Pick(id={self.id}, user_id={self.user_id}, player_id={self.player_id}, stat_type='{self.stat_type}')>"


class PlayerGameStat(Base):
    """
    Represents actual game statistics for a player in a specific game.
    """
    __tablename__ = "player_game_stats"
    
    id = Column(Integer, primary_key=True)
    player_id = Column(Integer, nullable=False)  # NBA player ID
    game_id = Column(Integer, nullable=False)    # NBA game ID
    points = Column(DECIMAL(10, 2))
    rebounds = Column(DECIMAL(10, 2))
    assists = Column(DECIMAL(10, 2))
    steals = Column(DECIMAL(10, 2))
    blocks = Column(DECIMAL(10, 2))
    turnovers = Column(DECIMAL(10, 2))
    three_pointers_made = Column(DECIMAL(10, 2))
    field_goal_percentage = Column(DECIMAL(5, 2))
    free_throw_percentage = Column(DECIMAL(5, 2))
    minutes_played = Column(DECIMAL(5, 2))
    game_date = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f"<PlayerGameStat(player_id={self.player_id}, game_id={self.game_id}, points={self.points})>"


class PlayerExpectedStat(Base):
    """
    Represents projected or expected statistics for a player in an upcoming game.
    """
    __tablename__ = "player_expected_stats"
    
    id = Column(Integer, primary_key=True)
    player_id = Column(Integer, nullable=False)  # NBA player ID
    game_id = Column(Integer, nullable=False)    # NBA game ID
    expected_points = Column(DECIMAL(10, 2))
    expected_rebounds = Column(DECIMAL(10, 2))
    expected_assists = Column(DECIMAL(10, 2))
    expected_steals = Column(DECIMAL(10, 2))
    expected_blocks = Column(DECIMAL(10, 2))
    expected_turnovers = Column(DECIMAL(10, 2))
    expected_three_pointers = Column(DECIMAL(10, 2))
    confidence_score = Column(DECIMAL(5, 2))  # 0-100 confidence percentage
    projection_source = Column(String(100))    # e.g., "ESPN", "DraftKings", "FanDuel"
    game_date = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f"<PlayerExpectedStat(player_id={self.player_id}, game_id={self.game_id}, expected_points={self.expected_points})>"


class PickResult(Base):
    """
    Represents the result/outcome of a user's pick once the game is settled.
    """
    __tablename__ = "pick_results"
    
    id = Column(Integer, primary_key=True)
    pick_id = Column(Integer, ForeignKey("picks.id"), nullable=False, unique=True)
    actual_value = Column(DECIMAL(10, 2), nullable=False)
    is_winner = Column(Boolean, nullable=False)
    points_earned = Column(Integer, default=0)  # Points awarded for correct pick
    settled_at = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    pick = relationship("Pick", back_populates="result")
    
    def __repr__(self):
        return f"<PickResult(pick_id={self.pick_id}, actual_value={self.actual_value}, is_winner={self.is_winner})>"
