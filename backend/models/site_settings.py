from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text

from models.base import Base


class SiteSettings(Base):
    __tablename__ = "site_settings"

    id = Column(Integer, primary_key=True, default=1)
    maintenance_mode = Column(Boolean, nullable=False, default=False)
    maintenance_message = Column(Text, nullable=False, default="The site is temporarily unavailable. We are performing scheduled maintenance. Please try again later.")
    upload_access_mode = Column(String(32), nullable=False, default="selected_roles")
    upload_roles = Column(Text, nullable=False, default='["admin", "cp"]')
    allowed_resource_types = Column(Text, nullable=False, default='["book", "paper"]')
    heartbeat_enabled = Column(Boolean, nullable=False, default=True)
    heartbeat_min_weekly_checks = Column(Integer, nullable=False, default=2)
    heartbeat_max_weekly_checks = Column(Integer, nullable=False, default=3)
    heartbeat_retry_delay_hours = Column(Integer, nullable=False, default=6)
    heartbeat_max_retry_attempts = Column(Integer, nullable=False, default=2)
    heartbeat_retry_enabled = Column(Boolean, nullable=False, default=True)
    heartbeat_retry_jitter_minutes = Column(Integer, nullable=False, default=30)
    heartbeat_run_on_startup = Column(Boolean, nullable=False, default=True)
    heartbeat_week_start = Column(DateTime(timezone=True), nullable=True)
    heartbeat_schedule = Column(Text, nullable=False, default="[]")
    heartbeat_completed_checks = Column(Integer, nullable=False, default=0)
    heartbeat_retry_attempts = Column(Integer, nullable=False, default=0)
    heartbeat_next_attempt_at = Column(DateTime(timezone=True), nullable=True)
    heartbeat_scheduler_status = Column(String(32), nullable=False, default="stopped")
