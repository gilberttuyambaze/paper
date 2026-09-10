# System-health database heartbeat

The heartbeat performs a small authenticated database transaction only on the singleton `system_health_heartbeat` record. It never creates or changes users, content, uploads, analytics, sessions, or permissions.

Long-running FastAPI instances start one bounded scheduler task per process. It uses an in-process lock plus a PostgreSQL transaction advisory lock and row lock so simultaneous workers cannot consume the same persisted slot. Lambda/serverless deployments are detected through `IS_LAMBDA` and do not start that task.

For a sleeping/serverless deployment, configure an external scheduler (GitHub Actions, provider cron, or equivalent) to make an authenticated request at least daily to `POST /api/v1/admin/settings/heartbeat/run`:

```text
External scheduler -> authenticated POST -> FastAPI -> Heartbeat service -> Supabase/Postgres
```

The caller must use a real application account with `system.health.manage`; the endpoint is not anonymous and never exposes database credentials. The endpoint returns `disabled` without writing if the feature is disabled.

Supabase alone determines inactivity and pausing according to its current platform rules. This mechanism provides legitimate low-volume database activity; it cannot guarantee a project will never be paused.
