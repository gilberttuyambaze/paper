"""add durable database activity heartbeat

Revision ID: i9j0k1l2m3n4
Revises: h8i9j0k1l2m3
"""

from alembic import op
import sqlalchemy as sa

revision = "i9j0k1l2m3n4"
down_revision = "h8i9j0k1l2m3"
branch_labels = None
depends_on = None


def upgrade():
    columns = (
        sa.Column("heartbeat_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("heartbeat_min_weekly_checks", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("heartbeat_max_weekly_checks", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("heartbeat_retry_delay_hours", sa.Integer(), nullable=False, server_default="6"),
        sa.Column("heartbeat_max_retry_attempts", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("heartbeat_run_on_startup", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("heartbeat_week_start", sa.DateTime(timezone=True)),
        sa.Column("heartbeat_schedule", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("heartbeat_completed_checks", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("heartbeat_retry_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("heartbeat_next_attempt_at", sa.DateTime(timezone=True)),
        sa.Column("heartbeat_scheduler_status", sa.String(length=32), nullable=False, server_default="stopped"),
    )
    for column in columns:
        op.add_column("site_settings", column)
    op.create_table(
        "system_health_heartbeat",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True)),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True)),
        sa.Column("last_failure_at", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.Text()),
        sa.Column("total_successes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_failures", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_duration_ms", sa.Integer()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.execute(sa.text("INSERT INTO system_health_heartbeat (id) VALUES (1)"))


def downgrade():
    op.drop_table("system_health_heartbeat")
    for name in ("heartbeat_scheduler_status", "heartbeat_next_attempt_at", "heartbeat_retry_attempts", "heartbeat_completed_checks", "heartbeat_schedule", "heartbeat_week_start", "heartbeat_run_on_startup", "heartbeat_max_retry_attempts", "heartbeat_retry_delay_hours", "heartbeat_max_weekly_checks", "heartbeat_min_weekly_checks", "heartbeat_enabled"):
        op.drop_column("site_settings", name)
