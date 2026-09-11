import asyncio
import json
import logging
import os
import random
from datetime import datetime, timedelta, timezone
from time import monotonic

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from models.site_settings import SiteSettings
from models.system_health import SystemHealthHeartbeat

logger = logging.getLogger(__name__)
HEARTBEAT_LOCK = asyncio.Lock()
ADVISORY_LOCK_ID = 614_201_771
MAX_WEEKLY_CHECKS, MAX_RETRY_HOURS, MAX_RETRIES, MAX_JITTER_MINUTES = 7, 72, 5, 720
RECENT_ATTEMPT_GUARD_SECONDS = 30
HEARTBEAT_ACTIVITY_SUBSCRIBERS: set[asyncio.Queue] = set()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


async def _notify_admin_of_heartbeat(settings: SiteSettings, health_data: dict) -> None:
    if not getattr(settings, "heartbeat_notify_admin", True):
        return
    if os.getenv("HEARTBEAT_NOTIFY_ADMIN", "true").strip().lower() in {"0", "false", "no", "off"}:
        return

    target_email = os.getenv("ADMIN_USER_EMAIL") or os.getenv("SUPER_ADMIN_USER_EMAIL")
    target_name = "Administrator"

    if not target_email:
        from core.database import db_manager
        session_factory = db_manager.async_session_maker
        if session_factory:
            try:
                from models.auth import User
                async with session_factory() as db:
                    admin_user = (await db.execute(
                        select(User).where(User.role.in_(["super_admin", "admin"])).order_by(User.role.desc()).limit(1)
                    )).scalar_one_or_none()
                    if admin_user:
                        target_email = admin_user.email
                        target_name = admin_user.name or admin_user.email
            except Exception:
                logger.exception("Failed to query admin for heartbeat notification")

    if not target_email:
        logger.debug("No admin email found for heartbeat notification")
        return

    try:
        from services.mailer import send_system_heartbeat_email
        await send_system_heartbeat_email(target_email, target_name, health_data)
        await publish_heartbeat_activity(f"Admin heartbeat report emailed to {target_email[:3]}***.", "notified")
    except Exception:
        logger.exception("Failed to deliver heartbeat email notification to admin")


def validate_heartbeat_config(values: dict) -> None:
    minimum, maximum = int(values.get("heartbeat_min_weekly_checks", 2)), int(values.get("heartbeat_max_weekly_checks", 3))
    delay, retries, jitter = int(values.get("heartbeat_retry_delay_hours", 6)), int(values.get("heartbeat_max_retry_attempts", 2)), int(values.get("heartbeat_retry_jitter_minutes", 30))
    if not 1 <= minimum <= MAX_WEEKLY_CHECKS or not minimum <= maximum <= MAX_WEEKLY_CHECKS:
        raise ValueError("Weekly checks must be between 1 and 7, with maximum at least minimum")
    if not 1 <= delay <= MAX_RETRY_HOURS: raise ValueError("Retry delay must be between 1 and 72 hours")
    if not 0 <= retries <= MAX_RETRIES: raise ValueError("Maximum retry attempts must be between 0 and 5")
    if not 0 <= jitter <= MAX_JITTER_MINUTES: raise ValueError("Retry jitter must be between 0 and 720 minutes")


def generate_week_schedule(week_start: datetime, minimum: int, maximum: int, rng=random) -> list[datetime]:
    validate_heartbeat_config({"heartbeat_min_weekly_checks": minimum, "heartbeat_max_weekly_checks": maximum})
    start = _utc(week_start).replace(hour=0, minute=0, second=0, microsecond=0)
    count = rng.randint(minimum, maximum)
    # Unique days give at least 24 hours between normal scheduled activity.
    return sorted(start + timedelta(days=day, hours=rng.randrange(6, 23), minutes=rng.randrange(0, 60)) for day in rng.sample(range(7), count))


