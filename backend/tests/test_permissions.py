from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from services.auth import role_for_identity
from services.authorization import PERMISSIONS, has_permission, permissions_for_role, require_permission


def actor(role: str):
    return SimpleNamespace(role=role)


def test_unknown_permission_fails_closed():
    assert not has_permission(actor("admin"), "unknown.permission")
    with pytest.raises(HTTPException) as error:
        require_permission(actor("admin"), "unknown.permission")
    assert error.value.status_code == 403


def test_super_admin_has_all_registered_privileged_permissions():
    permissions = permissions_for_role("super_admin")
    assert permissions == PERMISSIONS
    assert has_permission(actor("super_admin"), "site.maintenance.bypass")
    assert has_permission(actor("super_admin"), "users.transfer_super_admin")
    assert has_permission(actor("super_admin"), "site.settings.manage")


def test_configured_super_admin_identity_resolves_before_admin(monkeypatch):
    monkeypatch.setenv("SUPER_ADMIN_USER_ID", "platform-super-admin")
    monkeypatch.setenv("SUPER_ADMIN_USER_EMAIL", "super@example.com")
    monkeypatch.setenv("ADMIN_USER_ID", "platform-super-admin")

    assert role_for_identity("platform-super-admin", "other@example.com") == "super_admin"
    assert role_for_identity("other-user", "SUPER@example.com") == "super_admin"
    assert role_for_identity("other-user", "admin@example.com") in {"admin", "user"}


def test_permission_decisions_do_not_depend_on_role_checks_in_callers():
    assert has_permission(actor("admin"), "admin.dashboard.view")
    assert has_permission(actor("content_manager"), "users.manage")
    assert not has_permission(actor("cp"), "users.delete")
    assert not has_permission(actor("normal"), "uploads.book")


def test_require_permission_allows_permitted_role():
    assert require_permission(actor("admin"), "books.edit").role == "admin"
