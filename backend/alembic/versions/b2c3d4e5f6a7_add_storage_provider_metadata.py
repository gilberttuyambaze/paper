"""Add provider identifiers for durable storage resolution."""

from alembic import op
import sqlalchemy as sa


revision = "b2c3d4e5f6a7"
down_revision = "a7b8c9d0e1f2"
branch_labels = None
depends_on = None


def _add_missing_columns(table_name: str, columns: list[sa.Column]) -> None:
    bind = op.get_bind()
    existing = {column["name"] for column in sa.inspect(bind).get_columns(table_name)}
    for column in columns:
        if column.name not in existing:
            op.add_column(table_name, column)


def upgrade() -> None:
    _add_missing_columns(
        "books",
        [
            sa.Column("file_drive_file_id", sa.String(255), nullable=True),
            sa.Column("file_storage_provider", sa.String(80), nullable=True),
            sa.Column("cover_drive_file_id", sa.String(255), nullable=True),
            sa.Column("cover_storage_provider", sa.String(80), nullable=True),
        ],
    )
    _add_missing_columns(
        "papers",
        [
            sa.Column("file_drive_file_id", sa.String(255), nullable=True),
            sa.Column("file_storage_provider", sa.String(80), nullable=True),
            sa.Column("file_name", sa.String(500), nullable=True),
            sa.Column("file_size", sa.Integer(), nullable=True),
            sa.Column("file_mime_type", sa.String(150), nullable=True),
            sa.Column("solution_drive_file_id", sa.String(255), nullable=True),
            sa.Column("solution_storage_provider", sa.String(80), nullable=True),
            sa.Column("solution_file_name", sa.String(500), nullable=True),
            sa.Column("solution_file_size", sa.Integer(), nullable=True),
            sa.Column("solution_mime_type", sa.String(150), nullable=True),
        ],
    )
    _add_missing_columns(
        "solutions",
        [
            sa.Column("drive_file_id", sa.String(255), nullable=True),
            sa.Column("storage_provider", sa.String(80), nullable=True),
            sa.Column("file_name", sa.String(500), nullable=True),
            sa.Column("file_size", sa.Integer(), nullable=True),
            sa.Column("mime_type", sa.String(150), nullable=True),
        ],
    )


def downgrade() -> None:
    bind = op.get_bind()
    for table_name, column_names in {
        "books": ["file_drive_file_id", "file_storage_provider", "cover_drive_file_id", "cover_storage_provider"],
        "papers": ["file_drive_file_id", "file_storage_provider", "file_name", "file_size", "file_mime_type", "solution_drive_file_id", "solution_storage_provider", "solution_file_name", "solution_file_size", "solution_mime_type"],
        "solutions": ["drive_file_id", "storage_provider", "file_name", "file_size", "mime_type"],
    }.items():
        existing = {column["name"] for column in sa.inspect(bind).get_columns(table_name)}
        for column_name in column_names:
            if column_name in existing:
                op.drop_column(table_name, column_name)