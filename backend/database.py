"""
Database configuration and session management for the NBA application.
"""

import os
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session, declarative_base
from sqlalchemy.pool import StaticPool
from typing import Generator
import logging

# Configure logging
logger = logging.getLogger(__name__)

# Database configuration
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite:///./nba.db"
)

# Determine if using SQLite
SQLALCHEMY_KWARGS = {}
if DATABASE_URL.startswith("sqlite"):
    # SQLite specific configuration
    SQLALCHEMY_KWARGS = {
        "connect_args": {"check_same_thread": False},
        "poolclass": StaticPool,
    }
else:
    # PostgreSQL or other databases
    SQLALCHEMY_KWARGS = {
        "pool_pre_ping": True,  # Verify connections before using them
        "pool_size": 10,
        "max_overflow": 20,
    }

# Create database engine
engine = create_engine(
    DATABASE_URL,
    **SQLALCHEMY_KWARGS,
    echo=os.getenv("SQL_ECHO", "False").lower() == "true"
)

# Create session factory
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

# Create base class for models
Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """
    Dependency for getting database sessions in FastAPI routes.
    
    Usage:
        @app.get("/items/")
        def get_items(db: Session = Depends(get_db)):
            return db.query(Item).all()
    
    Yields:
        Session: SQLAlchemy database session
    """
    db = SessionLocal()
    try:
        yield db
    except Exception as e:
        logger.error(f"Database session error: {str(e)}")
        db.rollback()
        raise
    finally:
        db.close()


def init_db() -> None:
    """
    Initialize the database by creating all tables.
    This should be called once during application startup.
    """
    try:
        logger.info(f"Initializing database: {DATABASE_URL}")
        Base.metadata.create_all(bind=engine)
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Error initializing database: {str(e)}")
        raise


def drop_db() -> None:
    """
    Drop all tables from the database.
    WARNING: This is a destructive operation. Use with caution.
    """
    try:
        logger.warning("Dropping all database tables")
        Base.metadata.drop_all(bind=engine)
        logger.info("All database tables dropped")
    except Exception as e:
        logger.error(f"Error dropping database: {str(e)}")
        raise


def get_engine():
    """
    Get the SQLAlchemy engine instance.
    
    Returns:
        Engine: SQLAlchemy engine
    """
    return engine


def get_session_factory():
    """
    Get the session factory.
    
    Returns:
        sessionmaker: SQLAlchemy session factory
    """
    return SessionLocal


# Add event listeners for connection pool management (non-SQLite databases)
if not DATABASE_URL.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def receive_connect(dbapi_conn, connection_record):
        """Enable foreign keys on connection for PostgreSQL"""
        cursor = dbapi_conn.cursor()
        cursor.execute("SET foreign_key_checks=1")
        cursor.close()


# Health check function
def check_db_connection() -> bool:
    """
    Check if the database connection is healthy.
    
    Returns:
        bool: True if connection is healthy, False otherwise
    """
    try:
        with engine.connect() as connection:
            connection.execute("SELECT 1")
        logger.info("Database connection is healthy")
        return True
    except Exception as e:
        logger.error(f"Database connection error: {str(e)}")
        return False
