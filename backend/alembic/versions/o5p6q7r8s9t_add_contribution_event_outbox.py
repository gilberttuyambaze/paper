"""add paper communication outbox metadata

Revision ID: o5p6q7r8s9t
Revises: n4o5p6q7r8s
"""

from alembic import op
import sqlalchemy as sa

revision = "o5p6q7r8s9t"
down_revision = "n4o5p6q7r8s"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("communication_events", sa.Column("paper_id", sa.Integer(), nullable=True))
    op.add_column("communication_events", sa.Column("payload_json", sa.Text(), nullable=True))
    op.add_column("communication_events", sa.Column("delivery_started_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_communication_events_paper_id", "communication_events", ["paper_id"])
    # A unique index is portable to SQLite as well as PostgreSQL (Alembic's
    # ALTER TABLE ADD CONSTRAINT form is not supported by SQLite).
    op.create_index("uq_communication_event_paper_type", "communication_events", ["event_type", "paper_id"], unique=True)


def downgrade():
    op.drop_index("uq_communication_event_paper_type", table_name="communication_events")
    op.drop_index("ix_communication_events_paper_id", table_name="communication_events")
    op.drop_column("communication_events", "payload_json")
    op.drop_column("communication_events", "delivery_started_at")
    op.drop_column("communication_events", "paper_id")
