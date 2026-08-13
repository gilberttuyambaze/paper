# Paper Hub AI architecture

## Request path

The browser calls Paper Hub endpoints only. FastAPI authenticates the request,
then routes it through `AIService`, which selects a provider adapter. Provider
credentials never enter the frontend build or runtime configuration.

```text
Frontend -> /api/v1/aihub or /api/v1/study-ai -> AIService -> AIProvider -> provider API
```

`services/ai/base.py` contains provider-neutral requests, responses,
capabilities, and normalized errors. `services/ai/service.py` owns provider
selection, context/output limits, in-process per-user request limiting, safe
observability, and the explicit fallback policy. Provider-specific SDK code is
isolated in `services/ai/providers/`.

## OpenAI

Set `AI_ENABLED=true`, `AI_PROVIDER=openai`, `OPENAI_API_KEY`, and optionally
`OPENAI_MODEL`. The OpenAI adapter uses the official Python SDK Responses API
for text, streaming, structured outputs, and embeddings. It sets `store=false`
for Paper Hub requests. Image generation remains available through the existing
AI Hub route, now translated in the OpenAI adapter.

The default model is configuration, not application code. Choose a model that
supports the capabilities your route needs; the service checks declared provider
capabilities before dispatching. See the official [OpenAI quickstart](https://platform.openai.com/docs/quickstart/make-your-first-api-request) and [model documentation](https://developers.openai.com/api/docs/models/gpt-4o).

## Other providers and fallback

`openai_compatible` is an explicit adapter selection for a provider with a
Responses-compatible endpoint and its own `AI_COMPATIBLE_*` credentials. Adding
Anthropic, Gemini, or local models means implementing `AIProvider` in
`services/ai/providers/` and registering it in `AIProviderFactory`; routes do
not change.

`AI_FALLBACK_PROVIDER` is deliberately empty by default. Configuring it is an
explicit approval to send the same request, which can include authorized paper
context, to that provider after a provider-unavailable or rate-limit failure.

## Paper context and privacy

The current schema contains paper metadata and Google Drive file pointers, but
no extracted-PDF text, chunks, or vector index. Study AI therefore provides
only authorized metadata, recent discussion, and solutions, bounded by a
conservative character/token budget. It does not download or blindly submit a
complete PDF. `build_paper_context` is the insertion point for a future
authorized extraction/chunk/retrieval pipeline.

No database or Google Drive architecture changed. Supabase remains PostgreSQL;
Google Drive remains file storage.

## Limits, errors, and diagnostics

Configuration controls provider timeout, maximum input context, maximum output,
and a process-local per-user request limit. Logs record provider, model,
duration, request ID, success/failure, and available token counts; they do not
log prompts, document text, or credentials.

Errors are normalized as provider unavailable, authentication failure, rate
limit, timeout, context too large, invalid request, unavailable model, content
policy rejection, and malformed provider response. API consumers receive safe
messages rather than raw SDK exceptions.

## Local development and Render

Copy `backend/.env.example` to `backend/.env.local`, set the backend-only AI
values, and leave all `OPENAI_*` and `AI_COMPATIBLE_*` values out of frontend
environment files. For Render, configure the same values as encrypted server
environment variables; enable AI only after credentials and budget limits are
set. No database migration is required.
