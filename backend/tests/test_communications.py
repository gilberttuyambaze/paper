import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from core.database import Base
from models.auth import PasswordResetRequestAttempt, PasswordResetToken, User
from models.communications import CommunicationEvent
from services.communication_jobs import run_communication_maintenance
from services.communications import (
    dispatch_communication,
    send_account_invitation_event,
    send_new_login_event,
    send_password_changed_event,
    send_password_reset_event,
    send_security_alert_event,
    send_welcome_event,
)


class FakeDb:
    def __init__(self):
        self.events = []
        self.commits = 0

    def add(self, value):
        self.events.append(value)

    async def commit(self):
        self.commits += 1


def test_all_communication_events_use_central_dispatcher():
    async def run():
        db = FakeDb()
        user = SimpleNamespace(id="user-1", email="person@example.com", name="Person", role="normal")
        with patch("services.communications.dispatch_communication", new=AsyncMock(return_value=True)) as dispatch:
            await send_password_reset_event(db, user, "https://paperhubur.vercel.app/reset-password?token=one-time", datetime.now(timezone.utc))
            await send_password_changed_event(db, user)
            await send_welcome_event(db, user, "https://paperhubur.vercel.app/login")
            await send_new_login_event(db, user)
            await send_security_alert_event(db, user, "A sign-in was recorded.")
            await send_account_invitation_event(db, "invite@example.com", "https://paperhubur.vercel.app/invite/abc", "Person")
        return dispatch.call_args_list

    calls = asyncio.run(run())
    assert [call.kwargs["event_type"] for call in calls] == [
        "PASSWORD_CHANGED",
        "NEW_LOGIN",
        "SUSPICIOUS_LOGIN",
        "ACCOUNT_INVITATION",
    ]


def test_mailer_success_is_recorded_as_sent():
    async def run():
        db = FakeDb()
        with patch("services.communications.send_transactional_email", new=AsyncMock(return_value=True)):
            return await dispatch_communication(
                db,
                event_type="PASSWORD_CHANGED",
                user_id="user-1",
                recipient="person@example.com",
                subject="Changed",
                text="Changed",
                html="<p>Changed</p>",
            ), db

    sent, db = asyncio.run(run())
    assert sent is True
    assert db.events[0].status == "sent"
    assert db.events[0].sent_at is not None


def test_inactivity_job_is_bounded_idempotent_and_isolates_failures(tmp_path, monkeypatch):
    async def run():
        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'communications.db'}")
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        now = datetime.now(timezone.utc)
        async with sessions() as db:
            db.add_all([
                User(id="old-1", email="old1@example.com", last_login=now - timedelta(days=6)),
                User(id="old-2", email="old2@example.com", last_login=now - timedelta(days=6)),
                User(id="recent", email="recent@example.com", last_login=now - timedelta(days=2)),
                PasswordResetToken(user_id="old-1", token_hash="expired", expires_at=now - timedelta(minutes=1)),
                PasswordResetRequestAttempt(request_key="old", created_at=now - timedelta(days=2)),
            ])
            await db.commit()

        calls = []
        async def dispatch(db, **kwargs):
            calls.append(kwargs["user_id"])
            if kwargs["user_id"] == "old-1":
                raise RuntimeError("one recipient failed")
            return True

        with patch("services.communication_jobs.dispatch_communication", side_effect=dispatch):
            async with sessions() as db:
                await run_communication_maintenance(db, now=now)
            async with sessions() as db:
                await run_communication_maintenance(db, now=now)
                users = {user.id: user for user in (await db.execute(select(User))).scalars().all()}
                expired = (await db.execute(select(PasswordResetToken))).scalars().all()
                attempts = (await db.execute(select(PasswordResetRequestAttempt))).scalars().all()
        await engine.dispose()
        return calls, users, expired, attempts

    calls, users, expired, attempts = asyncio.run(run())
    assert calls == ["old-1", "old-2", "old-1"]
    assert users["old-2"].inactive_notification_sent_at is not None
    assert users["old-1"].inactive_notification_sent_at is None
    assert not expired
    assert not attempts
