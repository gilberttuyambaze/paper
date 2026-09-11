import asyncio
import hashlib
import logging
import os
from datetime import datetime, timezone

from core.database import db_manager
from models.communications import CommunicationEvent
from sqlalchemy import select
from services.mailer import (
    _build_account_invitation_message,
    _build_inactive_user_message,
    _build_new_login_message,
    _build_password_changed_message,
    _build_system_heartbeat_message,
    send_account_created_email,
    send_account_invitation_email,
    send_inactive_user_email,
    send_new_login_email,
    send_password_changed_email,
    send_password_reset_email,
    send_system_heartbeat_email,
    send_transactional_email,
)

logger = logging.getLogger(__name__)
_pending_delivery_tasks: set[asyncio.Task] = set()


def recipient_hash(email: str) -> str:
    return hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()


async def dispatch_communication(db, *, event_type: str, user_id: str | None, recipient: str, subject: str, text: str, html: str) -> bool:
    event = CommunicationEvent(event_type=event_type, user_id=user_id, recipient_hash=recipient_hash(recipient))
    db.add(event)
    try:
        sent = await send_transactional_email(recipient, subject, text, html)
    except Exception as exc:
        logger.warning("Communication delivery failed (event=%s, error=%s)", event_type, type(exc).__name__)
        sent = False
    event.status = "sent" if sent else "failed"
    event.error_category = None if sent else "provider_failure"
    event.sent_at = datetime.now(timezone.utc) if sent else None
    await db.commit()
    return sent


async def send_password_reset_event(db, user, reset_url: str, expires_at) -> bool:
    event = CommunicationEvent(event_type="PASSWORD_RESET", user_id=user.id, recipient_hash=recipient_hash(user.email))
    db.add(event)
    try:
        sent = await send_password_reset_email(user.email, reset_url, expires_at)
    except Exception as exc:
        logger.warning("Communication delivery failed (event=PASSWORD_RESET, error=%s)", type(exc).__name__)
        sent = False
    event.status = "sent" if sent else "failed"
    event.error_category = None if sent else "provider_failure"
    event.sent_at = datetime.now(timezone.utc) if sent else None
    await db.commit()
    return sent


async def _deliver_queued_password_reset(event_id: int, recipient: str, reset_url: str, expires_at) -> None:
    session_factory = db_manager.async_session_maker
    if not session_factory:
        return
    try:
        async with session_factory() as db:
            event = await db.get(CommunicationEvent, event_id)
            if not event:
                return
            try:
                sent = False
                for attempt in range(3):
                    event.retry_count = attempt
                    sent = await send_password_reset_email(recipient, reset_url, expires_at)
                    if sent:
                        break
                    if attempt < 2:
                        await asyncio.sleep(0.1)
                event.status = "sent" if sent else "failed"
                event.error_category = None if sent else "provider_failure"
                event.sent_at = datetime.now(timezone.utc) if sent else None
                await db.commit()
            except Exception as exc:
                await db.rollback()
                event = await db.get(CommunicationEvent, event_id)
                if event:
                    event.status = "failed"
                    event.error_category = type(exc).__name__[:64]
                    await db.commit()
                logger.warning("Queued password-reset delivery failed (event=%s, error=%s)", event_id, type(exc).__name__)
    except Exception:
        logger.exception("Queued password-reset delivery session failed")


async def queue_password_reset_event(db, user, reset_url: str, expires_at) -> None:
    event = CommunicationEvent(event_type="PASSWORD_RESET", user_id=user.id, recipient_hash=recipient_hash(user.email))
    db.add(event)
    await db.commit()
    task = asyncio.create_task(_deliver_queued_password_reset(event.id, user.email, reset_url, expires_at))
    _pending_delivery_tasks.add(task)
    task.add_done_callback(_pending_delivery_tasks.discard)