def _decode_schedule(raw: str | None) -> list[datetime]:
    try: return sorted(_utc(datetime.fromisoformat(item)) for item in json.loads(raw or "[]") if isinstance(item, str))
    except (ValueError, TypeError, json.JSONDecodeError): return []


def _encode_schedule(values: list[datetime]) -> str:
    return json.dumps([_utc(value).isoformat() for value in values])


def _sanitize_error(error: Exception) -> str:
    name, message = type(error).__name__, str(error).replace("\n", " ").strip()
    if any(marker in message.lower() for marker in ("password", "secret", "token", "postgres://", "postgresql://", "@")): return name
    return f"{name}: {message[:180]}" if message else name


async def publish_heartbeat_activity(message: str, state: str) -> None:
    event = {"message": message, "state": state, "timestamp": utc_now().isoformat()}
    logger.info("[heartbeat:%s] %s", state, message)
    for subscriber in tuple(HEARTBEAT_ACTIVITY_SUBSCRIBERS):
        if not subscriber.full():
            subscriber.put_nowait(event)


async def heartbeat_activity_stream():
    subscriber: asyncio.Queue = asyncio.Queue(maxsize=20)
    HEARTBEAT_ACTIVITY_SUBSCRIBERS.add(subscriber)
    try:
        logger.info("[heartbeat:stream] Backend heartbeat log stream connected")
        yield {"message": "Connected to the backend heartbeat log stream.", "state": "connected", "timestamp": utc_now().isoformat()}
        while True:
            try:
                yield await asyncio.wait_for(subscriber.get(), timeout=15)
            except asyncio.TimeoutError:
                yield {"message": "Monitoring is active; waiting for the next heartbeat action.", "state": "waiting", "timestamp": utc_now().isoformat()}
    finally:
        HEARTBEAT_ACTIVITY_SUBSCRIBERS.discard(subscriber)
        logger.info("[heartbeat:stream] Backend heartbeat log stream disconnected")


async def _row_for_update(db: AsyncSession) -> SystemHealthHeartbeat:
    return (await db.execute(select(SystemHealthHeartbeat).where(SystemHealthHeartbeat.id == 1).with_for_update())).scalar_one()


