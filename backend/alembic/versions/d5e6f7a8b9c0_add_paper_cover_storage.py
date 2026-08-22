"""Add Paper cover storage metadata."""

from alembic import op
import sqlalchemy as sa

revision = "d5e6f7a8b9c0"
down_revision = "c4d5e6f7a8b9"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    existing = {column["name"] for column in sa.inspect(bind).get_columns("papers")}
    columns = [
        sa.Column("cover_key", sa.String(), nullable=True),
        sa.Column("cover_drive_file_id", sa.String(), nullable=True),
        sa.Column("cover_storage_provider", sa.String(), nullable=True),
        sa.Column("cover_file_name", sa.String(), nullable=True),
        sa.Column("cover_file_size", sa.Integer(), nullable=True),
        sa.Column("cover_mime_type", sa.String(), nullable=True),
    ]
    for column in columns:
        if column.name not in existing:
            op.add_column("papers", column)


def downgrade():
    bind = op.get_bind()
    existing = {column["name"] for column in sa.inspect(bind).get_columns("papers")}
    for name in ("cover_mime_type", "cover_file_size", "cover_file_name", "cover_storage_provider", "cover_drive_file_id", "cover_key"):
        if name in existing:
            op.drop_column("papers", name)
