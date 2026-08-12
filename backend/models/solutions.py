from core.database import Base
from sqlalchemy import Boolean, Column, DateTime, Integer, String


class Solutions(Base):
    __tablename__ = "solutions"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    user_id = Column(String, nullable=False)
    paper_id = Column(Integer, nullable=False)
    content = Column(String, nullable=False)
    file_key = Column(String, nullable=True)
    drive_file_id = Column(String, nullable=True)
    storage_provider = Column(String, nullable=True)
    file_name = Column(String, nullable=True)
    file_size = Column(Integer, nullable=True)
    mime_type = Column(String, nullable=True)
    upvotes = Column(Integer, nullable=True)
    is_best = Column(Boolean, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=True)