import asyncio
import pytest
from types import SimpleNamespace

from services.site_access import can_upload_resource, is_super_admin, serialize_site_settings
from main import is_maintenance_technical_exemption


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
    ("selected_roles", "admin", True),
    ("selected_roles", "cp", False),
])
def test_upload_policy_matrix(mode, role, expected):
    settings = SimpleNamespace(maintenance_mode=False, upload_access_mode=mode, upload_roles='["admin"]', allowed_resource_types='["book"]', maintenance_message='maintenance')
    assert asyncio.run(can_upload_resource(FakeDb(settings), SimpleNamespace(role=role), "book")) is expected


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


def test_maintenance_technical_allowlist_is_conservative():
    assert is_maintenance_technical_exemption("/api/v1/auth/login")
    assert is_maintenance_technical_exemption("/health/database")
    assert not is_maintenance_technical_exemption("/api/v1/auth/register")
    assert not is_maintenance_technical_exemption("/api/v1/admin/settings/site-access")
    assert not is_maintenance_technical_exemption("/api/v1/books")