"""Database-backed Paper Intelligence queue and worker operations."""

from __future__ import annotations

import logging
import json
import os
import socket
import uuid
from time import monotonic
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select, update
from sqlalchemy.exc import IntegrityError

from models.paper_processing import PaperProcessingJob
from models.papers import Papers
from services.passage_indexing import PassageIndexService

logger = logging.getLogger(__name__)
PROCESSING_VERSION = "v2_structured"
DEFAULT_STALE_MINUTES = 20


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class PaperProcessingService:
    def __init__(self, db):
        self.db = db

    @staticmethod
    def _trace(event: str, job: PaperProcessingJob, **fields) -> None:
        """Emit one grep-friendly, secret-free lifecycle record."""
        context = " ".join(f"{key}={value}" for key, value in fields.items() if value is not None)
        logger.info("%s paper_id=%s job_id=%s attempt=%s %s", event, job.paper_id, job.id, job.attempt_count, context)

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
        logger.info("PROCESSING_JOB_CREATED paper_id=%s job_id=pending status=QUEUED", paper.id)
        return job

    async def claim_next(self) -> PaperProcessingJob | None:
        """Atomically claim one queued/retryable job. PostgreSQL workers skip locks."""
        now = utc_now()
        logger.info("PROCESSING_JOB_CLAIM_ATTEMPT worker_id=%s", socket.gethostname())
        # A worker can disappear mid-OCR. Reclaim only clearly stale leases;
        # normal jobs keep their PROCESSING state while actively running.
        stale_after = now - timedelta(minutes=max(5, int(os.getenv("PAPER_PROCESSING_STALE_MINUTES", str(DEFAULT_STALE_MINUTES)))))
        await self.db.execute(
            update(PaperProcessingJob)
            .where(
                PaperProcessingJob.status == "PROCESSING",
                PaperProcessingJob.started_at.is_not(None),
                PaperProcessingJob.started_at < stale_after,
                or_(
                    PaperProcessingJob.heartbeat_at.is_(None),
                    PaperProcessingJob.heartbeat_at < stale_after,
                ),
                PaperProcessingJob.attempt_count < PaperProcessingJob.max_attempts,
            )
            .values(
                status="QUEUED",
                current_stage="RECOVERING",
                progress_message="Recovering a job after an interrupted worker.",
            )
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
                heartbeat_at=now,
                updated_at=now,
                attempt_count=(job.attempt_count or 0) + 1,
                current_stage="PREPARING",
                pages_total=None,
                pages_completed=0,
                percent_complete=1,
                metrics_json=None,
                progress_message="Preparing document intelligence processing.",
            )
        )
        if claimed.rowcount != 1:
            await self.db.rollback()
            return None
        await self.db.commit()
        await self.db.refresh(job)
        self._trace("PROCESSING_JOB_CLAIMED", job, worker_id=socket.gethostname(), stage=job.current_stage)
        return job

    async def process_job(self, job_id: int) -> PaperProcessingJob | None:
        job = await self.db.get(PaperProcessingJob, job_id)
        if not job or job.status != "PROCESSING":
            return job
        paper = await self.db.get(Papers, job.paper_id)
        if not paper or not paper.file_key:
            return await self._fail(job, "The preserved original document is unavailable for processing.")
        try:
            run_id = uuid.uuid4().hex[:12]
            self._trace("PAPER_PROCESSING_START", job, run_id=run_id, worker_id=socket.gethostname())
            started = monotonic()
            last_persisted = 0.0

            async def report_progress(event: dict) -> None:
                """Persist truthful stage/page progress without committing per OCR box."""
                nonlocal last_persisted
                now_monotonic = monotonic()
                force = event.get("stage") in {"DOWNLOADING", "CLASSIFYING", "STRUCTURING", "EMBEDDING", "PERSISTING", "VALIDATING"}
                if not force and now_monotonic - last_persisted < 2.0:
                    return
                last_persisted = now_monotonic
                job.current_stage = str(event.get("stage") or job.current_stage or "PROCESSING")[:64]
                job.progress_message = str(event.get("message") or job.progress_message or "Processing academic content.")[:255]
                if event.get("pages_total") is not None:
                    job.pages_total = int(event["pages_total"])
                if event.get("pages_completed") is not None:
                    job.pages_completed = int(event["pages_completed"])
                if event.get("percent_complete") is not None:
                    job.percent_complete = max(0, min(99, int(event["percent_complete"])))
                job.heartbeat_at = utc_now()
                await self.db.commit()
                self._trace("PROCESSING_JOB_HEARTBEAT", job, run_id=run_id, stage=job.current_stage, pages_completed=job.pages_completed, pages_total=job.pages_total)

            job.current_stage = "EXTRACTING"
            job.progress_message = "Extracting text, structure, and page provenance."
            paper.extraction_status = "PROCESSING"
            await self.db.commit()
            index_result = await PassageIndexService(self.db).index_paper(paper, progress_callback=report_progress)
            if not index_result.get("ingestion_succeeded"):
                raise RuntimeError(index_result.get("error") or "Document ingestion did not complete")
            # Indexing commits its material independently. Marking READY is a
            # separate durable transition so a crash cannot report readiness early.
            job.status = "READY"
            job.current_stage = "READY"
            job.progress_message = "Academic processing complete; Study AI is ready."
            job.percent_complete = 100
            job.heartbeat_at = utc_now()
            job.metrics_json = json.dumps({**index_result.get("metrics", {}), "total_duration_ms": round((monotonic() - started) * 1000)})
            job.completed_at = utc_now()
            job.error_summary = None
            paper.extraction_status = "READY"
            from services.contribution_communications import record_contribution_event
            await record_contribution_event(
                self.db, event_type="PAPER_PROCESSING_COMPLETED", paper=paper, user_id=str(paper.user_id)
            )
            await self.db.commit()
            self._trace("PAPER_PROCESSING_COMPLETE", job, run_id=run_id, stage="READY", total_duration_ms=round((monotonic() - started) * 1000), passages=index_result.get("passages"))
            return job
        except Exception as exc:
            logger.exception("Paper processing failed for job_id=%s", job.id)
            # Persist a bounded diagnostic for operators. The client only sees
            # the safe state/message, never this internal detail.
            # PostgreSQL rejects every later statement after a SQL error until
            # the transaction is rolled back.  Reload by ID after rollback so
            # the failure record is written through a clean transaction rather
            # than masking the original error with InFailedSQLTransactionError.
            failed_job_id = job.id
            try:
                await self.db.rollback()
            except Exception:
                logger.exception("PROCESSING_JOB_ROLLBACK_FAILED job_id=%s", failed_job_id)
                raise
            return await self._fail(failed_job_id, f"{type(exc).__name__}: {exc}")

    async def _fail(self, job: PaperProcessingJob | int, message: str) -> PaperProcessingJob:
        if isinstance(job, int):
            reloaded = await self.db.get(PaperProcessingJob, job)
            if not reloaded:
                raise RuntimeError(f"Processing job {job} disappeared before failure could be persisted")
            job = reloaded
        paper = await self.db.get(Papers, job.paper_id)
        retryable = (job.attempt_count or 0) < (job.max_attempts or 1)
        job.status = "QUEUED" if retryable else "FAILED"
        job.current_stage = "RETRYING" if retryable else "FAILED"
        job.progress_message = "Processing will be retried." if retryable else "Academic processing needs attention."
        job.error_summary = message[:500]
        if not retryable:
            job.completed_at = utc_now()
        if paper:
            paper.extraction_status = job.status
        await self.db.commit()
        self._trace("PROCESSING_JOB_RETRY" if retryable else "PROCESSING_JOB_FAILED", job, stage=job.current_stage, error_type=message.split(":", 1)[0], retryable=retryable)
        return job

    async def retry(self, paper_id: int) -> PaperProcessingJob | None:
        job = (await self.db.execute(select(PaperProcessingJob).where(PaperProcessingJob.paper_id == paper_id).order_by(PaperProcessingJob.id.desc()).limit(1))).scalar_one_or_none()
        if not job:
            return None
        if job.status == "PROCESSING":
            return job
        job.status, job.attempt_count, job.error_summary = "QUEUED", 0, None
        job.current_stage, job.pages_completed, job.percent_complete = "QUEUED", 0, 0
        job.pages_total, job.completed_at, job.heartbeat_at, job.metrics_json = None, None, None, None
        job.progress_message = "Queued for another academic processing attempt."
        paper = await self.db.get(Papers, paper_id)
        if paper:
            paper.extraction_status = "QUEUED"
        await self.db.commit()
        return job
