"""track provider for each passage embedding space

Revision ID: t0u1v2w3x4y
Revises: s9t0u1v2w3x
"""

from alembic import op
import sqlalchemy as sa

revision = "t0u1v2w3x4y"
down_revision = "s9t0u1v2w3x"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("paper_passages", sa.Column("embedding_provider", sa.String(length=32), nullable=True))


def downgrade():
    op.drop_column("paper_passages", "embedding_provider")
