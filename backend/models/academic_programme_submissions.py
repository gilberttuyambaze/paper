from core.database import Base
from sqlalchemy import Column, DateTime, Integer, String


class AcademicProgrammeSubmission(Base):
    __tablename__ = "academic_programme_submissions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    institution_id = Column(String, nullable=False)
    campus_id = Column(String, nullable=False, index=True)
    college_id = Column(String, nullable=False, index=True)
    school_id = Column(String, nullable=False, index=True)
    academic_department_id = Column(String, nullable=True, index=True)
    raw_programme_name = Column(String(180), nullable=False)
    normalized_programme_name = Column(String(180), nullable=False, index=True)
    normalized_tokens = Column(String(300), nullable=False)
    submitted_by_user_id = Column(String, nullable=True, index=True)
    status = Column(String, nullable=False, default="unlisted", index=True)
    source = Column(String, nullable=False, default="profile")
    suggested_programme_id = Column(String, nullable=True)
    accepted_programme_id = Column(String, nullable=True)
    accepted_candidate_id = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), nullable=True)


class AcademicProgrammeAlias(Base):
    __tablename__ = "academic_programme_aliases"

    id = Column(Integer, primary_key=True, autoincrement=True)
    programme_id = Column(String, nullable=False, index=True)
    alias = Column(String(180), nullable=False)
    normalized_alias = Column(String(180), nullable=False, unique=True, index=True)
    source = Column(String, nullable=False, default="admin")
    verified_by = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=True)
