from sqlalchemy import CheckConstraint, Column, DateTime, Integer, String, Text
from sqlalchemy.sql import func

from models.base import Base


class SystemHealthHeartbeat(Base):
    __tablename__ = "system_health_heartbeat"
    __table_args__ = (
        CheckConstraint("id = 1", name="ck_system_health_heartbeat_singleton_id"),
    )

    id = Column(Integer, primary_key=True, default=1)
    heartbeat_key = Column(String(32), nullable=False, unique=True, default="default")
    last_success_at = Column(DateTime(timezone=True), nullable=True)
    last_attempt_at = Column(DateTime(timezone=True), nullable=True)
    last_failure_at = Column(DateTime(timezone=True), nullable=True)
    last_error = Column(Text, nullable=True)
    total_successes = Column(Integer, nullable=False, default=0)
    total_failures = Column(Integer, nullable=False, default=0)
    total_attempts = Column(Integer, nullable=False, default=0)
    consecutive_failures = Column(Integer, nullable=False, default=0)
    retry_attempts = Column(Integer, nullable=False, default=0)
    next_retry_at = Column(DateTime(timezone=True), nullable=True)
    next_scheduled_at = Column(DateTime(timezone=True), nullable=True)
    schedule = Column(Text, nullable=False, default="[]")
    last_duration_ms = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
