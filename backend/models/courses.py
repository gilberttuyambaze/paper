from sqlalchemy import Column, DateTime, Integer, String, Text, func

from core.database import Base


class Course(Base):
    __tablename__ = "courses"

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(100), nullable=True, index=True)
    normalized_code = Column(String(100), nullable=True, unique=True, index=True)
    name = Column(String(255), nullable=False, index=True)
    normalized_name = Column(String(255), nullable=False, unique=True, index=True)
    description = Column(Text, nullable=True)
    created_by = Column(String(255), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True, index=True)
