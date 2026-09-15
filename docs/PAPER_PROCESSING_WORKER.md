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
Jobs refresh a persisted heartbeat during stages and page processing. Jobs left
in `PROCESSING` with no heartbeat for `PAPER_PROCESSING_STALE_MINUTES` (default
`20`) are reclaimed safely after a crash; a healthy long OCR run is not
reclaimed merely because of elapsed time. The original PDF and submitted
metadata are never removed by a processing failure.

The worker image must include `pypdfium2`, `Pillow`, and
`rapidocr_onnxruntime`, all of which are now pinned through
`backend/requirements.txt`. These are required to render and OCR scanned or
mixed PDF pages; installing only `pypdf` supports native-text extraction but
cannot complete scanned-paper intelligence.

## Benchmarking a worker image

There are no committed production PDFs in this repository. To capture a
repeatable before/after measurement with approved fixtures, run the exact
ingestion pipeline locally or in the worker image:

```text
cd backend
PYTHONPATH=. python scripts/benchmark_document_ingestion.py /secure/fixture.pdf
```

The JSON result includes per-page classification/method/confidence and timing
for classification, rendering, OCR, vision fallback, structure extraction and
the total. Run it once each for a native-text, scanned and mixed fixture. Do
not treat queue delay as OCR time: the durable job's `started_at`,
`heartbeat_at`, `metrics_json`, and progress fields distinguish them.

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
