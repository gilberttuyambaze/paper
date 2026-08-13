from core.database import Base
from sqlalchemy import Column, DateTime, Integer, String


class User_profiles(Base):
    __tablename__ = "user_profiles"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    user_id = Column(String, nullable=False)
    display_name = Column(String, nullable=False)
    role = Column(String, nullable=False)
    trust_score = Column(Integer, nullable=True)
    upload_count = Column(Integer, nullable=True)
    download_count = Column(Integer, nullable=True)
    institution_type = Column(String, nullable=True)
    university_name = Column(String, nullable=True)
    ur_student_code = Column(String, nullable=True)
    ur_verification_status = Column(String, nullable=True)
    profile_picture_key = Column(String, nullable=True)
    phone_number = Column(String, nullable=True)
    college_name = Column(String, nullable=True)
    department_name = Column(String, nullable=True)
    institution_id = Column(String, nullable=True)
    campus_id = Column(String, nullable=True)
    college_id = Column(String, nullable=True)
    school_id = Column(String, nullable=True)
    academic_department_id = Column(String, nullable=True)
    programme_id = Column(String, nullable=True)
    programme_submission_id = Column(Integer, nullable=True)
    programme_name_other = Column(String, nullable=True)
    programme_name_normalized = Column(String, nullable=True)
    academic_programme_status = Column(String, nullable=True)
    year_of_study = Column(String, nullable=True)
    bio = Column(String, nullable=True)
    requested_role = Column(String, nullable=True)
    requested_role_status = Column(String, nullable=True)
    account_status = Column(String, nullable=True)
    suspension_reason = Column(String, nullable=True)
    suspended_until = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=True)
