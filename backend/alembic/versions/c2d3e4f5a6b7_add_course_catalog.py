"""add normalized course catalog and book relationships

Revision ID: c2d3e4f5a6b7
Revises: b1c2d3e4f5a6
"""
from alembic import op
import sqlalchemy as sa

revision = "c2d3e4f5a6b7"
down_revision = "b1c2d3e4f5a6"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table("courses", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("code", sa.String(100)), sa.Column("normalized_code", sa.String(100), unique=True), sa.Column("name", sa.String(255), nullable=False), sa.Column("normalized_name", sa.String(255), nullable=False, unique=True), sa.Column("description", sa.Text()), sa.Column("created_by", sa.String(255), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False), sa.Column("deleted_at", sa.DateTime(timezone=True)))
    for name, column in [("ix_courses_code", "code"), ("ix_courses_normalized_code", "normalized_code"), ("ix_courses_name", "name"), ("ix_courses_normalized_name", "normalized_name"), ("ix_courses_created_by", "created_by"), ("ix_courses_deleted_at", "deleted_at")]: op.create_index(name, "courses", [column])
    # book_courses was introduced with temporary text course IDs. Recreate it
    # as a normalized relation; this feature has no deployed legacy catalog.
    op.drop_table("book_courses")
    op.create_table("book_courses", sa.Column("book_id", sa.Integer(), nullable=False), sa.Column("course_id", sa.Integer(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False), sa.PrimaryKeyConstraint("book_id", "course_id"), sa.ForeignKeyConstraint(["book_id"], ["books.id"], ondelete="CASCADE"), sa.ForeignKeyConstraint(["course_id"], ["courses.id"], ondelete="CASCADE"))
    op.create_index("ix_book_courses_book_id", "book_courses", ["book_id"]); op.create_index("ix_book_courses_course_id", "book_courses", ["course_id"])
    if op.get_bind().dialect.name == "postgresql":
        for table in ("courses", "book_courses", "modules", "book_modules", "authors"):
            op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute("CREATE POLICY courses_select_policy ON courses FOR SELECT USING (deleted_at IS NULL)")
        op.execute("CREATE POLICY modules_select_policy ON modules FOR SELECT USING (true)")
        op.execute("CREATE POLICY book_courses_select_policy ON book_courses FOR SELECT USING (EXISTS (SELECT 1 FROM books b WHERE b.id = book_courses.book_id AND b.deleted_at IS NULL))")
        op.execute("CREATE POLICY book_modules_select_policy ON book_modules FOR SELECT USING (EXISTS (SELECT 1 FROM books b WHERE b.id = book_modules.book_id AND b.deleted_at IS NULL))")

def downgrade():
    if op.get_bind().dialect.name == "postgresql":
        for table, policy in (("book_modules", "book_modules_select_policy"), ("book_courses", "book_courses_select_policy"), ("modules", "modules_select_policy"), ("courses", "courses_select_policy")):
            op.execute(f"DROP POLICY IF EXISTS {policy} ON {table}")
        for table in ("authors", "book_modules", "modules", "book_courses", "courses"): op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
    op.drop_table("book_courses")
    op.create_table("book_courses", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("book_id", sa.Integer(), nullable=False), sa.Column("course_id", sa.String(255), nullable=False))
    op.create_index("ix_book_courses_book_id", "book_courses", ["book_id"]); op.create_index("ix_book_courses_course_id", "book_courses", ["course_id"])
    op.drop_table("courses")
