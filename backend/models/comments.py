from core.database import Base
from sqlalchemy import Column, DateTime, Integer, String


class Comments(Base):
    __tablename__ = "comments"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    user_id = Column(String, nullable=False)
    paper_id = Column(Integer, nullable=True)
    book_id = Column(Integer, nullable=True)
    content = Column(String, nullable=False)
    parent_id = Column(Integer, nullable=True)
    upvotes = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=True)