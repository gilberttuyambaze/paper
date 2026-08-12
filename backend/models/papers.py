from core.database import Base
from sqlalchemy import Boolean, Column, DateTime, Integer, String


class Papers(Base):
    __tablename__ = "papers"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    user_id = Column(String, nullable=False)
    title = Column(String, nullable=False)
    course_code = Column(String, nullable=False)
    course_name = Column(String, nullable=False)
    college = Column(String, nullable=False)
    department = Column(String, nullable=False)
    year = Column(Integer, nullable=False)
    paper_type = Column(String, nullable=False)
    lecturer = Column(String, nullable=True)
    description = Column(String, nullable=True)
    file_key = Column(String, nullable=True)
    file_drive_file_id = Column(String, nullable=True)
    file_storage_provider = Column(String, nullable=True)
    file_name = Column(String, nullable=True)
    file_size = Column(Integer, nullable=True)
    file_mime_type = Column(String, nullable=True)
    solution_key = Column(String, nullable=True)
    solution_drive_file_id = Column(String, nullable=True)
    solution_storage_provider = Column(String, nullable=True)
    solution_file_name = Column(String, nullable=True)
    solution_file_size = Column(Integer, nullable=True)
    solution_mime_type = Column(String, nullable=True)
    verification_status = Column(String, nullable=False)
    download_count = Column(Integer, nullable=True)
    report_count = Column(Integer, nullable=True)
    is_hidden = Column(Boolean, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=True)