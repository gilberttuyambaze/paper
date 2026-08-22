"""add performance indexes

Revision ID: 9c4b5a6d7e8f
Revises: f6a7b8c9d0e1
"""
from alembic import op
import sqlalchemy as sa

revision = "9c4b5a6d7e8f"
down_revision = "f6a7b8c9d0e1"
branch_labels = None
depends_on = None


def upgrade():
    """Create performance indexes using CONCURRENTLY outside transaction."""
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        inspector = sa.inspect(bind)
        existing = {index["name"] for index in inspector.get_indexes("user_profiles")}
        existing |= {index["name"] for index in inspector.get_indexes("papers")}
        indexes = (
            ("ix_user_profiles_user_id", "user_profiles", ["user_id"], None),
            ("ix_papers_public_download_count", "papers", ["download_count"], "is_hidden IS NOT TRUE AND verification_status = 'verified'"),
            ("ix_papers_institution_campus_created", "papers", ["institution_id", "campus_id", "created_at"], "is_hidden IS NOT TRUE AND verification_status = 'verified'"),
            ("ix_papers_programme_download", "papers", ["programme_id", "download_count"], "is_hidden IS NOT TRUE AND verification_status = 'verified' AND programme_id IS NOT NULL"),
        )
        for name, table, columns, predicate in indexes:
            if name not in existing:
                kwargs = {"sqlite_where": sa.text(predicate)} if predicate else {}
                op.create_index(name, table, columns, **kwargs)
        return

    ctx = op.get_context()
    # Run CONCURRENTLY operations outside Alembic's transactional context
    with ctx.autocommit_block():
        # 1. user_profiles.user_id
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_user_profiles_user_id ON user_profiles (user_id)"
        )

        # 2. public papers ordered by download_count
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_papers_public_download_count ON papers (download_count DESC) WHERE (is_hidden IS NOT TRUE AND verification_status = 'verified')"
        )

        # 3. institution/campus + created_at (recent papers)
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_papers_institution_campus_created ON papers (institution_id, campus_id, created_at DESC) WHERE (is_hidden IS NOT TRUE AND verification_status = 'verified')"
        )

        # 4. programme-specific popular papers
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_papers_programme_download ON papers (programme_id, download_count DESC) WHERE (is_hidden IS NOT TRUE AND verification_status = 'verified' AND programme_id IS NOT NULL)"
        )


def downgrade():
    """Drop the created indexes using CONCURRENTLY."""
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        for name, table in (
            ("ix_user_profiles_user_id", "user_profiles"),
            ("ix_papers_public_download_count", "papers"),
            ("ix_papers_institution_campus_created", "papers"),
            ("ix_papers_programme_download", "papers"),
        ):
            if name in {index["name"] for index in sa.inspect(bind).get_indexes(table)}:
                op.drop_index(name, table_name=table)
        return

    ctx = op.get_context()
    with ctx.autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_user_profiles_user_id")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_papers_public_download_count")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_papers_institution_campus_created")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_papers_programme_download")
