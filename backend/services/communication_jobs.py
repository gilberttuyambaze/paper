"""Bounded, idempotent communication maintenance jobs."""

import logging
import os
from datetime import datetime, timedelta, timezone

from models.auth import PasswordResetRequestAttempt, PasswordResetToken, User
from services.communications import dispatch_communication
from services.mailer import _build_inactive_user_message
from sqlalchemy import delete, select, update

logger = logging.getLogger(__name__)


async def run_communication_maintenance(db, *, now: datetime | None = None) -> None:
    now = now or datetime.now(timezone.utc)
    await db.execute(delete(PasswordResetToken).where(PasswordResetToken.expires_at <= now))
    await db.execute(delete(PasswordResetRequestAttempt).where(PasswordResetRequestAttempt.created_at < now - timedelta(hours=24)))

    threshold_days = max(1, int(os.getenv("INACTIVE_USER_THRESHOLD_DAYS", "5")))
    cutoff = now - timedelta(days=threshold_days)
    users = (await db.execute(
        select(User).where(
            User.last_login.is_not(None),
            User.last_login <= cutoff,
            User.inactive_notification_sent_at.is_(None),
        ).limit(100)
    )).scalars().all()
    await db.commit()

    login_url = f"{os.getenv('FRONTEND_URL', 'https://paperhubur.vercel.app').rstrip('/')}/login"

    for user in users:
        claim = await db.execute(
            update(User)
            .where(User.id == user.id, User.inactive_notification_sent_at.is_(None))
            .values(inactive_notification_sent_at=now)
        )
        await db.commit()
        if claim.rowcount != 1:
            continue
        try:
            msg = _build_inactive_user_message(user.email, user.name or "there", login_url)
            sent = await dispatch_communication(
                db,
                event_type="INACTIVE_USER",
                user_id=user.id,
                recipient=user.email,
                subject=msg["subject"],
                text=msg["text"],
                html=msg["html"],
            )
            if not sent:
                await db.execute(update(User).where(User.id == user.id).values(inactive_notification_sent_at=None))
                await db.commit()
        except Exception:
            await db.rollback()
            await db.execute(update(User).where(User.id == user.id).values(inactive_notification_sent_at=None))
            await db.commit()
            logger.exception("Inactive-user communication job failed for one recipient")