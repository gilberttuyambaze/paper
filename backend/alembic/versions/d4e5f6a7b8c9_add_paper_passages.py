"""add page-aware paper passages for hybrid retrieval

Revision ID: d4e5f6a7b8c9
Revises: a2b8c1d93f41
"""
from alembic import op
import sqlalchemy as sa

revision = "d4e5f6a7b8c9"
down_revision = "a2b8c1d93f41"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "paper_passages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("paper_id", sa.Integer(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("passage_index", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("text_hash", sa.String(64), nullable=False),
        sa.Column("course_code", sa.String(), nullable=True),
        sa.Column("course_name", sa.String(), nullable=True),
        sa.Column("academic_year", sa.Integer(), nullable=True),
        sa.Column("source_file_key", sa.String(), nullable=True),
        sa.Column("embedding_json", sa.Text(), nullable=True),
        sa.Column("embedding_model", sa.String(), nullable=True),
        sa.Column("embedding_dimension", sa.Integer(), nullable=True),
        sa.Column("embedding_status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("embedding_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("paper_id", "page_number", "passage_index", name="uq_paper_passage_position"),
    )
    op.create_index("ix_paper_passages_paper_id", "paper_passages", ["paper_id"])
    op.create_index("ix_paper_passages_course_code", "paper_passages", ["course_code"])
    op.create_index("ix_paper_passages_text_hash", "paper_passages", ["text_hash"])
    # PostgreSQL production deployments get a pgvector HNSW index. SQLite and
    # managed databases without the extension keep the JSON/cosine fallback.
    if op.get_bind().dialect.name == "postgresql":
        op.execute("""
        DO $$
        BEGIN
          BEGIN
            CREATE EXTENSION IF NOT EXISTS vector;
          EXCEPTION WHEN insufficient_privilege THEN
            RAISE NOTICE 'pgvector unavailable; using portable JSON embeddings';
          END;
          IF EXISTS (SELECT 1 FROM pg_type WHERE typname = 'vector') THEN
            EXECUTE 'ALTER TABLE paper_passages ADD COLUMN IF NOT EXISTS embedding_vector vector(1536)';
            IF NOT EXISTS (SELECT 1 FROM pg_class WHERE relname = 'ix_paper_passages_embedding_hnsw') THEN
              EXECUTE 'CREATE INDEX ix_paper_passages_embedding_hnsw ON paper_passages USING hnsw (embedding_vector vector_cosine_ops)';
            END IF;
          END IF;
        END $$;
        """)


def downgrade():
    op.drop_table("paper_passages")
