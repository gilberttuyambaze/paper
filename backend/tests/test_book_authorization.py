from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
import inspect
from services.authorization import CP_WINDOW, can_create_book, can_manage_book, can_manage_paper, can_read_book, can_upload
from pydantic import ValidationError
from routers.books import BookCreate, BookUpdate


def user(user_id: str, role: str):
    return SimpleNamespace(id=user_id, role=role)


def book(owner: str, created_at: datetime):
    return SimpleNamespace(uploaded_by=owner, created_at=created_at, deleted_at=None, status="active", visibility="public")


def test_active_public_books_are_readable_across_users_but_private_books_are_not():
    now = datetime(2026, 8, 23, 10, 0, tzinfo=timezone.utc)
    book_a = book("cp-a", now)
    admin, cp_a, cp_b, student = user("admin", "admin"), user("cp-a", "cp"), user("cp-b", "cp"), user("student", "normal")

    assert all(can_read_book(actor, book_a) for actor in (admin, cp_a, cp_b, student))

    book_a.status = "draft"
    assert can_read_book(admin, book_a)
    assert not any(can_read_book(actor, book_a) for actor in (cp_a, cp_b, student))

    book_a.status = "active"
    book_a.visibility = "private"
    assert can_read_book(admin, book_a)
    assert not any(can_read_book(actor, book_a) for actor in (cp_a, cp_b, student))

    book_a.visibility = "public"
    book_a.deleted_at = now
    assert can_read_book(admin, book_a)
    assert not any(can_read_book(actor, book_a) for actor in (cp_a, cp_b, student))


def test_upload_permission_is_shared_by_papers_and_books():
    assert can_upload(user("admin", "admin")) and can_create_book(user("admin", "admin"))
    assert can_upload(user("cp", "cp")) and can_create_book(user("cp", "cp"))
    assert not can_upload(user("student", "normal"))
    assert not can_create_book(user("student", "normal"))


def test_complete_book_permission_tree_uses_exact_48_hour_boundary():
    now = datetime(2026, 8, 23, 10, 0, tzinfo=timezone.utc)
    admin, cp_a, cp_b, student = user("admin", "admin"), user("cp-a", "cp"), user("cp-b", "cp"), user("student", "normal")
    assert can_manage_book(admin, book("cp-b", now - timedelta(days=30)), now)
    assert can_manage_book(cp_a, book("cp-a", now - timedelta(hours=1)), now)
    assert can_manage_book(cp_a, book("cp-a", now - timedelta(hours=47, minutes=59)), now)
    assert not can_manage_book(cp_a, book("cp-a", now - CP_WINDOW), now)
    assert not can_manage_book(cp_a, book("cp-a", now - timedelta(hours=72)), now)
    assert not can_manage_book(cp_a, book("cp-b", now - timedelta(hours=1)), now)
    assert not can_manage_book(cp_a, book("admin", now - timedelta(hours=1)), now)
    assert not can_manage_book(student, book("student", now - timedelta(hours=1)), now)


def test_clients_cannot_submit_protected_book_ownership_fields():
    payload = {"title": "Networks", "authors": ["Author"], "course_ids": ["CSC321"], "cover": {"key": "cover.png"}, "file": {"key": "book.pdf"}}
    with pytest.raises(ValidationError):
        BookCreate(**payload, uploaded_by="cp-a")
    with pytest.raises(ValidationError):
        BookUpdate(created_at="2026-08-21T10:00:00Z")


def test_papers_follow_the_same_admin_cp_ownership_window():
    now = datetime(2026, 8, 23, 10, 0, tzinfo=timezone.utc)
    paper = SimpleNamespace(user_id="cp-a", created_at=now - timedelta(hours=47, minutes=59))
    assert can_manage_paper(user("admin", "admin"), paper, now)
    assert can_manage_paper(user("cp-a", "cp"), paper, now)
    assert not can_manage_paper(user("cp-b", "cp"), paper, now)
    paper.created_at = now - CP_WINDOW
    assert not can_manage_paper(user("cp-a", "cp"), paper, now)


def test_book_upload_updates_profile_upload_count_and_trust_score():
    from routers.books import create_book
    source = inspect.getsource(create_book)
    # Book creation uses the same persisted contribution semantics as Paper creation;
    # it must happen at mutation time, never while a dashboard is read.
    assert "profile.upload_count = (profile.upload_count or 0) + 1" in source
    assert "profile.trust_score = (profile.trust_score or 0) + 2" in source
    assert "await create_notification" in source
