"""Database-backed Paper Intelligence queue and worker operations."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from models.paper_processing import PaperProcessingJob
from models.papers import Papers
from services.passage_indexing import PassageIndexService

logger = logging.getLogger(__name__)
PROCESSING_VERSION = "v2_structured"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class PaperProcessingService:
    def __init__(self, db):
        self.db = db

    async def enqueue(self, paper: Papers, *, processing_version: str = PROCESSING_VERSION) -> PaperProcessingJob:
        """Create one idempotent run record after a paper is durably received."""
        existing = (await self.db.execute(select(PaperProcessingJob).where(
            PaperProcessingJob.paper_id == paper.id,
            PaperProcessingJob.processing_version == processing_version,
        ))).scalar_one_or_none()
        if existing:
            return existing
        job = PaperProcessingJob(
            paper_id=paper.id,
            processing_version=processing_version,
            status="QUEUED",
            progress_message="Paper received; waiting for academic processing.",
        )
        self.db.add(job)
        paper.extraction_status = "QUEUED"
        paper.extraction_version = processing_version
        return job

    async def claim_next(self) -> PaperProcessingJob | None:
        """Atomically claim one queued/retryable job. PostgreSQL workers skip locks."""
        now = utc_now()
        # A worker can disappear mid-OCR. Reclaim only clearly stale leases;
        # normal jobs keep their PROCESSING state while actively running.
        await self.db.execute(
            update(PaperProcessingJob)
            .where(
                PaperProcessingJob.status == "PROCESSING",
                PaperProcessingJob.started_at.is_not(None),
                PaperProcessingJob.started_at < now - timedelta(hours=2),
                PaperProcessingJob.attempt_count < PaperProcessingJob.max_attempts,
            )
            .values(status="QUEUED", progress_message="Recovering a job after an interrupted worker.")
        )
        await self.db.commit()
        query = select(PaperProcessingJob).where(
            PaperProcessingJob.status == "QUEUED",
            PaperProcessingJob.attempt_count < PaperProcessingJob.max_attempts,
        ).order_by(PaperProcessingJob.created_at.asc()).limit(1)
        if self.db.bind and self.db.bind.dialect.name == "postgresql":
            query = query.with_for_update(skip_locked=True)
        job = (await self.db.execute(query)).scalar_one_or_none()
        if not job:
            return None
        # PostgreSQL's row lock protects the select/claim pair. The conditional
        # update is also essential for SQLite/local workers, which do not offer
        # SKIP LOCKED: only one concurrent claimant can change QUEUED here.
        claimed = await self.db.execute(
            update(PaperProcessingJob)
            .where(PaperProcessingJob.id == job.id, PaperProcessingJob.status == "QUEUED")
            .values(
                status="PROCESSING",
                started_at=now,
                updated_at=now,
                attempt_count=(job.attempt_count or 0) + 1,
                progress_message="Preparing document intelligence processing.",
            )
        )
        if claimed.rowcount != 1:
            await self.db.rollback()
            return None
        await self.db.commit()
        await self.db.refresh(job)
        return job

    async def process_job(self, job_id: int) -> PaperProcessingJob | None:
        job = await self.db.get(PaperProcessingJob, job_id)
        if not job or job.status != "PROCESSING":
            return job
        paper = await self.db.get(Papers, job.paper_id)
        if not paper or not paper.file_key:
            return await self._fail(job, "The preserved original document is unavailable for processing.")
        try:
            job.progress_message = "Extracting text, structure, and page provenance."
            paper.extraction_status = "PROCESSING"
            await self.db.commit()
            await PassageIndexService(self.db).index_paper(paper)
            # Indexing commits its material independently. Marking READY is a
            # separate durable transition so a crash cannot report readiness early.
            job.status = "READY"
            job.progress_message = "Academic processing complete; Study AI is ready."
            job.completed_at = utc_now()
            job.error_summary = None
            paper.extraction_status = "READY"
            from services.contribution_communications import record_contribution_event
            await record_contribution_event(
                self.db, event_type="PAPER_PROCESSING_COMPLETED", paper=paper, user_id=str(paper.user_id)
            )
            await self.db.commit()
            return job
        except Exception as exc:
            logger.exception("Paper processing failed for job_id=%s", job.id)
            return await self._fail(job, type(exc).__name__)

    async def _fail(self, job: PaperProcessingJob, message: str) -> PaperProcessingJob:
        paper = await self.db.get(Papers, job.paper_id)
        retryable = (job.attempt_count or 0) < (job.max_attempts or 1)
        job.status = "QUEUED" if retryable else "FAILED"
        job.progress_message = "Processing will be retried." if retryable else "Academic processing needs attention."
        job.error_summary = message[:500]
        if not retryable:
            job.completed_at = utc_now()
        if paper:
            paper.extraction_status = job.status
        await self.db.commit()
        return job

    async def retry(self, paper_id: int) -> PaperProcessingJob | None:
        job = (await self.db.execute(select(PaperProcessingJob).where(PaperProcessingJob.paper_id == paper_id).order_by(PaperProcessingJob.id.desc()).limit(1))).scalar_one_or_none()
        if not job:
            return None
        if job.status == "PROCESSING":
            return job
        job.status, job.attempt_count, job.error_summary = "QUEUED", 0, None
        job.progress_message = "Queued for another academic processing attempt."
        paper = await self.db.get(Papers, paper_id)
        if paper:
            paper.extraction_status = "QUEUED"
        await self.db.commit()
        return job
