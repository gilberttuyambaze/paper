"""add durable page-level paper extraction evidence

Revision ID: q7r8s9t0u1v
Revises: p6q7r8s9t0u
"""

from alembic import op
import sqlalchemy as sa

revision = "q7r8s9t0u1v"
down_revision = "p6q7r8s9t0u"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "paper_page_extractions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("paper_id", sa.Integer(), nullable=False),
        sa.Column("processing_version", sa.String(length=64), nullable=False, server_default="v2_structured"),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("extraction_method", sa.String(length=32), nullable=True),
        sa.Column("extraction_confidence", sa.Float(), nullable=True),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("text_length", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.String(length=500), nullable=True),
        sa.Column("source_file_key", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("paper_id", "processing_version", "page_number", name="uq_paper_page_extraction_run"),
    )
    op.create_index("ix_paper_page_extractions_paper_id", "paper_page_extractions", ["paper_id"])
    op.create_index("ix_paper_page_extractions_status", "paper_page_extractions", ["status"])


def downgrade():
    op.drop_index("ix_paper_page_extractions_status", table_name="paper_page_extractions")
    op.drop_index("ix_paper_page_extractions_paper_id", table_name="paper_page_extractions")
    op.drop_table("paper_page_extractions")
