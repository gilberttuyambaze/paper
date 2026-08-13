"""add normalized academic context fields

Revision ID: a2b8c1d93f41
Revises: f97c229ef883
"""
from alembic import op
import sqlalchemy as sa

revision = "a2b8c1d93f41"
down_revision = "f97c229ef883"
branch_labels = None
depends_on = None

PROFILE_COLUMNS = ["institution_id", "campus_id", "college_id", "school_id", "academic_department_id", "programme_id", "programme_submission_id", "programme_name_other", "programme_name_normalized", "academic_programme_status"]
PAPER_COLUMNS = PROFILE_COLUMNS + ["semester", "examination_session"]


def _column(name):
    # Submission primary keys are integers in the application models.
    return sa.Column(name, sa.Integer() if name == "programme_submission_id" else sa.String(), nullable=True)

def upgrade():
    for column in PROFILE_COLUMNS:
        op.add_column("user_profiles", _column(column))
    for column in PAPER_COLUMNS:
        op.add_column("papers", _column(column))
    op.create_table("academic_programme_submissions", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("institution_id", sa.String(), nullable=False), sa.Column("campus_id", sa.String(), nullable=False), sa.Column("college_id", sa.String(), nullable=False), sa.Column("school_id", sa.String(), nullable=False), sa.Column("academic_department_id", sa.String(), nullable=True), sa.Column("raw_programme_name", sa.String(180), nullable=False), sa.Column("normalized_programme_name", sa.String(180), nullable=False), sa.Column("normalized_tokens", sa.String(300), nullable=False), sa.Column("submitted_by_user_id", sa.String(), nullable=True), sa.Column("status", sa.String(), nullable=False), sa.Column("suggested_programme_id", sa.String(), nullable=True), sa.Column("accepted_programme_id", sa.String(), nullable=True), sa.Column("accepted_candidate_id", sa.Integer(), nullable=True), sa.Column("created_at", sa.DateTime(timezone=True), nullable=True), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_programme_submission_context", "academic_programme_submissions", ["campus_id", "college_id", "school_id", "normalized_programme_name"], unique=False)
    op.create_table("academic_programme_aliases", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("programme_id", sa.String(), nullable=False), sa.Column("alias", sa.String(180), nullable=False), sa.Column("normalized_alias", sa.String(180), nullable=False, unique=True), sa.Column("source", sa.String(), nullable=False), sa.Column("verified_by", sa.String(), nullable=True), sa.Column("created_at", sa.DateTime(timezone=True), nullable=True))

def downgrade():
    op.drop_table("academic_programme_aliases")
    op.drop_index("ix_programme_submission_context", table_name="academic_programme_submissions")
    op.drop_table("academic_programme_submissions")
    for column in reversed(PAPER_COLUMNS): op.drop_column("papers", column)
    for column in reversed(PROFILE_COLUMNS): op.drop_column("user_profiles", column)
