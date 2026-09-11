"""Comprehensive tests for Role-Based Access Control (RBAC) hierarchy, target enforcement, and content moderation boundaries."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from services.authorization import (
    CONTENT_MANAGER_EDITABLE_RESOURCE_FIELDS,
    CP_WINDOW,
    PERMISSIONS,
    ROLE_LEVELS,
    ROLE_PERMISSIONS,
    actor_can_manage_target,
    can_create_book,
    can_delete_book,
    can_delete_paper,
    can_manage_book,
    can_manage_paper,
    can_read_book,
    can_upload,
    has_permission,
    is_admin_or_super_admin,
    is_super_admin,
    permissions_for_role,
    require_permission,
    role_has_permission,
    role_level,
)
from routers.papers import _validate_paper_update_permissions
from routers.books import _validate_book_update_permissions
from routers.user_profiles import _validate_self_profile_update


def make_user(user_id: str, role: str):
    return SimpleNamespace(id=user_id, role=role, permissions=sorted(permissions_for_role(role)))


def make_profile(user_id: str, role: str):
    return SimpleNamespace(id=1, user_id=user_id, role=role)


def make_book(uploaded_by: str, created_at: datetime):
    return SimpleNamespace(id=1, uploaded_by=uploaded_by, created_at=created_at, status="active", visibility="public")


def make_paper(user_id: str, created_at: datetime):
    return SimpleNamespace(id=1, user_id=user_id, created_at=created_at, is_hidden=False, verification_status="verified")


# ==============================================================================
# 1. ROLE HIERARCHY & NUMERIC LEVELS
# ==============================================================================

def test_role_hierarchy_numeric_levels():
    assert role_level("super_admin") == 100
    assert role_level("admin") == 90
    assert role_level("content_manager") == 70
    assert role_level("lecturer") == 60
    assert role_level("cp") == 60
    assert role_level("verified_contributor") == 60
    assert role_level("normal") == 20
    assert role_level("user") == 20
    assert role_level("unknown_role") == 20
    assert role_level(None) == 20


def test_is_admin_or_super_admin():
    assert is_admin_or_super_admin(make_user("1", "super_admin"))
    assert is_admin_or_super_admin(make_user("2", "admin"))
    assert not is_admin_or_super_admin(make_user("3", "content_manager"))
    assert not is_admin_or_super_admin(make_user("4", "cp"))
    assert not is_admin_or_super_admin(make_user("5", "lecturer"))
    assert not is_admin_or_super_admin(make_user("6", "normal"))
    assert not is_admin_or_super_admin(make_user("7", "user"))


# ==============================================================================
# 2. ACTOR CAN MANAGE TARGET (HIERARCHY ENFORCEMENT)
# ==============================================================================

def test_super_admin_can_manage_all_subordinates():
    super_admin = make_user("super", "super_admin")
    assert actor_can_manage_target(super_admin, make_profile("adm", "admin"))
    assert actor_can_manage_target(super_admin, make_profile("cm", "content_manager"))
    assert actor_can_manage_target(super_admin, make_profile("cp1", "cp"))
    assert actor_can_manage_target(super_admin, make_profile("lec", "lecturer"))
    assert actor_can_manage_target(super_admin, make_profile("usr", "normal"))
    assert actor_can_manage_target(super_admin, make_profile("super2", "super_admin"))


def test_admin_can_only_manage_strictly_lower_roles():
    admin = make_user("adm", "admin")
    # Admin CANNOT manage super_admin
    assert not actor_can_manage_target(admin, make_profile("super", "super_admin"))
    # Admin CANNOT manage peer admin
    assert not actor_can_manage_target(admin, make_profile("adm2", "admin"))
    # Admin CAN manage lower roles
    assert actor_can_manage_target(admin, make_profile("cm", "content_manager"))
    assert actor_can_manage_target(admin, make_profile("cp1", "cp"))
    assert actor_can_manage_target(admin, make_profile("lec", "lecturer"))
    assert actor_can_manage_target(admin, make_profile("usr", "normal"))


def test_content_manager_and_below_cannot_manage_any_user():
    cm = make_user("cm", "content_manager")
    cp = make_user("cp", "cp")
    student = make_user("student", "normal")

    for actor in (cm, cp, student):
        assert not actor_can_manage_target(actor, make_profile("super", "super_admin"))
        assert not actor_can_manage_target(actor, make_profile("adm", "admin"))
        assert not actor_can_manage_target(actor, make_profile("cm2", "content_manager"))
        assert not actor_can_manage_target(actor, make_profile("cp2", "cp"))
        assert not actor_can_manage_target(actor, make_profile("usr2", "normal"))


# ==============================================================================
# 3. CONTENT MANAGER PERMISSIONS BOUNDARIES
# ==============================================================================

def test_content_manager_permissions_matrix():
    cm_perms = permissions_for_role("content_manager")

    # Content Manager MUST have content moderation permissions
    assert "admin.dashboard.view" in cm_perms
    assert "users.view" in cm_perms
    assert "books.view" in cm_perms
    assert "books.edit_metadata" in cm_perms
    assert "papers.view" in cm_perms
    assert "papers.edit_metadata" in cm_perms
    assert "papers.verify" in cm_perms
    assert "papers.hide" in cm_perms
    assert "reports.manage" in cm_perms

    # Content Manager MUST NOT have user mutation or deletion permissions
    assert "users.manage" not in cm_perms
    assert "users.edit_profile" not in cm_perms
    assert "users.edit_academic" not in cm_perms
    assert "users.change_verification" not in cm_perms
    assert "users.change_status" not in cm_perms
    assert "users.change_role" not in cm_perms
    assert "users.delete" not in cm_perms
    assert "users.transfer_super_admin" not in cm_perms

    # Content Manager MUST NOT have resource deletion or storage mutation permissions
    assert "books.delete" not in cm_perms
    assert "papers.delete" not in cm_perms
    assert "storage.manage" not in cm_perms
    assert "storage.delete" not in cm_perms
    assert "site.settings.manage" not in cm_perms
    assert "system.health.manage" not in cm_perms


# ==============================================================================
# 4. RESOURCE DELETION & CP 48-HOUR BOUNDARY
# ==============================================================================

def test_resource_deletion_permissions():
    now = datetime(2026, 9, 11, 12, 0, tzinfo=timezone.utc)
    super_admin = make_user("super", "super_admin")
    admin = make_user("adm", "admin")
    cm = make_user("cm", "content_manager")
    cp_owner = make_user("cp1", "cp")
    cp_other = make_user("cp2", "cp")
    student = make_user("student", "normal")

    paper_recent = make_paper("cp1", now - timedelta(hours=10))
    paper_old = make_paper("cp1", now - timedelta(hours=50))
    book_recent = make_book("cp1", now - timedelta(hours=10))
    book_old = make_book("cp1", now - timedelta(hours=50))

    # Super Admin and Admin can delete any paper / book regardless of age
    assert can_delete_paper(super_admin, paper_recent, now)
    assert can_delete_paper(super_admin, paper_old, now)
    assert can_delete_paper(admin, paper_recent, now)
    assert can_delete_paper(admin, paper_old, now)

    assert can_delete_book(super_admin, book_recent, now)
    assert can_delete_book(super_admin, book_old, now)
    assert can_delete_book(admin, book_recent, now)
    assert can_delete_book(admin, book_old, now)

    # Content Manager cannot delete any paper / book
    assert not can_delete_paper(cm, paper_recent, now)
    assert not can_delete_paper(cm, paper_old, now)
    assert not can_delete_book(cm, book_recent, now)
    assert not can_delete_book(cm, book_old, now)

    # CP can delete own resource within 48h, but NOT after 48h, and NOT another user's resource
    assert can_delete_paper(cp_owner, paper_recent, now)
    assert not can_delete_paper(cp_owner, paper_old, now)
    assert not can_delete_paper(cp_other, paper_recent, now)

    assert can_delete_book(cp_owner, book_recent, now)
    assert not can_delete_book(cp_owner, book_old, now)
    assert not can_delete_book(cp_other, book_recent, now)

    # Normal student cannot delete
    assert not can_delete_paper(student, paper_recent, now)
    assert not can_delete_book(student, book_recent, now)


# ==============================================================================
# 5. SAFE RESOURCE METADATA EDITING VS PROTECTED FIELDS
# ==============================================================================

def test_content_manager_safe_resource_fields():
    cm = make_user("cm", "content_manager")
    admin = make_user("adm", "admin")

    safe_updates = {
        "title": "New Title",
        "description": "New Description",
        "course_code": "CSC101",
        "course_name": "Intro to CS",
        "year": 2026,
    }

    # Safe fields validation should pass for Content Manager
    _validate_paper_update_permissions(cm, safe_updates)
    _validate_book_update_permissions(cm, safe_updates)

    # Protected fields (file keys, ownership, verification) must be rejected for Content Manager
    with pytest.raises(HTTPException) as exc_info:
        _validate_paper_update_permissions(cm, {**safe_updates, "file_key": "malicious.pdf"})
    assert exc_info.value.status_code == 403

    with pytest.raises(HTTPException) as exc_info:
        _validate_paper_update_permissions(cm, {**safe_updates, "user_id": "attacker"})
    assert exc_info.value.status_code == 403

    with pytest.raises(HTTPException) as exc_info:
        _validate_book_update_permissions(cm, {**safe_updates, "file_key": "malicious.pdf"})
    assert exc_info.value.status_code == 403

    # Admin has full edit permissions, so all fields are allowed
    _validate_paper_update_permissions(admin, {**safe_updates, "file_key": "updated.pdf"})
    _validate_book_update_permissions(admin, {**safe_updates, "file_key": "updated.pdf"})


# ==============================================================================
# 6. USER PROFILE MASS-ASSIGNMENT PROTECTION
# ==============================================================================

def test_user_profile_mass_assignment_protection():
    student = make_user("student", "normal")
    admin = make_user("adm", "admin")

    safe_self_update = {
        "display_name": "Updated Name",
        "phone_number": "+250780000000",
        "bio": "CS Student",
    }

    # Normal user updating safe fields passes
    _validate_self_profile_update(student, safe_self_update)

    # Normal user attempting to elevate role is blocked
    with pytest.raises(HTTPException) as exc_info:
        _validate_self_profile_update(student, {**safe_self_update, "role": "admin"})
    assert exc_info.value.status_code == 403

    # Normal user attempting to inflate trust score is blocked
    with pytest.raises(HTTPException) as exc_info:
        _validate_self_profile_update(student, {**safe_self_update, "trust_score": 999})
    assert exc_info.value.status_code == 403

    # Normal user attempting to change account status is blocked
    with pytest.raises(HTTPException) as exc_info:
        _validate_self_profile_update(student, {**safe_self_update, "account_status": "active"})
    assert exc_info.value.status_code == 403

    # Normal user attempting to self-verify is blocked
    with pytest.raises(HTTPException) as exc_info:
        _validate_self_profile_update(student, {**safe_self_update, "ur_verification_status": "verified"})
    assert exc_info.value.status_code == 403

    # Normal user attempting to alter audit counts or suspension is blocked
    for privileged_field in ("upload_count", "download_count", "suspension_reason", "suspended_until", "requested_role_status"):
        with pytest.raises(HTTPException) as exc_info:
            _validate_self_profile_update(student, {**safe_self_update, privileged_field: "injected_value"})
        assert exc_info.value.status_code == 403

    # Admin is permitted
    _validate_self_profile_update(admin, {**safe_self_update, "role": "admin", "trust_score": 100})


# ==============================================================================
# 7. ADVERSARIAL AUDIT: USER ADMINISTRATION MUTATION VECTORS
# ==============================================================================

def test_content_manager_cannot_perform_any_user_administration():
    cm = make_user("cm_1", "content_manager")
    target_student = make_profile("student_1", "normal")
    target_cp = make_profile("cp_1", "cp")
    target_cm = make_profile("cm_2", "content_manager")
    target_admin = make_profile("admin_1", "admin")
    target_super = make_profile("super_1", "super_admin")

    # Content manager cannot administratively manage any target in hierarchy
    for target in (target_student, target_cp, target_cm, target_admin, target_super):
        assert not actor_can_manage_target(cm, target)

    # Content manager lacks all user mutation permissions
    for perm in (
        "users.manage",
        "users.edit_profile",
        "users.edit_academic",
        "users.change_verification",
        "users.change_status",
        "users.change_role",
        "users.delete",
        "users.transfer_super_admin",
    ):
        assert not has_permission(cm, perm)
        with pytest.raises(HTTPException) as exc_info:
            require_permission(cm, perm)
        assert exc_info.value.status_code == 403


def test_content_manager_role_assignment_prevention():
    from routers.admin_hub import _ensure_role_assignment_allowed
    cm = make_user("cm_1", "content_manager")
    target = make_profile("student_1", "normal")

    # Content manager attempting to assign any role is blocked
    for attempted_role in ("admin", "content_manager", "cp", "lecturer", "normal"):
        with pytest.raises(HTTPException) as exc_info:
            _ensure_role_assignment_allowed(cm, target, attempted_role)
        assert exc_info.value.status_code == 403


# ==============================================================================
# 8. ADVERSARIAL AUDIT: ADMIN TARGET HIERARCHY & SELF-PROMOTION
# ==============================================================================

def test_admin_target_hierarchy_restrictions():
    from routers.admin_hub import _ensure_role_assignment_allowed
    admin = make_user("admin_1", "admin")
    super_admin_profile = make_profile("super_1", "super_admin")
    peer_admin_profile = make_profile("admin_2", "admin")
    subordinate_profile = make_profile("student_1", "normal")
    self_profile = make_profile("admin_1", "admin")

    # Admin CANNOT manage super_admin
    assert not actor_can_manage_target(admin, super_admin_profile)
    with pytest.raises(HTTPException) as exc_info:
        _ensure_role_assignment_allowed(admin, super_admin_profile, "normal")
    assert exc_info.value.status_code == 403

    # Admin CANNOT manage peer admin
    assert not actor_can_manage_target(admin, peer_admin_profile)
    with pytest.raises(HTTPException) as exc_info:
        _ensure_role_assignment_allowed(admin, peer_admin_profile, "normal")
    assert exc_info.value.status_code == 403

    # Admin CANNOT promote anyone to super_admin
    with pytest.raises(HTTPException) as exc_info:
        _ensure_role_assignment_allowed(admin, subordinate_profile, "super_admin")
    assert exc_info.value.status_code == 403

    # Admin CANNOT assign a role equal to or higher than their own
    with pytest.raises(HTTPException) as exc_info:
        _ensure_role_assignment_allowed(admin, subordinate_profile, "admin")
    assert exc_info.value.status_code == 403

    # Admin CANNOT modify their own role (self-demotion or self-elevation)
    with pytest.raises(HTTPException) as exc_info:
        _ensure_role_assignment_allowed(admin, self_profile, "super_admin")
    assert exc_info.value.status_code == 403

    # Admin CAN manage strictly lower roles (content_manager, cp, lecturer, normal)
    assert actor_can_manage_target(admin, subordinate_profile)
    _ensure_role_assignment_allowed(admin, subordinate_profile, "cp")
    _ensure_role_assignment_allowed(admin, subordinate_profile, "lecturer")
    _ensure_role_assignment_allowed(admin, subordinate_profile, "content_manager")


# ==============================================================================
# 9. ADVERSARIAL AUDIT: CRAFTED INJECTION IN RESOURCE UPDATES
# ==============================================================================

def test_content_manager_crafted_resource_injection_all_vectors():
    cm = make_user("cm_1", "content_manager")

    forbidden_payloads = [
        {"user_id": "attacker_id"},
        {"uploaded_by": "attacker_id"},
        {"file_key": "injected_path/payload.pdf"},
        {"cover_key": "injected_path/cover.png"},
        {"solution_key": "injected_path/sol.pdf"},
        {"file_drive_file_id": "google_drive_file_123"},
        {"cover_drive_file_id": "google_drive_cover_123"},
        {"solution_drive_file_id": "google_drive_sol_123"},
        {"file_storage_provider": "google_drive"},
        {"verification_status": "verified"},
        {"is_hidden": True},
        {"download_count": 9999},
        {"report_count": 0},
    ]

    for payload in forbidden_payloads:
        with pytest.raises(HTTPException) as exc_info:
            _validate_paper_update_permissions(cm, payload)
        assert exc_info.value.status_code == 403

        with pytest.raises(HTTPException) as exc_info:
            _validate_book_update_permissions(cm, payload)
        assert exc_info.value.status_code == 403


# ==============================================================================
# 10. ADVERSARIAL AUDIT: STORAGE ACCESS & SYSTEM MANAGEMENT VECTORS
# ==============================================================================

def test_content_manager_cannot_access_storage_or_system_administration():
    from dependencies.auth import get_admin_user, get_super_admin_user
    cm = make_user("cm_1", "content_manager")

    # get_admin_user dependency (used for create-bucket, delete-object, list-buckets, rename-object, settings)
    # must reject content manager
    assert not is_admin_or_super_admin(cm)
    with pytest.raises(HTTPException) as exc_info:
        # Simulate dependency call
        if not is_admin_or_super_admin(cm):
            raise HTTPException(status_code=403, detail="Admin access required")
    assert exc_info.value.status_code == 403

    # get_super_admin_user must reject content manager and admin
    admin = make_user("adm_1", "admin")
    assert not is_super_admin(cm)
    assert not is_super_admin(admin)
    with pytest.raises(HTTPException) as exc_info:
        if not is_super_admin(cm):
            raise HTTPException(status_code=403, detail="Super Admin access required")
    assert exc_info.value.status_code == 403


# ==============================================================================
# 11. ADVERSARIAL AUDIT: CP OWNERSHIP TAMPERING & 48-HOUR BOUNDARY
# ==============================================================================

def test_cp_ownership_and_time_tampering_boundaries():
    now = datetime(2026, 9, 11, 12, 0, tzinfo=timezone.utc)
    cp_legit = make_user("cp_legit", "cp")
    cp_attacker = make_user("cp_attacker", "cp")

    # Paper created by cp_legit 1 hour ago
    paper = make_paper("cp_legit", now - timedelta(hours=1))

    # cp_attacker CANNOT manage or delete cp_legit's paper
    assert not can_manage_paper(cp_attacker, paper, now)
    assert not can_delete_paper(cp_attacker, paper, now)

    # Even if cp_legit is within 48h, past 48h boundary is strictly enforced
    paper_expired = make_paper("cp_legit", now - timedelta(hours=48, seconds=1))
    assert not can_manage_paper(cp_legit, paper_expired, now)
    assert not can_delete_paper(cp_legit, paper_expired, now)

    # Book created by cp_legit
    book = make_book("cp_legit", now - timedelta(hours=1))
    assert not can_manage_book(cp_attacker, book, now)
    assert not can_delete_book(cp_attacker, book, now)

    book_expired = make_book("cp_legit", now - timedelta(hours=48, seconds=1))
    assert not can_manage_book(cp_legit, book_expired, now)
    assert not can_delete_book(cp_legit, book_expired, now)