async def _deliver_queued_communication(
    event_id: int,
    recipient: str,
    subject: str,
    text: str,
    html: str,
) -> None:
    session_factory = db_manager.async_session_maker
    if not session_factory:
        return
    try:
        async with session_factory() as db:
            event = await db.get(CommunicationEvent, event_id)
            if not event:
                return
            try:
                sent = False
                for attempt in range(3):
                    event.retry_count = attempt
                    sent = await send_transactional_email(recipient, subject, text, html)
                    if sent:
                        break
                    if attempt < 2:
                        await asyncio.sleep(0.1)
                event.status = "sent" if sent else "failed"
                event.error_category = None if sent else "provider_failure"
                event.sent_at = datetime.now(timezone.utc) if sent else None
                await db.commit()
            except Exception as exc:
                await db.rollback()
                event = await db.get(CommunicationEvent, event_id)
                if event:
                    event.status = "failed"
                    event.error_category = type(exc).__name__[:64]
                    await db.commit()
                logger.warning("Queued communication delivery failed (event=%s, error=%s)", event_id, type(exc).__name__)
    except Exception:
        logger.exception("Queued communication delivery session failed")


async def queue_communication_event(
    db,
    *,
    event_type: str,
    user_id: str | None,
    recipient: str,
    subject: str,
    text: str,
    html: str,
) -> CommunicationEvent:
    event = CommunicationEvent(event_type=event_type, user_id=user_id, recipient_hash=recipient_hash(recipient))
    db.add(event)
    await db.commit()
    task = asyncio.create_task(_deliver_queued_communication(event.id, recipient, subject, text, html))
    _pending_delivery_tasks.add(task)
    task.add_done_callback(_pending_delivery_tasks.discard)
    return event


async def _deliver_queued_welcome(event_id: int, recipient: str, user_name: str, role: str, login_url: str) -> None:
    session_factory = db_manager.async_session_maker
    if not session_factory:
        return
    try:
        async with session_factory() as db:
            event = await db.get(CommunicationEvent, event_id)
            if not event:
                return
            try:
                sent = False
                for attempt in range(3):
                    event.retry_count = attempt
                    sent = await send_account_created_email(recipient, user_name, role, login_url)
                    if sent:
                        break
                    if attempt < 2:
                        await asyncio.sleep(0.1)
                event.status = "sent" if sent else "failed"
                event.error_category = None if sent else "provider_failure"
                event.sent_at = datetime.now(timezone.utc) if sent else None
                await db.commit()
            except Exception as exc:
                await db.rollback()
                event = await db.get(CommunicationEvent, event_id)
                if event:
                    event.status = "failed"
                    event.error_category = type(exc).__name__[:64]
                    await db.commit()
                logger.warning("Queued welcome delivery failed (event=%s, error=%s)", event_id, type(exc).__name__)
    except Exception:
        logger.exception("Queued welcome delivery session failed")


async def queue_welcome_event(db, user, login_url: str) -> CommunicationEvent:
    event = CommunicationEvent(event_type="WELCOME", user_id=user.id, recipient_hash=recipient_hash(user.email))
    db.add(event)
    await db.commit()
    task = asyncio.create_task(_deliver_queued_welcome(event.id, user.email, user.name or "there", user.role or "user", login_url))
    _pending_delivery_tasks.add(task)
    task.add_done_callback(_pending_delivery_tasks.discard)
    return event


async def queue_password_changed_event(db, user) -> CommunicationEvent:
    msg = _build_password_changed_message(user.email, user.name or "there", datetime.now(timezone.utc))
    return await queue_communication_event(
        db,
        event_type="PASSWORD_CHANGED",
        user_id=user.id,
        recipient=user.email,
        subject=msg["subject"],
        text=msg["text"],
        html=msg["html"],
    )


async def queue_new_login_event(db, user) -> CommunicationEvent:
    msg = _build_new_login_message(user.email, user.name or "there", datetime.now(timezone.utc))
    return await queue_communication_event(
        db,
        event_type="NEW_LOGIN",
        user_id=user.id,
        recipient=user.email,
        subject=msg["subject"],
        text=msg["text"],
        html=msg["html"],
    )


async def send_welcome_event(db, user, login_url: str) -> bool:
    event = CommunicationEvent(event_type="WELCOME", user_id=user.id, recipient_hash=recipient_hash(user.email))
    db.add(event)
    try:
        sent = await send_account_created_email(user.email, user.name or "there", user.role or "user", login_url)
    except Exception as exc:
        logger.warning("Communication delivery failed (event=WELCOME, error=%s)", type(exc).__name__)
        sent = False
    event.status = "sent" if sent else "failed"
    event.error_category = None if sent else "provider_failure"
    event.sent_at = datetime.now(timezone.utc) if sent else None
    await db.commit()
    return sent


