"""add structured question classification metadata

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
"""
from alembic import op
import sqlalchemy as sa
revision = "f6a7b8c9d0e1"; down_revision = "e5f6a7b8c9d0"; branch_labels = None; depends_on = None
def upgrade():
    op.create_table("paper_questions", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("paper_id", sa.Integer(), nullable=False), sa.Column("passage_id", sa.Integer()), sa.Column("question_number", sa.String()), sa.Column("text", sa.Text(), nullable=False), sa.Column("page_start", sa.Integer(), nullable=False), sa.Column("page_end", sa.Integer(), nullable=False), sa.Column("course_code", sa.String()), sa.Column("academic_year", sa.Integer()), sa.Column("classification_status", sa.String(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True)))
    op.create_table("question_topics", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("question_id", sa.Integer(), nullable=False), sa.Column("topic", sa.String(), nullable=False), sa.Column("subtopic", sa.String()), sa.Column("confidence", sa.Integer(), nullable=False), sa.Column("source", sa.String(), nullable=False), sa.Column("classifier_version", sa.String(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True)))
    op.create_table("question_classifications", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("question_id", sa.Integer(), nullable=False), sa.Column("question_types", sa.String()), sa.Column("type_confidence", sa.Integer()), sa.Column("difficulty", sa.String(), nullable=False), sa.Column("difficulty_confidence", sa.Integer()), sa.Column("difficulty_method", sa.String(), nullable=False), sa.Column("classifier_version", sa.String(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True)))
    op.create_table("question_attempts", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("user_id", sa.String(), nullable=False), sa.Column("question_id", sa.Integer(), nullable=False), sa.Column("is_correct", sa.Boolean()), sa.Column("score", sa.Integer()), sa.Column("time_taken_seconds", sa.Integer()), sa.Column("created_at", sa.DateTime(timezone=True)))
def downgrade():
    op.drop_table("question_attempts"); op.drop_table("question_classifications"); op.drop_table("question_topics"); op.drop_table("paper_questions")
