"""add durable paper embedding and retrieval state

Revision ID: r8s9t0u1v2w
Revises: q7r8s9t0u1v
"""

from alembic import op
import sqlalchemy as sa

revision = "r8s9t0u1v2w"
down_revision = "q7r8s9t0u1v"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("papers", sa.Column("embedding_status", sa.String(length=32), nullable=True, server_default="PENDING"))
    op.add_column("papers", sa.Column("embedding_error", sa.String(length=500), nullable=True))
    op.add_column("papers", sa.Column("retrieval_mode", sa.String(length=32), nullable=True, server_default="KEYWORD_ONLY"))


def downgrade():
    op.drop_column("papers", "retrieval_mode")
    op.drop_column("papers", "embedding_error")
    op.drop_column("papers", "embedding_status")
