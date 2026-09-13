from models.base import Base
from sqlalchemy import Column, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.sql import func


class CommunicationEvent(Base):
    __tablename__ = "communication_events"
    __table_args__ = (UniqueConstraint("event_type", "paper_id", name="uq_communication_event_paper_type"),)

    id = Column(Integer, primary_key=True, index=True)
    event_type = Column(String(64), nullable=False, index=True)
    user_id = Column(String(255), nullable=True, index=True)
    paper_id = Column(Integer, nullable=True, index=True)
    recipient_hash = Column(String(64), nullable=False, index=True)
    status = Column(String(32), nullable=False, default="pending")
    provider_message_id = Column(String(255), nullable=True)
    retry_count = Column(Integer, nullable=False, default=0)
    delivery_started_at = Column(DateTime(timezone=True), nullable=True)
    error_category = Column(String(64), nullable=True)
    payload_json = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    sent_at = Column(DateTime(timezone=True), nullable=True)
