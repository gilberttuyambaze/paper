"""Local regression checks for the UR academic taxonomy and its migration."""
import importlib.util
from pathlib import Path

import asyncio
import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import create_engine, inspect, text
from alembic.migration import MigrationContext
from alembic.operations import Operations

from routers.academics import router
from services.academic_taxonomy import NODES, children, validate_context


ROOT = Path(__file__).resolve().parents[1]

def _migration(filename):
    spec = importlib.util.spec_from_file_location(filename, ROOT / "alembic" / "versions" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def _upgrade(connection, migration):
    context = MigrationContext.configure(connection)
    operations = Operations(context)
    operations._install_proxy()
    try:
        migration.upgrade()
    finally:
        operations._remove_proxy()

def _ids():
    campus = "ur-campus-nyarugenge"
    college = f"{campus}-college-cst"
    school = f"{college}-school-engineering"
    programme = f"{school}-programme-mechanical-engineering"
    return campus, college, school, programme

def test_taxonomy_hierarchy_and_invalid_contexts():
    campus, college, school, programme = _ids()
    validate_context("ur", campus, college, school, programme)
    assert len(children("ur")) == 8
    assert NODES[programme].parent_id == school
    for args in [
        ("ur", "ur-campus-remera", college, school, programme),
        ("ur", campus, "ur-campus-remera-college-cmhs", school, programme),
        ("ur", campus, college, school, "ur-campus-remera-college-cmhs-school-medicine-programme-mbbs"),
        ("ur", "not-a-campus", college, school, programme),
        ("ur", campus, college, school, programme, "not-a-department"),
    ]:
        with pytest.raises(ValueError):
            validate_context(*args)

def test_taxonomy_api_is_public_and_returns_children():
    app = FastAPI(); app.include_router(router)
    async def verify():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v1/academics/taxonomy")
            assert response.status_code == 200
            payload = response.json()
            assert payload["institution"]["id"] == "ur"
            assert payload["nodes"] == (await client.get("/api/v1/academics/taxonomy")).json()["nodes"]
            assert (await client.get("/api/v1/academics/ur-campus-rwamagana/children")).json() == {"items": []}
            assert (await client.get("/api/v1/academics/nope/children")).status_code == 404
    asyncio.run(verify())

def test_academic_migration_preserves_legacy_rows(tmp_path):
    database = create_engine(f"sqlite:///{tmp_path / 'audit.db'}")
    initial = _migration("f97c229ef883_auto_update.py")
    academic = _migration("a2b8c1d93f41_add_academic_taxonomy_fields.py")
    with database.begin() as connection:
        _upgrade(connection, initial)
        connection.execute(text("INSERT INTO user_profiles (user_id, display_name, role) VALUES ('legacy-user', 'Legacy User', 'normal')"))
        connection.execute(text("INSERT INTO papers (user_id, title, course_code, course_name, college, department, year, paper_type, verification_status) VALUES ('legacy-user', 'Legacy', 'LEG101', 'Legacy Course', 'Legacy College', 'Legacy Department', 2025, 'Exam', 'unverified')"))
        _upgrade(connection, academic)
        assert connection.execute(text("SELECT display_name FROM user_profiles WHERE user_id = 'legacy-user'")).scalar_one() == "Legacy User"
        assert connection.execute(text("SELECT title FROM papers WHERE title = 'Legacy'")).scalar_one() == "Legacy"
    columns = {column["name"]: column for column in inspect(database).get_columns("papers")}
    assert all(columns[name]["nullable"] for name in ("institution_id", "campus_id", "college_id", "school_id", "academic_department_id", "programme_id", "semester", "examination_session"))
    profile_columns = {column["name"]: column for column in inspect(database).get_columns("user_profiles")}
    assert all(profile_columns[name]["nullable"] for name in ("institution_id", "campus_id", "college_id", "school_id", "academic_department_id", "programme_id"))
