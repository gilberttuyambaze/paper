"""Book catalogue, relationships, and immutable activity records."""

from sqlalchemy import Column, DateTime, Integer, String, Text, func

from core.database import Base


class Book(Base):
    __tablename__ = "books"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    title = Column(String(500), nullable=False, index=True)
    description = Column(Text, nullable=True)
    isbn = Column(String(32), nullable=True, index=True)
    edition = Column(String(100), nullable=True)
    publication_year = Column(Integer, nullable=True)
    language = Column(String(80), nullable=True)
    publisher = Column(String(255), nullable=True)
    category = Column(String(120), nullable=True, index=True)
    subject = Column(String(120), nullable=True, index=True)
    year_of_study = Column(String(50), nullable=True, index=True)
    semester = Column(String(50), nullable=True, index=True)
    status = Column(String(20), nullable=False, default="draft", index=True)
    visibility = Column(String(20), nullable=False, default="public", index=True)
    uploaded_by = Column(String(255), nullable=False, index=True)
    cover_key = Column(String(1024), nullable=True)
    cover_drive_file_id = Column(String(255), nullable=True)
    cover_storage_provider = Column(String(80), nullable=True)
    cover_drive_file_id = Column(String(255), nullable=True)
    cover_storage_provider = Column(String(80), nullable=True)
    cover_file_name = Column(String(500), nullable=True)
    cover_mime_type = Column(String(150), nullable=True)
    file_key = Column(String(1024), nullable=True)
    file_drive_file_id = Column(String(255), nullable=True)
    file_storage_provider = Column(String(80), nullable=True)
    file_drive_file_id = Column(String(255), nullable=True)
    file_storage_provider = Column(String(80), nullable=True)
    file_name = Column(String(500), nullable=True)
    file_mime_type = Column(String(150), nullable=True)
    file_size = Column(Integer, nullable=True)
    file_uploaded_at = Column(DateTime(timezone=True), nullable=True)
    download_count = Column(Integer, nullable=False, default=0, server_default="0", index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class BookAuthor(Base):
    __tablename__ = "book_authors"

    id = Column(Integer, primary_key=True, autoincrement=True)
    book_id = Column(Integer, nullable=False, index=True)
    author_id = Column(Integer, nullable=False, index=True)


class Author(Base):
    __tablename__ = "authors"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False, unique=True, index=True)
    profile_image = Column(String(1024), nullable=True)
    biography = Column(Text, nullable=True)
    institution = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class BookCourse(Base):
    __tablename__ = "book_courses"

    book_id = Column(Integer, primary_key=True, nullable=False, index=True)
    # The current project does not have a course table.  This is intentionally
    # a stable course identifier, ready to become a foreign key when one exists.
    course_id = Column(Integer, primary_key=True, nullable=False, index=True)


class Module(Base):
    __tablename__ = "modules"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False, index=True)
    normalized_name = Column(String(255), nullable=False, unique=True, index=True)
    code = Column(String(100), nullable=True, index=True)
    description = Column(Text, nullable=True)
    course_id = Column(Integer, nullable=True, index=True)
    created_by = Column(String(255), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class BookModule(Base):
    __tablename__ = "book_modules"

    id = Column(Integer, primary_key=True, autoincrement=True)
    book_id = Column(Integer, nullable=False, index=True)
    module_id = Column(Integer, nullable=False, index=True)


class BookActivity(Base):
    __tablename__ = "book_activities"

    id = Column(Integer, primary_key=True, autoincrement=True)
    book_id = Column(Integer, nullable=False, index=True)
    actor_id = Column(String(255), nullable=True, index=True)
    actor_role = Column(String(50), nullable=True)
    action = Column(String(80), nullable=False)
    detail = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)
