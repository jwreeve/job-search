from sqlalchemy import create_engine, Column, String, DateTime, Boolean, Text, Integer, text, inspect
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime, timezone
import uuid

import os
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./jobs.db")
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class Job(Base):
    __tablename__ = "jobs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    job_key = Column(String, unique=True, nullable=False)
    title = Column(String, nullable=False)
    url = Column(String)
    source_url = Column(String, nullable=False)
    source_name = Column(String)
    matched_keywords = Column(String)
    first_seen = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    is_new = Column(Boolean, default=True)
    is_saved = Column(Boolean, default=False)


class ScanLog(Base):
    __tablename__ = "scan_logs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    scanned_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    source_url = Column(String)
    source_name = Column(String)
    jobs_found = Column(Integer, default=0)
    status = Column(String)
    error_message = Column(Text)


Base.metadata.create_all(bind=engine)


def _migrate():
    inspector = inspect(engine)
    existing = [c["name"] for c in inspector.get_columns("jobs")]
    if "is_saved" not in existing:
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE jobs ADD COLUMN is_saved BOOLEAN DEFAULT 0"))
            conn.commit()

_migrate()
