"""Run a durable communication-outbox worker separately from OCR processing.

Usage: ``PYTHONPATH=. python scripts/process_communication_events.py``
"""

import asyncio
import logging
import os
import socket
from services.mailer import brevo_is_configured

from core.database import db_manager
from services.contribution_communications import deliver_pending_contribution_events

logger = logging.getLogger(__name__)


async def run() -> None:
    await db_manager.init_db()
    poll_seconds = max(1, int(os.getenv("COMMUNICATION_OUTBOX_POLL_SECONDS", "10")))
    logger.info("COMMUNICATION WORKER STARTED worker_id=%s poll_interval=%s brevo_configured=%s sender_configured=%s", socket.gethostname(), poll_seconds, brevo_is_configured(), bool(os.getenv("SMTP_FROM_EMAIL")))
    while True:
        try:
            async with db_manager.async_session_maker() as db:
                delivered = await deliver_pending_contribution_events(db)
                if delivered:
                    logger.info("Delivered %s contribution communication event(s)", delivered)
        except Exception:
            # Receipt emails are downstream from upload success. Keep polling
            # after a transient provider/database failure instead of silently
            # stranding pending events.
            logger.exception("Contribution communication worker cycle failed; retrying")
        await asyncio.sleep(poll_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    asyncio.run(run())
