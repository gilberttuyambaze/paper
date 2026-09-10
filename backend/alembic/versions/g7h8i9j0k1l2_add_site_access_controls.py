"""add persisted site access controls and Super Admin role

Revision ID: g7h8i9j0k1l2
Revises: d5e6f7a8b9c0, f6a7b8c9d0e1
"""

from alembic import op
import sqlalchemy as sa


revision = "g7h8i9j0k1l2"
down_revision = ("d5e6f7a8b9c0", "f6a7b8c9d0e1")
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "site_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("maintenance_mode", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("maintenance_message", sa.Text(), nullable=False, server_default="The site is temporarily unavailable. We are performing scheduled maintenance. Please try again later."),
        sa.Column("upload_access_mode", sa.String(length=32), nullable=False, server_default="selected_roles"),
        sa.Column("upload_roles", sa.Text(), nullable=False, server_default='["admin", "cp"]'),
        sa.Column("allowed_resource_types", sa.Text(), nullable=False, server_default='["book", "paper"]'),
    )
    op.execute(sa.text("INSERT INTO site_settings (id) VALUES (1)"))


def downgrade():
    op.drop_table("site_settings")