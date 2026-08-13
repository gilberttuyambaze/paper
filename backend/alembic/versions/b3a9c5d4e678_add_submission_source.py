"""add source to academic_programme_submissions

Revision ID: b3a9c5d4e678
Revises: a2b8c1d93f41
"""
from alembic import op
import sqlalchemy as sa

revision = "b3a9c5d4e678"
down_revision = "a2b8c1d93f41"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('academic_programme_submissions', sa.Column('source', sa.String(), nullable=False, server_default='profile'))
    # remove server_default if desired in application-level migrations


def downgrade():
    op.drop_column('academic_programme_submissions', 'source')
