"""add truthful paper processing progress and heartbeat

Revision ID: p6q7r8s9t0u
Revises: o5p6q7r8s9t
"""

from alembic import op
import sqlalchemy as sa

revision = "p6q7r8s9t0u"
down_revision = "o5p6q7r8s9t"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("paper_processing_jobs", sa.Column("current_stage", sa.String(length=64), nullable=True))
    op.add_column("paper_processing_jobs", sa.Column("pages_total", sa.Integer(), nullable=True))
    op.add_column("paper_processing_jobs", sa.Column("pages_completed", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("paper_processing_jobs", sa.Column("percent_complete", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("paper_processing_jobs", sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("paper_processing_jobs", sa.Column("metrics_json", sa.Text(), nullable=True))
    op.create_index("ix_paper_processing_jobs_heartbeat_at", "paper_processing_jobs", ["heartbeat_at"])


def downgrade():
    op.drop_index("ix_paper_processing_jobs_heartbeat_at", table_name="paper_processing_jobs")
    op.drop_column("paper_processing_jobs", "metrics_json")
    op.drop_column("paper_processing_jobs", "heartbeat_at")
    op.drop_column("paper_processing_jobs", "percent_complete")
    op.drop_column("paper_processing_jobs", "pages_completed")
    op.drop_column("paper_processing_jobs", "pages_total")
    op.drop_column("paper_processing_jobs", "current_stage")
