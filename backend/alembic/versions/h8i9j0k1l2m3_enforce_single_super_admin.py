"""enforce the single Super Admin invariant

Revision ID: h8i9j0k1l2m3
Revises: g7h8i9j0k1l2
"""

from alembic import op
import sqlalchemy as sa


revision = "h8i9j0k1l2m3"
down_revision = "g7h8i9j0k1l2"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index(
        "uq_users_single_super_admin",
        "users",
        ["role"],
        unique=True,
        postgresql_where=sa.text("role = 'super_admin'"),
        sqlite_where=sa.text("role = 'super_admin'"),
    )


def downgrade():
    op.drop_index("uq_users_single_super_admin", table_name="users")