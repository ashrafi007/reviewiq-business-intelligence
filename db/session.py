import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg2://", 1)

engine = (
    create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
        pool_recycle=300,
        connect_args={
            "keepalives": 1,
            "keepalives_idle": 30,
            "keepalives_interval": 10,
            "keepalives_count": 3,
            "connect_timeout": 10,
            "options": "-c statement_timeout=30000",
        },
    )
    if DATABASE_URL
    else None
)
SessionLocal = sessionmaker(bind=engine) if engine else None


def get_session():
    if SessionLocal is None:
        raise RuntimeError("DATABASE_URL is not set in .env")
    return SessionLocal()
