from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from services.heartbeat import RECENT_ATTEMPT_GUARD_SECONDS, generate_week_schedule, heartbeat_status, validate_heartbeat_config


class DeterministicRandom:
    def randint(self, minimum, maximum): return minimum
    def sample(self, values, count): return list(values[:count])
    def randrange(self, start, stop): return start


def settings(**values):
    defaults = {"heartbeat_enabled": True, "heartbeat_min_weekly_checks": 2, "heartbeat_max_weekly_checks": 3, "heartbeat_retry_enabled": True, "heartbeat_retry_delay_hours": 6, "heartbeat_retry_jitter_minutes": 30, "heartbeat_max_retry_attempts": 2, "heartbeat_run_on_startup": True}
    return SimpleNamespace(**(defaults | values))


def row(**values):
    defaults = {"last_attempt_at": None, "last_success_at": None, "last_failure_at": None, "next_scheduled_at": None, "next_retry_at": None, "total_attempts": 0, "total_successes": 0, "total_failures": 0, "consecutive_failures": 0, "retry_attempts": 0, "last_duration_ms": None}
    return SimpleNamespace(**(defaults | values))


def test_schedule_has_two_or_three_separated_utc_slots():
    schedule = generate_week_schedule(datetime(2026, 8, 23, tzinfo=timezone.utc), 2, 3)
    assert 2 <= len(schedule) <= 3
    assert all(item.tzinfo == timezone.utc for item in schedule)
    assert len({item.date() for item in schedule}) == len(schedule)


def test_schedule_uses_server_randomness_when_injected():
    schedule = generate_week_schedule(datetime(2026, 8, 24, tzinfo=timezone.utc), 2, 3, DeterministicRandom())
    assert len(schedule) == 2
    assert [item.hour for item in schedule] == [6, 6]


@pytest.mark.parametrize("values", [{"heartbeat_min_weekly_checks": 0}, {"heartbeat_min_weekly_checks": 4, "heartbeat_max_weekly_checks": 2}, {"heartbeat_retry_delay_hours": 0}, {"heartbeat_retry_delay_hours": 73}, {"heartbeat_retry_jitter_minutes": -1}, {"heartbeat_max_retry_attempts": 6}])
def test_invalid_configuration_is_rejected(values):
    with pytest.raises(ValueError): validate_heartbeat_config(values)


def test_default_configuration_is_valid():
    validate_heartbeat_config({})


def test_recent_attempt_guard_is_short_and_positive():
    assert 0 < RECENT_ATTEMPT_GUARD_SECONDS <= 60


def test_status_reports_disabled_retrying_degraded_and_failed():
    assert heartbeat_status(row(), settings(heartbeat_enabled=False), False)["status"] == "disabled"
    assert heartbeat_status(row(next_retry_at=datetime.now(timezone.utc)), settings(), True)["status"] == "retrying"
    assert heartbeat_status(row(consecutive_failures=1), settings(heartbeat_max_retry_attempts=3), True)["status"] == "degraded"
    assert heartbeat_status(row(consecutive_failures=2), settings(heartbeat_max_retry_attempts=2), True)["status"] == "failed"


def test_heartbeat_notification_honors_admin_preference(monkeypatch):
    import asyncio
    from unittest.mock import AsyncMock, patch
    from services.heartbeat import _notify_admin_of_heartbeat

    async def run():
        # When enabled and admin email is configured
        monkeypatch.setenv("ADMIN_USER_EMAIL", "admin@ur.ac.rw")
        monkeypatch.delenv("HEARTBEAT_NOTIFY_ADMIN", raising=False)
        with patch("services.mailer.send_system_heartbeat_email", new=AsyncMock(return_value=True)) as mock_send:
            await _notify_admin_of_heartbeat(settings(heartbeat_notify_admin=True), {"status": "healthy"})
            assert mock_send.call_count == 1
            assert mock_send.call_args[0][0] == "admin@ur.ac.rw"

        # When admin turned off notification in settings
        with patch("services.mailer.send_system_heartbeat_email", new=AsyncMock(return_value=True)) as mock_send:
            await _notify_admin_of_heartbeat(settings(heartbeat_notify_admin=False), {"status": "healthy"})
            assert mock_send.call_count == 0

        # When disabled via environment variable
        monkeypatch.setenv("HEARTBEAT_NOTIFY_ADMIN", "false")
        with patch("services.mailer.send_system_heartbeat_email", new=AsyncMock(return_value=True)) as mock_send:
            await _notify_admin_of_heartbeat(settings(heartbeat_notify_admin=True), {"status": "healthy"})
            assert mock_send.call_count == 0

    asyncio.run(run())
