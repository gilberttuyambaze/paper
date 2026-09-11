import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from dependencies.auth import get_current_user, get_optional_current_user


class FakeResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class FakeDb:
    def __init__(self, user):
        self.user = user

    async def get(self, model, user_id):
        return self.user

    async def execute(self, query):
        return FakeResult(None)


def test_required_auth_rejects_stale_session_version(monkeypatch):
    user = SimpleNamespace(id="user-1", role="normal", session_version=2, auth_provider="email", password_hash=None)
    db = FakeDb(user)
    monkeypatch.setattr("dependencies.auth.decode_access_token", lambda token: {"sub": "user-1", "session_version": 1})

    with pytest.raises(HTTPException) as error:
        asyncio.run(get_current_user("token", db))

    assert error.value.status_code == 401


def test_optional_auth_rejects_stale_session_version(monkeypatch):
    user = SimpleNamespace(id="user-1", role="normal", session_version=2)
    db = FakeDb(user)
    monkeypatch.setattr("dependencies.auth.decode_access_token", lambda token: {"sub": "user-1", "session_version": 1})

    assert asyncio.run(get_optional_current_user(SimpleNamespace(scheme="bearer", credentials="token"), db)) is None