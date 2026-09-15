"""Run by a dedicated worker process: ``PYTHONPATH=. python scripts/process_paper_jobs.py``."""

import asyncio
import logging
import os
import socket
from time import monotonic
from sqlalchemy import case, func, select
from models.paper_processing import PaperProcessingJob
from services.storage import StorageService

from core.database import db_manager
from services.paper_processing import PaperProcessingService

logger = logging.getLogger(__name__)


async def run() -> None:
    await db_manager.init_db()
    poll_seconds = max(1, int(os.getenv("PAPER_PROCESSING_POLL_SECONDS", "5")))
    worker_id = socket.gethostname()
    next_heartbeat = 0.0
    try:
        import pypdfium2  # noqa: F401
        from services.ocr.factory import get_ocr_provider
        ocr = await get_ocr_provider()
        logger.info("PAPER PROCESSING WORKER STARTED worker_id=%s poll_interval=%s storage_provider=%s ocr_available=%s pdf_engine_available=true", worker_id, poll_seconds, type(StorageService()._impl).__name__, bool(ocr))
    except Exception as exc:
        logger.exception("WORKER_STARTUP_FAILED component=paper_processing error_type=%s", type(exc).__name__)
        raise
    while True:
        try:
            async with db_manager.async_session_maker() as db:
                service = PaperProcessingService(db)
                job = await service.claim_next()
                if job:
                    await service.process_job(job.id)
                elif monotonic() >= next_heartbeat:
                    counts = (await db.execute(select(
                        func.sum(case((PaperProcessingJob.status == "QUEUED", 1), else_=0)),
                        func.sum(case((PaperProcessingJob.status == "PROCESSING", 1), else_=0)),
                    ))).one()
                    logger.info("PAPER_WORKER_HEARTBEAT worker_id=%s queued_jobs=%s processing_jobs=%s", worker_id, counts[0] or 0, counts[1] or 0)
                    next_heartbeat = monotonic() + 30
        except Exception:
            # A transient DB/storage failure must not kill the durable worker
            # and leave all later uploads in QUEUED.
            logger.exception("Paper processing worker cycle failed; retrying")
        await asyncio.sleep(poll_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    asyncio.run(run())
