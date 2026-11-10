# Deployment and operations

Apply all Alembic migrations before serving requests. Local startup refuses an uninitialized database. The PowerShell launch/stop scripts manage only their recorded process IDs and creation times; they do not stop unrelated processes. A separate durable worker is required for queued tasks.

## Environment

| Variable | Purpose |
| --- | --- |
| DATABASE_URL | SQLite locally; PostgreSQL via postgresql+psycopg in deployment |
| EXECUTION_MODE | recommendation by default; only simulation permits internal adjustment records |
| LLM_PROVIDER / OPENAI_API_KEY / OPENAI_MODEL | mock by default; optional paid typed OpenAI reasoning/tool adapter |
| MAX_CORRECTION_ITERATIONS | 1–3, default three |
| DUAL_APPROVAL_THRESHOLD | Initial threshold for newly initialized tenant policies |
| CURRENCY_PRECISION_OVERRIDES | JSON map of registered ISO currency codes to 0–6 decimal places |
| RATE_LIMIT_PER_MINUTE / RATE_LIMIT_BACKEND | Local memory limiter or shared database counter; Compose uses database |
| ALLOW_LEGACY_TOKENS | false by default; only controlled compatibility/test use |
| FILE_ENCRYPTION_KEY | Base64 AES-256 key for retained original binaries |
| REQUIRE_FILE_ENCRYPTION | Refuse unencrypted binary retention when enabled |
| CORS_ORIGINS | Exact comma-separated frontend origins |
| FINANCIAL_SOURCE_URL / FINANCIAL_SOURCE_TOKEN | Operator-selected HTTPS JSON import; redirects disabled |
| FINANCIAL_SOURCE_DATABASE_URL | Read-only PostgreSQL/SQLite import from reconciliation_export view |
| POSTGRES_PASSWORD | Required URL-safe deployment secret for Compose |

Credential renewal is a local operator command: `cd backend; python -m app.issue_access --name analyst --org-id ORGANIZATION_ID`. It revokes old grants and writes a fresh eight-hour credential to the ignored local file. Authenticated POST /auth/rotate provides session rotation. Never commit credentials, encryption keys or database files.

Original binary encryption does not replace encrypted database volumes/backups or TLS. Use PostgreSQL SSL configuration, an authenticated TLS reverse proxy and appropriate storage/backups. Tenant retention duration is configuration; infrastructure archival, legal holds and backup lifecycle remain operator responsibilities. Immutable source/audit records are not silently deleted.

## Docker verification

The current Windows host provides docker and standalone docker-compose. `docker-compose config --quiet` succeeds with a supplied validation password. There is no running Docker engine and WSL is not installed. Container build/start and live PostgreSQL verification therefore remain unverified here. No operating-system feature installation or reboot was attempted.

CI defines PostgreSQL migrations and a synthetic integration script. On a dedicated PostgreSQL test/staging database, initialize identities, set RUN_FINANCIAL_SIMULATION_TESTS=1 and run `python scripts/verify_postgres.py`. It verifies ten-agent investigation, independent approval, idempotent simulation and reversal. Never use a production financial database for this test.

## Troubleshooting

- API test client stalls in a restricted Windows socketpair: run the same tests with loopback sockets available; do not weaken assertions.
- Access denied/expired: renew the local credential or rotate the active session; indefinite legacy tokens are off by default.
- Approval denied: switch to a different checker; high-value drafts need two distinct checkers.
- Stale proposal: a policy/account change invalidated its version. Reassessment/fresh approval is required; do not bypass the validator.
- Queued investigation remains queued: start `python -m app.worker`; inspect task status. Exhausted or abandoned leases escalate after three attempts.
- Unsupported correction: only evidenced bank-charge journals are executable simulations. Other discrepancies produce manual investigation recommendations, preserving financial controls.
- Port already in use: inspect the owning application. Launch scripts intentionally refuse to replace another server.
- Original file decryption fails: supply the same encryption key used at ingestion; do not overwrite encrypted source data.
- XLSX/CSV rejected: inspect row errors; use unique headers, unambiguous dates, matching debit/credit direction and currency precision.
