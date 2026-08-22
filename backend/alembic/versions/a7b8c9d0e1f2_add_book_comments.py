"""Allow discussions to be attached to books."""

from alembic import op
import sqlalchemy as sa


revision = "a7b8c9d0e1f2"
down_revision = ("9c4b5a6d7e8f", "c3d4e5f6a7b8")
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    columns = [c["name"] for c in insp.get_columns("comments")]

    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("comments") as batch_op:
            batch_op.alter_column("paper_id", existing_type=sa.Integer(), nullable=True)
    else:
        op.alter_column("comments", "paper_id", existing_type=sa.Integer(), nullable=True)
    if "book_id" not in columns:
        op.add_column("comments", sa.Column("book_id", sa.Integer(), nullable=True))

    indexes = [idx["name"] for idx in insp.get_indexes("comments")]
    if "ix_comments_book_id" not in indexes:
        op.create_index("ix_comments_book_id", "comments", ["book_id"], unique=False)


def downgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    indexes = [idx["name"] for idx in insp.get_indexes("comments")]
    if "ix_comments_book_id" in indexes:
        op.drop_index("ix_comments_book_id", table_name="comments")
    columns = [c["name"] for c in insp.get_columns("comments")]
    if "book_id" in columns:
        op.drop_column("comments", "book_id")
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("comments") as batch_op:
            batch_op.alter_column("paper_id", existing_type=sa.Integer(), nullable=False)
    else:
        op.alter_column("comments", "paper_id", existing_type=sa.Integer(), nullable=False)