async def send_password_changed_event(db, user) -> bool:
    msg = _build_password_changed_message(user.email, user.name or "there", datetime.now(timezone.utc))
    return await dispatch_communication(
        db,
        event_type="PASSWORD_CHANGED",
        user_id=user.id,
        recipient=user.email,
        subject=msg["subject"],
        text=msg["text"],
        html=msg["html"],
    )


async def send_new_login_event(db, user) -> bool:
    msg = _build_new_login_message(user.email, user.name or "there", datetime.now(timezone.utc))
    return await dispatch_communication(
        db,
        event_type="NEW_LOGIN",
        user_id=user.id,
        recipient=user.email,
        subject=msg["subject"],
        text=msg["text"],
        html=msg["html"],
    )


async def send_security_alert_event(db, user, alert_context: str) -> bool:
    return await dispatch_communication(
        db,
        event_type="SUSPICIOUS_LOGIN",
        user_id=user.id,
        recipient=user.email,
        subject="Security alert for your PaperHub account",
        text=f"We detected a sign-in that may need your attention. {alert_context} If this was not you, change your password and contact support.",
        html=f"<p>We detected a sign-in that may need your attention.</p><p>{alert_context}</p><p>If this was not you, change your password and contact support.</p>",
    )


async def send_account_invitation_event(db, recipient: str, invitation_url: str, inviter_name: str) -> bool:
    msg = _build_account_invitation_message(recipient, inviter_name, invitation_url)
    return await dispatch_communication(
        db,
        event_type="ACCOUNT_INVITATION",
        user_id=None,
        recipient=recipient,
        subject=msg["subject"],
        text=msg["text"],
        html=msg["html"],
    )


async def queue_account_invitation_event(db, recipient: str, invitation_url: str, inviter_name: str) -> CommunicationEvent:
    msg = _build_account_invitation_message(recipient, inviter_name, invitation_url)
    return await queue_communication_event(
        db,
        event_type="ACCOUNT_INVITATION",
        user_id=None,
        recipient=recipient,
        subject=msg["subject"],
        text=msg["text"],
        html=msg["html"],
    )


async def send_inactive_user_event(db, user, login_url: str | None = None) -> bool:
    url = login_url or f"{os.getenv('FRONTEND_URL', 'https://paperhubur.vercel.app').rstrip('/')}/login"
    msg = _build_inactive_user_message(user.email, user.name or "there", url)
    return await dispatch_communication(
        db,
        event_type="INACTIVE_USER",
        user_id=user.id,
        recipient=user.email,
        subject=msg["subject"],
        text=msg["text"],
        html=msg["html"],
    )


async def queue_inactive_user_event(db, user, login_url: str | None = None) -> CommunicationEvent:
    url = login_url or f"{os.getenv('FRONTEND_URL', 'https://paperhubur.vercel.app').rstrip('/')}/login"
    msg = _build_inactive_user_message(user.email, user.name or "there", url)
    return await queue_communication_event(
        db,
        event_type="INACTIVE_USER",
        user_id=user.id,
        recipient=user.email,
        subject=msg["subject"],
        text=msg["text"],
        html=msg["html"],
    )


async def send_system_heartbeat_event(db, recipient: str, admin_name: str, health_data: dict) -> bool:
    msg = _build_system_heartbeat_message(recipient, admin_name, health_data)
    return await dispatch_communication(
        db,
        event_type="SYSTEM_HEARTBEAT",
        user_id=None,
        recipient=recipient,
        subject=msg["subject"],
        text=msg["text"],
        html=msg["html"],
    )


async def queue_system_heartbeat_event(db, recipient: str, admin_name: str, health_data: dict) -> CommunicationEvent:
    msg = _build_system_heartbeat_message(recipient, admin_name, health_data)
    return await queue_communication_event(
        db,
        event_type="SYSTEM_HEARTBEAT",
        user_id=None,
        recipient=recipient,
        subject=msg["subject"],
        text=msg["text"],
        html=msg["html"],
    )