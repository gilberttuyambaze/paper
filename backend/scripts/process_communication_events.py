"""Run a durable communication-outbox worker separately from OCR processing.

Usage: ``PYTHONPATH=. python scripts/process_communication_events.py``
"""

import asyncio
import logging
import os

from core.database import db_manager
from services.contribution_communications import deliver_pending_contribution_events


async def run() -> None:
    await db_manager.init_db()
    poll_seconds = max(1, int(os.getenv("COMMUNICATION_OUTBOX_POLL_SECONDS", "10")))
    while True:
        async with db_manager.async_session_maker() as db:
            await deliver_pending_contribution_events(db)
        await asyncio.sleep(poll_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    asyncio.run(run())
