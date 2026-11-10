# API reference

The live OpenAPI contract at `/openapi.json` and interactive `/docs` are the authoritative request schemas. All business routes use `/api/v1` and require a bearer token; health is public.

- Identity: GET /me and /users; POST /auth/rotate.
- Data: POST /data/upload, /data/records, /data/upload/preview, /data/preview; GET /data/datasets and /{id}, /{id}/quality, /{id}/transactions, /{id}/original, /{id}/masked-transactions; GET/POST /data/mappings.
- Integrations: POST /integrations/http/import and /integrations/database/import, using operator environment configuration rather than arbitrary user URLs/SQL.
- Reconciliation: POST/GET /reconciliation; GET /{id}; POST /{id}/run and /{id}/manual-match; GET /{id}/matches and /{id}/exceptions.
- Match review: POST /matches/{id}/review with an accept/reject decision and reason.
- Exceptions: GET /exceptions and /{id}, /{id}/analysis, /{id}/reflections, /{id}/agents, /{id}/checkpoints; POST /{id}/investigate, /{id}/corrections/propose, /{id}/verify-resolution, /{id}/assign.
- Corrections: GET /corrections; POST /{id}/validate, /approve, /reject, /execute, /reverse.
- Asynchronous jobs: POST /tasks; GET /tasks/{id}; process through `python -m app.worker`.
- Controls: GET/POST /settings/policy and /settings/accounts.
- ML: POST /ml/train; GET /ml/models; POST /ml/models/{id}/rank.
- Reports: GET /reports/reconciliation/{id}, /reports/performance, /reports/exceptions, /reports/aging, /reports/corrections, /reports/audit. Reconciliation/aging/correction/audit exports support format=json,csv,pdf.
- Demonstrations: POST /demo for bank data; POST /demo/{kind} for ap, ar, gateway, intercompany or gl.
- Audit/health: GET /audit and /health.

Money is serialized as decimal strings. execute/reverse require an Idempotency-Key of 8-120 characters. Reusing a key for another proposal/operation returns 409. Lists for datasets/jobs/exceptions/audits and transaction rows take offset/limit, capped at 200; the client fetches subsequent pages. Per-job match lists and correction lists currently have different collection limits documented in code; large installations should supply server-side filtered queries instead of loading whole workspaces.

Errors use 401 identity, 403 role/policy, 404 unavailable or other-tenant resources, 409 invalid state/conflict, 413 request size, 422 invalid schema, 429 rate limit, and 502/503 integration/provider failures. Raw source/provider error details are not returned as tracebacks.
