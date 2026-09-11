"""add heartbeat_notify_admin to site_settings

Revision ID: l2m3n4o5p6q7
Revises: k1l2m3n4o5p6
"""
from alembic import op
import sqlalchemy as sa

revision = "l2m3n4o5p6q7"
down_revision = "k1l2m3n4o5p6"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "site_settings" in tables:
        columns = {col["name"] for col in inspector.get_columns("site_settings")}
        if "heartbeat_notify_admin" not in columns:
            op.add_column("site_settings", sa.Column("heartbeat_notify_admin", sa.Boolean(), nullable=False, server_default=sa.text("true")))


def downgrade():
    op.drop_column("site_settings", "heartbeat_notify_admin")
