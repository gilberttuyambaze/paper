"""add book management

Revision ID: b1c2d3e4f5a6
Revises: 9c4b5a6d7e8f
"""

from alembic import op
import sqlalchemy as sa

revision = "b1c2d3e4f5a6"
down_revision = "9c4b5a6d7e8f"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existing_tables = set(insp.get_table_names())

    if "books" not in existing_tables:
        op.create_table("books",
            sa.Column("id", sa.Integer(), primary_key=True), sa.Column("title", sa.String(500), nullable=False),
            sa.Column("description", sa.Text()), sa.Column("isbn", sa.String(32)), sa.Column("edition", sa.String(100)),
            sa.Column("publication_year", sa.Integer()), sa.Column("language", sa.String(80)), sa.Column("publisher", sa.String(255)),
            sa.Column("category", sa.String(120)), sa.Column("subject", sa.String(120)), sa.Column("status", sa.String(20), nullable=False),
            sa.Column("visibility", sa.String(20), nullable=False), sa.Column("uploaded_by", sa.String(255), nullable=False),
            sa.Column("cover_key", sa.String(1024)), sa.Column("cover_file_name", sa.String(500)), sa.Column("cover_mime_type", sa.String(150)),
            sa.Column("file_key", sa.String(1024)), sa.Column("file_name", sa.String(500)), sa.Column("file_mime_type", sa.String(150)), sa.Column("file_size", sa.Integer()), sa.Column("file_uploaded_at", sa.DateTime(timezone=True)),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("deleted_at", sa.DateTime(timezone=True)), sa.Column("deleted_by", sa.String(255)))
        for name, column in [("ix_books_title", "title"), ("ix_books_isbn", "isbn"), ("ix_books_category", "category"), ("ix_books_subject", "subject"), ("ix_books_status", "status"), ("ix_books_visibility", "visibility"), ("ix_books_uploaded_by", "uploaded_by"), ("ix_books_created_at", "created_at"), ("ix_books_deleted_at", "deleted_at")]:
            op.create_index(name, "books", [column])

    if "authors" not in existing_tables:
        op.create_table("authors", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("name", sa.String(255), nullable=False, unique=True), sa.Column("profile_image", sa.String(1024)), sa.Column("biography", sa.Text()), sa.Column("institution", sa.String(255)), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
        op.create_index("ix_authors_name", "authors", ["name"])

    if "book_authors" not in existing_tables:
        op.create_table("book_authors", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("book_id", sa.Integer(), nullable=False), sa.Column("author_id", sa.Integer(), nullable=False))
        op.create_index("ix_book_authors_book_id", "book_authors", ["book_id"]); op.create_index("ix_book_authors_author_id", "book_authors", ["author_id"])

    if "book_courses" not in existing_tables:
        op.create_table("book_courses", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("book_id", sa.Integer(), nullable=False), sa.Column("course_id", sa.String(255), nullable=False))
        op.create_index("ix_book_courses_book_id", "book_courses", ["book_id"]); op.create_index("ix_book_courses_course_id", "book_courses", ["course_id"])

    if "modules" not in existing_tables:
        op.create_table("modules", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("name", sa.String(255), nullable=False), sa.Column("normalized_name", sa.String(255), nullable=False, unique=True), sa.Column("code", sa.String(100)), sa.Column("description", sa.Text()), sa.Column("course_id", sa.String(255)), sa.Column("created_by", sa.String(255), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
        op.create_index("ix_modules_name", "modules", ["name"]); op.create_index("ix_modules_normalized_name", "modules", ["normalized_name"]); op.create_index("ix_modules_code", "modules", ["code"]); op.create_index("ix_modules_course_id", "modules", ["course_id"]); op.create_index("ix_modules_created_by", "modules", ["created_by"])

    if "book_modules" not in existing_tables:
        op.create_table("book_modules", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("book_id", sa.Integer(), nullable=False), sa.Column("module_id", sa.Integer(), nullable=False))
        op.create_index("ix_book_modules_book_id", "book_modules", ["book_id"]); op.create_index("ix_book_modules_module_id", "book_modules", ["module_id"])

    if "book_activities" not in existing_tables:
        op.create_table("book_activities", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("book_id", sa.Integer(), nullable=False), sa.Column("actor_id", sa.String(255)), sa.Column("actor_role", sa.String(50)), sa.Column("action", sa.String(80), nullable=False), sa.Column("detail", sa.Text()), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
        op.create_index("ix_book_activities_book_id", "book_activities", ["book_id"]); op.create_index("ix_book_activities_actor_id", "book_activities", ["actor_id"]); op.create_index("ix_book_activities_created_at", "book_activities", ["created_at"])


def downgrade():
    op.drop_table("book_activities"); op.drop_table("book_modules"); op.drop_table("modules"); op.drop_table("book_courses"); op.drop_table("book_authors"); op.drop_table("authors"); op.drop_table("books")
