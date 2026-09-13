# Paper Intelligence worker deployment

Paper upload receipt and Paper Intelligence processing are intentionally separate.
The Render web service validates the contributor, stores the original PDF through
the existing storage flow, persists the paper and creates a `QUEUED`
`paper_processing_jobs` record. It must not run OCR or embeddings in the HTTP
request.

Deploy a separate Render Background Worker using the same backend source,
Python environment, database URL, storage credentials and AI/OCR configuration
as the web service.

```text
Build command: pip install -r backend/requirements.txt
Start command: cd backend && PYTHONPATH=. python scripts/process_paper_jobs.py
```

The worker polls the database (`PAPER_PROCESSING_POLL_SECONDS`, default `5`),
claims one job at a time, and runs the existing ingestion pipeline:

```text
QUEUED → PROCESSING → READY
                   └→ QUEUED (retry, at most three attempts) → FAILED
```

PostgreSQL workers use `FOR UPDATE SKIP LOCKED`; the claim transition also uses
a conditional update so local SQLite workers cannot claim the same queued job.
Jobs left in `PROCESSING` by an interrupted worker are reclaimed only after a
two-hour stale lease. The original PDF and submitted metadata are never removed
by a processing failure.

Contributor communication is an outbox event in `communication_events`. The
paper worker records `PAPER_PROCESSING_COMPLETED` only after READY. Deploy a
second, lightweight Render Background Worker to deliver contributor outbox
events independently of long-running OCR:

```text
Build command: pip install -r backend/requirements.txt
Start command: cd backend && PYTHONPATH=. python scripts/process_communication_events.py
```

It polls `COMMUNICATION_OUTBOX_POLL_SECONDS` (default `10`). Brevo delivery
failures are recorded and retried without changing paper receipt or processing
success. This separation ensures `PAPER_RECEIVED` is not delayed by an active
OCR job.
