import asyncio
import json
import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from services.site_access import can_upload_resource, is_super_admin, serialize_site_settings
from main import is_maintenance_technical_exemption, user_can_bypass_maintenance
import main as main_module
import routers.health as health_module


class FakeAsyncSession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def add(self, *args, **kwargs):
        return None

    async def flush(self, *args, **kwargs):
        return None

    async def get(self, *args, **kwargs):
        return None

    async def scalar(self, *args, **kwargs):
        return None


class FakeDb:
    def __init__(self, settings):
        self.settings = settings

    async def get(self, model, key):
        return self.settings

    def add(self, value):
        self.settings = value

    async def flush(self):
        return None


@pytest.mark.parametrize("mode,role,expected", [
    ("nobody", "admin", False),
    ("authenticated", "normal", True),
    ("authenticated", "admin", True),
    ("selected_roles", "admin", True),
    ("selected_roles", "normal", False),
    ("selected_roles", "cp", False),
])
def test_upload_policy_matrix(mode, role, expected):
    settings = SimpleNamespace(maintenance_mode=False, upload_access_mode=mode, upload_roles='["admin"]', allowed_resource_types='["book"]', maintenance_message='maintenance')
    assert asyncio.run(can_upload_resource(FakeDb(settings), SimpleNamespace(role=role), "book")) is expected


def test_selected_role_upload_does_not_require_upload_permission():
    settings = SimpleNamespace(maintenance_mode=False, upload_access_mode="selected_roles", upload_roles='["normal"]', allowed_resource_types='["book"]', maintenance_message='maintenance')
    assert asyncio.run(can_upload_resource(FakeDb(settings), SimpleNamespace(role="normal"), "book"))


def test_resource_types_are_independent_and_maintenance_blocks_normal_users():
    settings = SimpleNamespace(maintenance_mode=True, upload_access_mode="authenticated", upload_roles="[]", allowed_resource_types='["book"]', maintenance_message='maintenance')
    db = FakeDb(settings)
    assert not asyncio.run(can_upload_resource(db, SimpleNamespace(role="admin"), "book"))
    assert not asyncio.run(can_upload_resource(db, SimpleNamespace(role="super_admin"), "paper"))
    assert asyncio.run(can_upload_resource(db, SimpleNamespace(role="super_admin"), "book"))


def test_super_admin_identity_and_serialization():
    assert is_super_admin(SimpleNamespace(role="super_admin"))
    assert not is_super_admin(SimpleNamespace(role="admin"))
    data = serialize_site_settings(SimpleNamespace(maintenance_mode=False, maintenance_message="x", upload_access_mode="nobody", upload_roles="[]", allowed_resource_types='["paper"]'))
    assert data["allowed_resource_types"] == ["paper"]


@pytest.mark.parametrize("allowed,resource,expected", [
    (["book"], "book", True),
    (["book"], "paper", False),
    (["paper"], "paper", True),
    (["paper"], "book", False),
])
def test_upload_resource_types_are_independent(allowed, resource, expected):
    settings = SimpleNamespace(maintenance_mode=False, upload_access_mode="authenticated", upload_roles="[]", allowed_resource_types=json.dumps(allowed), maintenance_message="maintenance")
    assert asyncio.run(can_upload_resource(FakeDb(settings), SimpleNamespace(role="normal"), resource)) is expected


def test_maintenance_technical_allowlist_is_conservative():
    assert is_maintenance_technical_exemption("/api/v1/auth/login")
    assert is_maintenance_technical_exemption("/health/database")
    assert not is_maintenance_technical_exemption("/api/v1/auth/register")
    assert not is_maintenance_technical_exemption("/api/v1/admin/settings/site-access")
    assert not is_maintenance_technical_exemption("/api/v1/books")


def test_health_status_is_public_while_maintenance_is_on():
    client = TestClient(main_module.app)
    settings = SimpleNamespace(
        maintenance_mode=True,
        maintenance_message="Maintenance in progress",
        upload_access_mode="authenticated",
        upload_roles='["admin", "cp"]',
        allowed_resource_types='["book", "paper"]',
        heartbeat_enabled=True,
    )

    with patch.object(main_module.db_manager, "async_session_maker", return_value=FakeAsyncSession()), \
         patch.object(health_module, "get_site_settings", AsyncMock(return_value=settings)):
        response = client.get("/health/site-access", headers={"Origin": "https://paperhubur.vercel.app"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["maintenance_mode"] is True
    assert payload["maintenance_message"] == settings.maintenance_message
    assert payload["upload_access_mode"] == settings.upload_access_mode
    assert payload["upload_roles"] == ["admin", "cp"]
    assert payload["allowed_resource_types"] == ["book", "paper"]
    assert "heartbeat_enabled" not in payload


def test_maintenance_blocked_get_has_cors_headers():
    client = TestClient(main_module.app)
    settings = SimpleNamespace(maintenance_mode=True, maintenance_message="Maintenance in progress")
    origin = "https://paperhubur.vercel.app"

    with patch.object(main_module.db_manager, "async_session_maker", return_value=FakeAsyncSession()), \
         patch("main.get_site_settings", AsyncMock(return_value=settings)):
        response = client.get(
            "/api/v1/notifications",
            headers={"Origin": origin},
        )

    assert response.status_code == 503
    assert response.headers.get("access-control-allow-origin") == origin
    assert response.headers.get("access-control-allow-credentials", "").lower() == "true"


def test_maintenance_preflight_from_frontend_origin_has_cors_headers():
    client = TestClient(main_module.app)
    settings = SimpleNamespace(maintenance_mode=True, maintenance_message="Maintenance in progress")
    origin = "https://paperhubur.vercel.app"

    with patch.object(main_module.db_manager, "async_session_maker", return_value=FakeAsyncSession()), \
         patch("main.get_site_settings", AsyncMock(return_value=settings)):
        response = client.options(
            "/api/v1/notifications",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "authorization,content-type",
            },
        )

    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == origin
    assert response.headers.get("access-control-allow-credentials", "").lower() == "true"
    assert "GET" in response.headers.get("access-control-allow-methods", "")


def test_unapproved_origin_still_rejected_on_maintenance_preflight():
    client = TestClient(main_module.app)
    settings = SimpleNamespace(maintenance_mode=True, maintenance_message="Maintenance in progress")

    with patch.object(main_module.db_manager, "async_session_maker", return_value=FakeAsyncSession()), \
         patch("main.get_site_settings", AsyncMock(return_value=settings)):
        response = client.options(
            "/api/v1/notifications",
            headers={
                "Origin": "https://evil.example",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "authorization,content-type",
            },
        )

    assert response.status_code == 400
    assert response.headers.get("access-control-allow-origin") is None