"""add durable paper processing jobs

Revision ID: n4o5p6q7r8s
Revises: m3n4o5p6q7r8
"""

from alembic import op
import sqlalchemy as sa

revision = "n4o5p6q7r8s"
down_revision = "m3n4o5p6q7r8"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "paper_processing_jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("paper_id", sa.Integer(), nullable=False),
        sa.Column("processing_version", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="QUEUED"),
        sa.Column("progress_message", sa.String(length=255)),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("error_summary", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("paper_id", "processing_version", name="uq_paper_processing_job_run"),
    )
    op.create_index("ix_paper_processing_jobs_paper_id", "paper_processing_jobs", ["paper_id"])
    op.create_index("ix_paper_processing_jobs_status", "paper_processing_jobs", ["status"])


def downgrade():
    op.drop_index("ix_paper_processing_jobs_status", table_name="paper_processing_jobs")
    op.drop_index("ix_paper_processing_jobs_paper_id", table_name="paper_processing_jobs")
    op.drop_table("paper_processing_jobs")
