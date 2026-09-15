from core.database import Base
from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, Text, UniqueConstraint, func


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
    semester = Column(String, nullable=True)
    examination_session = Column(String, nullable=True)
    year_of_study = Column(String, nullable=True, index=True)
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
    cover_key = Column(String, nullable=True)
    cover_drive_file_id = Column(String, nullable=True)
    cover_storage_provider = Column(String, nullable=True)
    cover_file_name = Column(String, nullable=True)
    cover_file_size = Column(Integer, nullable=True)
    cover_mime_type = Column(String, nullable=True)
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
    extraction_status = Column(String(32), nullable=True, default="completed")
    extraction_method = Column(String(32), nullable=True)
    extraction_quality = Column(Float, nullable=True)
    ocr_used = Column(Boolean, nullable=True, default=False)
    failed_pages = Column(Text, nullable=True)
    extraction_version = Column(String(32), nullable=True)
    # Extraction and vectorization are deliberately independent.  A paper with
    # durable passages remains useful to keyword retrieval during an embedding
    # provider outage.
    embedding_status = Column(String(32), nullable=True, default="PENDING")
    embedding_error = Column(String(500), nullable=True)
    retrieval_mode = Column(String(32), nullable=True, default="KEYWORD_ONLY")
    created_at = Column(DateTime(timezone=True), nullable=True)


class PaperPassage(Base):
    """Page-aware, independently retrievable source material for a paper."""
    __tablename__ = "paper_passages"
    __table_args__ = (UniqueConstraint("paper_id", "page_number", "passage_index", name="uq_paper_passage_position"),)

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    paper_id = Column(Integer, nullable=False, index=True)
    page_number = Column(Integer, nullable=False)
    passage_index = Column(Integer, nullable=False)
    question_number = Column(String(64), nullable=True, index=True)
    section_title = Column(String(255), nullable=True)
    extraction_method = Column(String(32), nullable=True)
    extraction_confidence = Column(Float, nullable=True)
    parent_passage_id = Column(Integer, nullable=True)
    text = Column(Text, nullable=False)
    text_hash = Column(String(64), nullable=False, index=True)
    course_code = Column(String, nullable=True, index=True)
    course_name = Column(String, nullable=True)
    academic_year = Column(Integer, nullable=True, index=True)
    source_file_key = Column(String, nullable=True)
    embedding_json = Column(Text, nullable=True)
    embedding_model = Column(String, nullable=True)
    embedding_provider = Column(String(32), nullable=True)
    embedding_dimension = Column(Integer, nullable=True)
    embedding_status = Column(String, nullable=False, default="pending")
    embedding_updated_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class PaperPageExtraction(Base):
    """Durable per-page extraction evidence for diagnosis and provenance."""
    __tablename__ = "paper_page_extractions"
    __table_args__ = (UniqueConstraint("paper_id", "processing_version", "page_number", name="uq_paper_page_extraction_run"),)

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    paper_id = Column(Integer, nullable=False, index=True)
    processing_version = Column(String(64), nullable=False, default="v2_structured")
    page_number = Column(Integer, nullable=False)
    status = Column(String(32), nullable=False, index=True)
    extraction_method = Column(String(32), nullable=True)
    extraction_confidence = Column(Float, nullable=True)
    text = Column(Text, nullable=True)
    text_length = Column(Integer, nullable=False, default=0)
    error_message = Column(String(500), nullable=True)
    source_file_key = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class PaperQuestion(Base):
    __tablename__ = "paper_questions"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    paper_id = Column(Integer, nullable=False, index=True)
    passage_id = Column(Integer, nullable=True, index=True)
    question_number = Column(String, nullable=True)
    text = Column(Text, nullable=False)
    page_start = Column(Integer, nullable=False)
    page_end = Column(Integer, nullable=False)
    course_code = Column(String, nullable=True, index=True)
    academic_year = Column(Integer, nullable=True)
    classification_status = Column(String, nullable=False, default="pending")
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class QuestionTopic(Base):
    __tablename__ = "question_topics"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    question_id = Column(Integer, nullable=False, index=True)
    topic = Column(String, nullable=False, index=True)
    subtopic = Column(String, nullable=True)
    confidence = Column(Integer, nullable=False)
    source = Column(String, nullable=False)
    classifier_version = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class QuestionClassification(Base):
    __tablename__ = "question_classifications"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    question_id = Column(Integer, nullable=False, index=True)
    question_types = Column(String, nullable=True)
    type_confidence = Column(Integer, nullable=True)
    difficulty = Column(String, nullable=False, default="Unknown")
    difficulty_confidence = Column(Integer, nullable=True)
    difficulty_method = Column(String, nullable=False, default="heuristic")
    classifier_version = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class QuestionAttempt(Base):
    __tablename__ = "question_attempts"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(String, nullable=False, index=True)
    question_id = Column(Integer, nullable=False, index=True)
    is_correct = Column(Boolean, nullable=True)
    score = Column(Integer, nullable=True)
    time_taken_seconds = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
