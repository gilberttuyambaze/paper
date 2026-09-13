# UR Past Paper

## Overview

`UR Past Paper` is a full-stack learning repository that combines a FastAPI backend with a React + Vite frontend. The application supports paper uploads, solutions, search, user account handling, and storage integration.

## What it does

- Stores papers and solutions in a structured backend service.
- Allows authenticated users to upload and download documents.
- Supports file storage through a backend storage provider.
- Provides search and discovery for uploaded papers.
- Exposes an admin interface for storage inspection and debugging.

## Project structure

- `backend/` — FastAPI backend source code and Python services.
- `frontend/` — React application using Vite, Tailwind CSS, and type-safe API calls.

## Setup

### Backend

1. Create and activate a Python virtual environment.
2. Install Python dependencies.
3. Configure environment variables for the backend.
4. Run the backend server.

Example:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
export DATABASE_URL=sqlite:///./backend.db
export ENVIRONMENT=dev
export URHUD_AUTO_CREATE_TABLES=true
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

For the complete local contribution lifecycle, run the two durable workers in
separate terminals as well. They deliver acknowledgement emails and process
papers after the upload response has returned:

```bash
cd backend
PYTHONPATH=. python scripts/process_communication_events.py
# in another terminal
PYTHONPATH=. python scripts/process_paper_jobs.py
```

On Windows, `npm run dev:all` from `frontend/` starts the API, frontend, and
both workers together.

### Frontend

1. Install node dependencies.
2. Run the frontend server.

Example:

```bash
cd frontend
pnpm install
pnpm dev
```

## Storage

The backend can use different storage backends. The application currently supports:

- Supabase storage
- Google Drive storage integration

When Google Drive is enabled, uploaded documents are stored under a configured Drive folder and served through a backend proxy.

## Database Health Activity

The backend includes an optional, lightweight database heartbeat for Supabase-backed deployments. It updates one singleton system-health row and does not create users, resources, analytics, or other business records. The Super Admin can configure it in the Admin Dashboard under Database Health / Activity.

By default, the scheduler plans two to three checks per week with server-side randomized days and time windows. Failures are recorded and retried after several hours with bounded jitter and a maximum retry count. The in-process scheduler runs only while a long-lived FastAPI process is alive; sleeping/serverless deployments should invoke a protected external scheduler or cron job instead.

For sleeping/serverless deployments, a secret-bearing scheduler can call `POST /api/v1/admin/settings/heartbeat/run` with a current Super Admin bearer token. Never expose that token to browser code or anonymous callers.

This is a best-effort activity mechanism and does not guarantee that a Supabase Free project will never pause. Upgrading to a paid Supabase plan is the platform-supported way to eliminate automatic Free-plan pausing.

## Notes

- Keep the `backend/` and `frontend/` directories separated.
- The repository root now contains only the two main application folders and Git metadata.
- Environment and configuration files live inside the `frontend/` and `backend/` subdirectories.

## Styling

The frontend uses Tailwind CSS for a clean, responsive user interface. Styles are organized in the `frontend/src` tree inside the frontend app with component-based styling and utility-first classes.

## Contact

If you need help running the project, check the `frontend/package.json` scripts and backend startup commands in `backend/scripts/bootstrap_backend.py`.
