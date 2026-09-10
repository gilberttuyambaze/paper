"""expand production system-health heartbeat

Revision ID: j0k1l2m3n4o
Revises: i9j0k1l2m3n4
"""
from alembic import op
import sqlalchemy as sa

revision = "j0k1l2m3n4o"
down_revision = "i9j0k1l2m3n4"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("site_settings", sa.Column("heartbeat_retry_enabled", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("site_settings", sa.Column("heartbeat_retry_jitter_minutes", sa.Integer(), nullable=False, server_default="30"))
    for column in (
        sa.Column("heartbeat_key", sa.String(length=32), nullable=False, server_default="default"),
        sa.Column("total_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("retry_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_retry_at", sa.DateTime(timezone=True)),
        sa.Column("next_scheduled_at", sa.DateTime(timezone=True)),
        sa.Column("schedule", sa.Text(), nullable=False, server_default="[]"),
    ):
        op.add_column("system_health_heartbeat", column)
    op.create_unique_constraint("uq_system_health_heartbeat_key", "system_health_heartbeat", ["heartbeat_key"])
    op.create_check_constraint("ck_system_health_heartbeat_singleton_id", "system_health_heartbeat", "id = 1")
    # Existing migrations insert this row; this is safe on supported databases and
    # preserves an existing installation without touching application data.
    op.execute(sa.text("UPDATE system_health_heartbeat SET heartbeat_key = 'default' WHERE id = 1"))


def downgrade():
    op.drop_constraint("ck_system_health_heartbeat_singleton_id", "system_health_heartbeat", type_="check")
    op.drop_constraint("uq_system_health_heartbeat_key", "system_health_heartbeat", type_="unique")
    for name in ("schedule", "next_scheduled_at", "next_retry_at", "retry_attempts", "consecutive_failures", "total_attempts", "heartbeat_key"):
        op.drop_column("system_health_heartbeat", name)
    op.drop_column("site_settings", "heartbeat_retry_jitter_minutes")
    op.drop_column("site_settings", "heartbeat_retry_enabled")
