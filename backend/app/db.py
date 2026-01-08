import os

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker


def _normalize_database_url(url: str) -> str:
    # Render (and some other hosts) may provide postgres://; SQLAlchemy prefers postgresql://
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql://", 1)
    return url


def get_database_url() -> str:
    env_url = os.getenv("DATABASE_URL")
    if env_url:
        return _normalize_database_url(env_url)

    # Local/dev default: SQLite file in the current working directory.
    # In production (Render), you can set SQLITE_PATH to a mounted disk path like /var/data/nba.db.
    sqlite_path = os.getenv("SQLITE_PATH", "./nba.db").strip()
    if not sqlite_path:
        sqlite_path = "./nba.db"

    if sqlite_path.startswith("sqlite:"):
        return sqlite_path
    if sqlite_path.startswith("/"):
        return f"sqlite:////{sqlite_path.lstrip('/')}"
    return f"sqlite:///{sqlite_path}"


DATABASE_URL = get_database_url()

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()
