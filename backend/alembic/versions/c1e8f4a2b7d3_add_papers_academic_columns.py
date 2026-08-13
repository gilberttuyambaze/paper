"""add missing academic taxonomy columns to papers (non-destructive)

Revision ID: c1e8f4a2b7d3
Revises: b3a9c5d4e678
"""
from alembic import op
import sqlalchemy as sa

revision = "c1e8f4a2b7d3"
down_revision = "b3a9c5d4e678"
branch_labels = None
depends_on = None


def upgrade():
    # This database has historically had partially applied taxonomy changes.
    # Inspect before adding so the repair is safe both for the known production
    # state and for databases that already have a subset of these columns.
    existing = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("papers")}
    columns = (
        sa.Column("institution_id", sa.String(), nullable=True),
        sa.Column("campus_id", sa.String(), nullable=True),
        sa.Column("college_id", sa.String(), nullable=True),
        sa.Column("school_id", sa.String(), nullable=True),
        sa.Column("academic_department_id", sa.String(), nullable=True),
        sa.Column("programme_id", sa.String(), nullable=True),
        sa.Column("programme_submission_id", sa.Integer(), nullable=True),
        sa.Column("programme_name_other", sa.String(), nullable=True),
        sa.Column("programme_name_normalized", sa.String(), nullable=True),
        sa.Column("academic_programme_status", sa.String(), nullable=True),
        sa.Column("semester", sa.String(), nullable=True),
        sa.Column("examination_session", sa.String(), nullable=True),
    )
    for column in columns:
        if column.name not in existing:
            op.add_column("papers", column)


def downgrade():
    # This rollback drops data; it is retained for Alembic completeness and must
    # not be used as an operational recovery path in production.
    op.execute("""
    ALTER TABLE papers
      DROP COLUMN IF EXISTS examination_session,
      DROP COLUMN IF EXISTS semester,
      DROP COLUMN IF EXISTS academic_programme_status,
      DROP COLUMN IF EXISTS programme_name_normalized,
      DROP COLUMN IF EXISTS programme_name_other,
      DROP COLUMN IF EXISTS programme_submission_id,
      DROP COLUMN IF EXISTS programme_id,
      DROP COLUMN IF EXISTS academic_department_id,
      DROP COLUMN IF EXISTS school_id,
      DROP COLUMN IF EXISTS college_id,
      DROP COLUMN IF EXISTS campus_id,
      DROP COLUMN IF EXISTS institution_id;
    """)
