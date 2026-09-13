"""Run by a dedicated worker process: ``PYTHONPATH=. python scripts/process_paper_jobs.py``."""

import asyncio
import logging
import os

from core.database import db_manager
from services.paper_processing import PaperProcessingService


async def run() -> None:
    await db_manager.init_db()
    poll_seconds = max(1, int(os.getenv("PAPER_PROCESSING_POLL_SECONDS", "5")))
    while True:
        async with db_manager.async_session_maker() as db:
            service = PaperProcessingService(db)
            job = await service.claim_next()
            if job:
                await service.process_job(job.id)
        await asyncio.sleep(poll_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    asyncio.run(run())
