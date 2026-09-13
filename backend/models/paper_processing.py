"""Durable work records for Paper Intelligence processing.

Workers claim these records from the database; a web request never owns the
long-running extraction work.
"""

from core.database import Base
from sqlalchemy import Column, DateTime, Integer, String, Text, UniqueConstraint, func


class PaperProcessingJob(Base):
    __tablename__ = "paper_processing_jobs"
    __table_args__ = (UniqueConstraint("paper_id", "processing_version", name="uq_paper_processing_job_run"),)

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    paper_id = Column(Integer, nullable=False, index=True)
    processing_version = Column(String(64), nullable=False, default="v2_structured")
    status = Column(String(32), nullable=False, default="QUEUED", index=True)
    progress_message = Column(String(255), nullable=True)
    attempt_count = Column(Integer, nullable=False, default=0)
    max_attempts = Column(Integer, nullable=False, default=3)
    error_summary = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=True)
