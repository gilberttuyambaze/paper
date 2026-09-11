"""add password reset security and communication records

Revision ID: k1l2m3n4o5p6
Revises: j0k1l2m3n4o
"""
from alembic import op
import sqlalchemy as sa

revision = "k1l2m3n4o5p6"
down_revision = "j0k1l2m3n4o"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "session_version" not in {column["name"] for column in inspector.get_columns("users")}:
        op.add_column("users", sa.Column("session_version", sa.Integer(), nullable=False, server_default="0"))
    if "inactive_notification_sent_at" not in {column["name"] for column in inspector.get_columns("users")}:
        op.add_column("users", sa.Column("inactive_notification_sent_at", sa.DateTime(timezone=True), nullable=True))

    if "password_reset_tokens" not in tables:
        op.create_table(
            "password_reset_tokens",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.String(length=255), nullable=False),
            sa.Column("token_hash", sa.String(length=128), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
    _create_index_if_missing(inspector, "ix_password_reset_tokens_user_id", "password_reset_tokens", ["user_id"])
    _create_index_if_missing(inspector, "ix_password_reset_tokens_token_hash", "password_reset_tokens", ["token_hash"], unique=True)

    if "password_reset_request_attempts" not in tables:
        op.create_table(
            "password_reset_request_attempts",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("request_key", sa.String(length=128), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
    _create_index_if_missing(inspector, "ix_password_reset_request_attempts_request_key", "password_reset_request_attempts", ["request_key"])

    if "communication_events" not in tables:
        op.create_table(
            "communication_events",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("event_type", sa.String(length=64), nullable=False),
            sa.Column("user_id", sa.String(length=255), nullable=True),
            sa.Column("recipient_hash", sa.String(length=64), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
            sa.Column("provider_message_id", sa.String(length=255), nullable=True),
            sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("error_category", sa.String(length=64), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        )
    _create_index_if_missing(inspector, "ix_communication_events_event_type", "communication_events", ["event_type"])
    _create_index_if_missing(inspector, "ix_communication_events_user_id", "communication_events", ["user_id"])
    _create_index_if_missing(inspector, "ix_communication_events_recipient_hash", "communication_events", ["recipient_hash"])


def downgrade():
    op.drop_index("ix_communication_events_recipient_hash", table_name="communication_events")
    op.drop_index("ix_communication_events_user_id", table_name="communication_events")
    op.drop_index("ix_communication_events_event_type", table_name="communication_events")
    op.drop_table("communication_events")
    op.drop_index("ix_password_reset_request_attempts_request_key", table_name="password_reset_request_attempts")
    op.drop_table("password_reset_request_attempts")
    # Keep password_reset_tokens on downgrade: older deployments may have
    # created this security table through metadata startup, and dropping it
    # would destroy active reset-state data.
    op.drop_column("users", "session_version")
    op.drop_column("users", "inactive_notification_sent_at")


def _create_index_if_missing(inspector, name, table_name, columns, unique=False):
    existing = {index["name"] for index in inspector.get_indexes(table_name)}
    if name not in existing:
        op.create_index(name, table_name, columns, unique=unique)
