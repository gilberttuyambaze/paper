"""remove Book soft-delete columns

Revision ID: c4d5e6f7a8b9
Revises: b2c3d4e5f6a7
"""

from alembic import op
import sqlalchemy as sa

revision = "c4d5e6f7a8b9"
down_revision = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("books")}
    indexes = {index["name"] for index in inspector.get_indexes("books")}
    if bind.dialect.name == "postgresql":
        op.execute("DROP POLICY IF EXISTS book_courses_select_policy ON book_courses")
        op.execute("DROP POLICY IF EXISTS book_modules_select_policy ON book_modules")
    if "ix_books_deleted_at" in indexes:
        op.drop_index("ix_books_deleted_at", table_name="books")
    if "deleted_by" in columns:
        op.drop_column("books", "deleted_by")
    if "deleted_at" in columns:
        op.drop_column("books", "deleted_at")


def downgrade():
    op.add_column("books", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("books", sa.Column("deleted_by", sa.String(255), nullable=True))
    op.create_index("ix_books_deleted_at", "books", ["deleted_at"])
