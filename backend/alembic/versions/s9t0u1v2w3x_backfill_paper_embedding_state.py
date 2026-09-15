"""backfill durable embedding state from existing passages

Revision ID: s9t0u1v2w3x
Revises: r8s9t0u1v2w
"""

from alembic import op

revision = "s9t0u1v2w3x"
down_revision = "r8s9t0u1v2w"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        UPDATE papers p
        SET embedding_status = CASE
                WHEN EXISTS (SELECT 1 FROM paper_passages pp WHERE pp.paper_id = p.id AND pp.embedding_status = 'ready') THEN 'READY'
                WHEN EXISTS (SELECT 1 FROM paper_passages pp WHERE pp.paper_id = p.id AND pp.embedding_status = 'failed') THEN 'FAILED'
                WHEN EXISTS (SELECT 1 FROM paper_passages pp WHERE pp.paper_id = p.id) THEN 'PENDING'
                ELSE COALESCE(p.embedding_status, 'PENDING')
            END,
            retrieval_mode = CASE
                WHEN EXISTS (SELECT 1 FROM paper_passages pp WHERE pp.paper_id = p.id AND pp.embedding_status = 'ready') THEN 'HYBRID'
                ELSE 'KEYWORD_ONLY'
            END
    """)


def downgrade():
    pass
