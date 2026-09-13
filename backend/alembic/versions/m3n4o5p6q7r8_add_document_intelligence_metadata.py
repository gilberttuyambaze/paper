"""add document intelligence and extraction metadata to papers and paper_passages

Revision ID: m3n4o5p6q7r8
Revises: l2m3n4o5p6q7
"""
from alembic import op
import sqlalchemy as sa

revision = "m3n4o5p6q7r8"
down_revision = "l2m3n4o5p6q7"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "papers" in tables:
        columns = {col["name"] for col in inspector.get_columns("papers")}
        if "extraction_status" not in columns:
            op.add_column("papers", sa.Column("extraction_status", sa.String(length=32), nullable=True, server_default="completed"))
        if "extraction_method" not in columns:
            op.add_column("papers", sa.Column("extraction_method", sa.String(length=32), nullable=True))
        if "extraction_quality" not in columns:
            op.add_column("papers", sa.Column("extraction_quality", sa.Float(), nullable=True))
        if "ocr_used" not in columns:
            op.add_column("papers", sa.Column("ocr_used", sa.Boolean(), nullable=True, server_default=sa.text("false")))
        if "failed_pages" not in columns:
            op.add_column("papers", sa.Column("failed_pages", sa.Text(), nullable=True))
        if "extraction_version" not in columns:
            op.add_column("papers", sa.Column("extraction_version", sa.String(length=32), nullable=True))

    if "paper_passages" in tables:
        columns = {col["name"] for col in inspector.get_columns("paper_passages")}
        if "question_number" not in columns:
            op.add_column("paper_passages", sa.Column("question_number", sa.String(length=64), nullable=True))
            try:
                op.create_index("ix_paper_passages_question_number", "paper_passages", ["question_number"], unique=False)
            except Exception:
                pass
        if "section_title" not in columns:
            op.add_column("paper_passages", sa.Column("section_title", sa.String(length=255), nullable=True))
        if "extraction_method" not in columns:
            op.add_column("paper_passages", sa.Column("extraction_method", sa.String(length=32), nullable=True))
        if "extraction_confidence" not in columns:
            op.add_column("paper_passages", sa.Column("extraction_confidence", sa.Float(), nullable=True))
        if "parent_passage_id" not in columns:
            op.add_column("paper_passages", sa.Column("parent_passage_id", sa.Integer(), nullable=True))


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "paper_passages" in tables:
        columns = {col["name"] for col in inspector.get_columns("paper_passages")}
        if "parent_passage_id" in columns:
            op.drop_column("paper_passages", "parent_passage_id")
        if "extraction_confidence" in columns:
            op.drop_column("paper_passages", "extraction_confidence")
        if "extraction_method" in columns:
            op.drop_column("paper_passages", "extraction_method")
        if "section_title" in columns:
            op.drop_column("paper_passages", "section_title")
        if "question_number" in columns:
            try:
                op.drop_index("ix_paper_passages_question_number", table_name="paper_passages")
            except Exception:
                pass
            op.drop_column("paper_passages", "question_number")

    if "papers" in tables:
        columns = {col["name"] for col in inspector.get_columns("papers")}
        if "extraction_version" in columns:
            op.drop_column("papers", "extraction_version")
        if "failed_pages" in columns:
            op.drop_column("papers", "failed_pages")
        if "ocr_used" in columns:
            op.drop_column("papers", "ocr_used")
        if "extraction_quality" in columns:
            op.drop_column("papers", "extraction_quality")
        if "extraction_method" in columns:
            op.drop_column("papers", "extraction_method")
        if "extraction_status" in columns:
            op.drop_column("papers", "extraction_status")
