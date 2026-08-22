"""Allow discussions to be attached to books."""

from alembic import op
import sqlalchemy as sa


revision = "a7b8c9d0e1f2"
down_revision = ("9c4b5a6d7e8f", "c3d4e5f6a7b8")
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column("comments", "paper_id", existing_type=sa.Integer(), nullable=True)
    op.add_column("comments", sa.Column("book_id", sa.Integer(), nullable=True))
    op.create_index("ix_comments_book_id", "comments", ["book_id"], unique=False)


def downgrade():
    op.drop_index("ix_comments_book_id", table_name="comments")
    op.drop_column("comments", "book_id")
    op.alter_column("comments", "paper_id", existing_type=sa.Integer(), nullable=False)