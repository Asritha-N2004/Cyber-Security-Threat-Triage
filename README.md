# Reconcile — Self-Correcting Financial Reconciliation

A working full-stack research platform with immutable financial imports, six specialized accounting workflows, a ten-agent LangGraph, independent accounting validation, bounded self-correction, human approvals, auditable simulation/reversal and evidence-based resolution.

Default reasoning is deterministic mock mode and default execution is recommendation-only. Paid-provider calls, real ERP postings and research superiority are not implied by a successful demo. See [implementation status](IMPLEMENTATION_STATUS.md) for verification evidence and remaining environment-dependent checks.

## Hosted dashboard

Open [Reconcile on Vercel](https://reconcile-agentic-ai.vercel.app). Choose **Create account**, enter a username and a password of at least 6 characters, then sign in. No email, access token, uppercase letter, number or symbol requirement. Usernames can include spaces and are case-insensitive. Each account receives a separate workspace; passwords are salted and hashed with scrypt, and sessions use revocable Secure/HttpOnly cookies. Execution remains recommendation-only.

Reconciliation details use `/reconciliation/workspace`, keeping the record UUID out of the visible address. The selected record is retained in browser navigation state and session storage for refresh/back navigation. Open a reconciliation from the list in a new browser session; old record links still redirect to the clean address after sign-in.

Deployment is in [resum-projects / reconcile-agentic-ai](https://vercel.com/resum-projects/reconcile-agentic-ai). The React dashboard and FastAPI API share one domain through Vercel Services; Neon stores durable PostgreSQL records. Schema migrations run at build time. Vercel investigations complete inside the serverless invocation with durable task statuses and bounded retries; ordinary installations continue to use the standalone worker. Execution stays recommendation-only. Local records and credentials are excluded from uploads by `.vercelignore`.

Redeploy the linked project with `vercel deploy --prod --scope resum-projects`. Hosting secrets live in Vercel environment settings; preserve the existing file encryption key to retain access to encrypted files. The hosted login page uses `ACCOUNT_LOGIN_MODE=true` and `HOSTED_DEMO_MODE=false`. Anonymous demo access is disabled. Existing demo records are preserved separately and are not assigned to new accounts. Account sessions last seven days and sign-out revokes the session immediately. Password reset and email recovery are not implemented.

## Local setup

Requires Python 3.11+, Node 22+ and pnpm. In the repository root:

```powershell
python -m pip install -r backend/requirements.txt
cd frontend
pnpm install
cd ..
.\scripts\Start-Local.ps1
```

The launcher migrates SQLite, initializes separate local identities and starts the API, durable worker and React preview in hidden processes. Open [the workspace](http://127.0.0.1:5173). The local launcher now opens the dashboard without an access token. Use the **Local demo identity** selector to switch between analyst, checker/second-checker and administrator. This convenience is restricted to loopback requests and the explicitly configured local organization. Use `Start-Local.ps1 -TokenAuth` to retain the token sign-in screen. Manual server startup and Docker continue to require authentication by default; their credentials remain in the private, Git-ignored `backend/.local/credentials.json` and expire after eight hours.

For explicit internal financial simulation: `.\scripts\Start-Local.ps1 -Simulation`. Stop owned services with `.\scripts\Stop-Local.ps1`. No external accounting system is modified.

If using the bundled Codex Node runtime without a global pnpm command:

```powershell
node "$env:USERPROFILE\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules\pnpm\bin\pnpm.cjs" install
```

Run that from frontend. For a normal development environment use your installed pnpm directly.

Manual startup, in separate terminals:

```powershell
cd backend
python -m alembic upgrade head
python -m app.bootstrap
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

```powershell
cd backend
python -m app.worker
```

```powershell
cd frontend
pnpm dev
```

Environment variables are read from the process. Local Python does not automatically load `.env`; set variables in your shell. Compose reads `.env`.

## Try the application

1. Overview → Run synthetic demo → matching workspace → exception investigation.
2. Accounting workflows → run AP, AR, gateway, intercompany or GL demos, or select real imported datasets and supporting POs/account mappings.
3. Agent observatory → queue investigation and inspect all ten actual node outputs/checkpoints.
4. Approval center → sign in as a distinct checker, inspect validation/evidence, approve; simulate/reverse only when explicitly enabled.
5. Import records → preview CSV/XLSX/JSON, save column mappings, import with per-row errors; rejected records remain visible.
6. Accounting controls → configure tenant accounts and posting/approval policy as administrator. Changed policy invalidates earlier proposals.
7. Financial reports → CSV/JSON/PDF. Separate accounting statements and original source totals preserve the distinction between evidence and adjustments.
8. Exception case controls → assign investigators; authorized closure requires a new completed reconciliation, full accepted match and unchanged original source/target anchor.

## Test and evaluate

```powershell
cd backend
python -m pytest -q
```

```powershell
cd frontend
pnpm build
pnpm test
pnpm exec playwright install chromium
pnpm exec playwright test --workers=1
```

Browser tests require initialized identities, the backend in simulation mode and the worker running. They create synthetic records in the configured local database.

From the repository root:

```powershell
python scripts/generate_data.py
python evaluation/run.py
python evaluation/study.py --count 50
```

The six-arm study defaults to mock mode. `--provider openai` requires credentials and incurs paid calls. Ground truth stays separate from inputs. Model training/ranking endpoints consume audited human reviews and preserve held-out run/record separation; they never accept matches automatically.

## Docker and CI

Copy `.env.example` to `.env`, set a strong URL-safe POSTGRES_PASSWORD, and use a running Linux-capable Docker engine:

```powershell
docker-compose config --quiet
docker-compose up --build -d
docker-compose exec backend python -m app.bootstrap
```

Read private credentials inside the backend container, then open [localhost:8080](http://127.0.0.1:8080). Compose includes PostgreSQL, backend, frontend, durable worker and optional Redis. The standalone docker-compose command is available on the current host; its Docker engine/WSL are unavailable, so successful container execution is not claimed. GitHub Actions includes backend/frontend checks, browser flows and a dedicated PostgreSQL synthetic-control integration job; remote CI execution is not claimed before it runs.

## Documentation

- [Architecture and schema](docs/architecture.md)
- [Specialized accounting contracts](docs/specialized_workflows.md)
- [Matching and normalization](docs/reconciliation_engine.md)
- [Ten-agent design](docs/agent_design.md)
- [Financial controls and security](docs/financial_controls.md)
- [API reference](docs/api_documentation.md) and [interactive OpenAPI](http://127.0.0.1:8000/docs)
- [Evaluation methodology](docs/evaluation_methodology.md)
- [Deployment and troubleshooting](docs/deployment.md)