async def _try_database_lock(db: AsyncSession) -> bool:
    if db.bind and db.bind.dialect.name == "postgresql":
        return bool((await db.execute(text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": ADVISORY_LOCK_ID})).scalar_one())
    return True


def _ensure_schedule(row: SystemHealthHeartbeat, settings: SiteSettings, now: datetime) -> None:
    slots = [item for item in _decode_schedule(row.schedule) if item > now]
    if not slots:
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        slots = [item for item in generate_week_schedule(start, settings.heartbeat_min_weekly_checks, settings.heartbeat_max_weekly_checks) if item > now]
        if not slots: slots = generate_week_schedule(start + timedelta(days=7), settings.heartbeat_min_weekly_checks, settings.heartbeat_max_weekly_checks)
    row.schedule, row.next_scheduled_at = _encode_schedule(slots), slots[0]


def heartbeat_status(row: SystemHealthHeartbeat, settings: SiteSettings, scheduler_running: bool) -> dict:
    if not settings.heartbeat_enabled: state = "disabled"
    elif row.next_retry_at: state = "retrying"
    elif (row.consecutive_failures or 0) >= max(1, settings.heartbeat_max_retry_attempts): state = "failed"
    elif row.consecutive_failures: state = "degraded"
    elif row.next_scheduled_at: state = "healthy"
    else: state = "pending"
    messages = {"disabled": "The heartbeat is turned off, so no database checks are being scheduled.", "retrying": "The last check failed. The system is waiting before trying again.", "failed": "The heartbeat has reached its retry limit. Review the database connection.", "degraded": "The heartbeat is working, but recent checks have reported failures.", "healthy": "The database health check completed successfully and the next check is scheduled.", "pending": "The heartbeat is preparing its next database health check."}
    return {"enabled": bool(settings.heartbeat_enabled), "scheduler_running": scheduler_running, "last_attempt_at": row.last_attempt_at, "last_success_at": row.last_success_at, "last_failure_at": row.last_failure_at, "next_scheduled_at": row.next_scheduled_at, "next_retry_at": row.next_retry_at, "total_attempts": row.total_attempts or 0, "total_successes": row.total_successes or 0, "total_failures": row.total_failures or 0, "consecutive_failures": row.consecutive_failures or 0, "retry_attempts": row.retry_attempts or 0, "last_duration_ms": row.last_duration_ms, "status": state, "activity_message": messages[state]}


async def _success(db: AsyncSession, row: SystemHealthHeartbeat, settings: SiteSettings, now: datetime, consume_slot: bool) -> dict:
    started = monotonic()
    row.last_attempt_at, row.total_attempts = now, (row.total_attempts or 0) + 1
    if consume_slot:
        remaining = [item for item in _decode_schedule(row.schedule) if item > now]
        row.schedule, row.next_scheduled_at = _encode_schedule(remaining), (remaining[0] if remaining else None)
    await db.flush()  # minimal, legitimate transaction on only the health row
    row.total_successes, row.consecutive_failures = (row.total_successes or 0) + 1, 0
    row.retry_attempts, row.next_retry_at, row.last_success_at, row.last_error = 0, None, now, None
    row.last_duration_ms = max(0, int((monotonic() - started) * 1000))
    _ensure_schedule(row, settings, now)
    await db.commit()

    health_data = {
        "status": "healthy",
        "duration_ms": row.last_duration_ms or 0,
        "mode": "Scheduled Check" if consume_slot else "Manual Check",
        "total_attempts": row.total_attempts or 0,
        "total_successes": row.total_successes or 0,
        "next_scheduled": row.next_scheduled_at.strftime("%Y-%m-%d %H:%M UTC") if row.next_scheduled_at else "Not scheduled",
    }
    asyncio.create_task(_notify_admin_of_heartbeat(settings, health_data))

    return {"executed": True, "success": True, "reason": "ok"}


async def _failure(db: AsyncSession, settings: SiteSettings, now: datetime, error: Exception) -> dict:
    await db.rollback()
    try:
        row = await _row_for_update(db)
        row.last_attempt_at, row.total_attempts = now, (row.total_attempts or 0) + 1
        row.total_failures, row.consecutive_failures = (row.total_failures or 0) + 1, (row.consecutive_failures or 0) + 1
        row.last_failure_at, row.last_error = now, _sanitize_error(error)
        retry = (row.retry_attempts or 0) + 1
        if settings.heartbeat_retry_enabled and retry <= settings.heartbeat_max_retry_attempts:
            row.retry_attempts = retry
            row.next_retry_at = now + timedelta(hours=settings.heartbeat_retry_delay_hours, minutes=random.randint(0, settings.heartbeat_retry_jitter_minutes))
        else:
            row.retry_attempts, row.next_retry_at = min(retry, settings.heartbeat_max_retry_attempts), None
        _ensure_schedule(row, settings, now)
        await db.commit()

        health_data = {
            "status": "failed",
            "duration_ms": 0,
            "mode": "Database Health Check",
            "total_attempts": getattr(row, "total_attempts", 1),
            "total_successes": getattr(row, "total_successes", 0),
            "next_scheduled": row.next_retry_at.strftime("%Y-%m-%d %H:%M UTC") if getattr(row, "next_retry_at", None) else "Not scheduled",
        }
        asyncio.create_task(_notify_admin_of_heartbeat(settings, health_data))
    except Exception:
        await db.rollback()
        logger.exception("Unable to persist heartbeat failure telemetry")
    return {"executed": True, "success": False, "reason": "database_error"}



async def run_heartbeat_once(db: AsyncSession, settings: SiteSettings, now: datetime | None = None, manual: bool = False) -> dict:
    """A manually requested attempt obeys disabled policy and never consumes a slot."""
    now = _utc(now or utc_now())
    if not settings.heartbeat_enabled: return {"executed": False, "success": False, "reason": "disabled"}
    await publish_heartbeat_activity("Starting a manual database health check.", "checking")
    async with HEARTBEAT_LOCK:
        if not await _try_database_lock(db):
            await db.rollback(); return {"executed": False, "success": False, "reason": "claimed_by_another_instance"}
        try:
            row = await _row_for_update(db)
            if manual and row.last_attempt_at and (now - _utc(row.last_attempt_at)).total_seconds() < RECENT_ATTEMPT_GUARD_SECONDS:
                await db.commit()
                await publish_heartbeat_activity("This check was skipped because an identical check was recorded recently.", "skipped")
                return {"executed": False, "success": False, "reason": "already_recorded_recently"}
            await publish_heartbeat_activity("The health result is being recorded in the dedicated system-health table.", "recording")
            result = await _success(db, row, settings, now, not manual)
            await publish_heartbeat_activity("Database health check completed successfully.", "completed")
            await publish_heartbeat_activity("This check is complete. The scheduler is idle until the next scheduled run.", "idle")
            return result
        except Exception as error:
            result = await _failure(db, settings, now, error)
            await publish_heartbeat_activity("The database health check failed; the retry policy is being evaluated.", "failed")
            return result


async def run_due_heartbeat(db: AsyncSession, settings: SiteSettings, now: datetime | None = None, startup: bool = False) -> dict:
    now = _utc(now or utc_now())
    if not settings.heartbeat_enabled: return {"executed": False, "success": False, "reason": "disabled"}
    async with HEARTBEAT_LOCK:
        if not await _try_database_lock(db):
            await db.rollback(); return {"executed": False, "success": False, "reason": "claimed_by_another_instance"}
        row = await _row_for_update(db)
        _ensure_schedule(row, settings, now)
        retry_due = bool(row.next_retry_at and row.next_retry_at <= now)
        due = retry_due or bool(row.next_scheduled_at and row.next_scheduled_at <= now) or (startup and settings.heartbeat_run_on_startup)
        if not due:
            await db.commit(); return {"executed": False, "success": False, "reason": "not_due"}
        try:
            await publish_heartbeat_activity("The scheduler is running the planned database health check.", "checking")
            await publish_heartbeat_activity("The health result is being recorded in the dedicated system-health table.", "recording")
            result = await _success(db, row, settings, now, not retry_due)
            await publish_heartbeat_activity("Scheduled database health check completed successfully.", "completed")
            await publish_heartbeat_activity("This check is complete. The scheduler is idle until the next scheduled run.", "idle")
            return result
        except Exception as error:
            result = await _failure(db, settings, now, error)
            await publish_heartbeat_activity("The scheduled database health check failed; the retry policy is being evaluated.", "failed")
            return result


async def scheduler_loop(session_factory, stop_event: asyncio.Event, startup: bool = False) -> None:
    """One bounded task per app process; no Lambda caller starts this loop."""
    while not stop_event.is_set():
        delay = 900
        try:
            async with session_factory() as db:
                settings = await db.get(SiteSettings, 1)
                from services.communication_jobs import run_communication_maintenance
                await run_communication_maintenance(db)
                if settings:
                    await run_due_heartbeat(db, settings, startup=startup)
                    row = await db.get(SystemHealthHeartbeat, 1)
                    events = [item for item in (row.next_scheduled_at, row.next_retry_at) if item]
                    if events: delay = max(1, min(900, int((min(events) - utc_now()).total_seconds())))
        except Exception: logger.exception("Heartbeat scheduler cycle failed")
        startup = False
        try: await asyncio.wait_for(stop_event.wait(), timeout=delay)
        except asyncio.TimeoutError: pass
