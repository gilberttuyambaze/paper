"""add book download counter

Revision ID: c3d4e5f6a7b8
Revises: c2d3e4f5a6b7
"""

from alembic import op
import sqlalchemy as sa


revision = "c3d4e5f6a7b8"
down_revision = "c2d3e4f5a6b7"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    columns = [c["name"] for c in insp.get_columns("books")]
    if "download_count" not in columns:
        op.add_column("books", sa.Column("download_count", sa.Integer(), nullable=False, server_default=sa.text("0")))
    indexes = [idx["name"] for idx in insp.get_indexes("books")]
    if "ix_books_download_count" not in indexes:
        op.create_index("ix_books_download_count", "books", ["download_count"])


def downgrade():
    op.drop_index("ix_books_download_count", table_name="books")
    op.drop_column("books", "download_count")
