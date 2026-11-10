# Implementation status

Last verified: 10 November 2026. The local application phases are substantially implemented and tested; a working Vercel deployment now uses a live Neon PostgreSQL database. **The entire master specification is not claimed complete:** container-engine verification, paid-provider validation, organization-specific integration/posting policies and representative research trials remain environment/data dependent.

## Phase ledger

| Phase | Implemented behavior | Verification |
| --- | --- | --- |
| 1 Repository | Initialized the originally empty Git repository with backend, frontend, tests, research, scripts and docs | Import/startup/build checks |
| 2 Foundation/database | FastAPI, SQLAlchemy, 25 relational tables, nine Alembic revisions, tenant scopes, expiring identities and roles | Fresh/existing SQLite migrations; PostgreSQL DDL compilation; API isolation tests |
| 3 Ingestion | CSV/XLSX/JSON/manual inputs, preview, reusable mappings, per-row partial errors, source binary SHA-256 retention, optional AES-GCM, ISO currencies/configurable precision, value/posting dates/timezones, per-field canonical transformations | Import/precision/timezone/encryption/connector tests; browser preview/import |
| 4 Reconciliation | Decimal arithmetic, exact currency/account/sign/date constraints and per-currency totals | Exact/tolerance/date/large-value tests |
| 5 Matching/exceptions | Fuzzy, split/aggregation, conflicts, cross-ID duplicate review, unusual-value flags, normalized unique membership, audited accept/reject and constrained manual matches | Coverage, duplicate, no-double-consumption, review-count tests |
| 6 Financial validation | Independently normalized source integrity; journal balance/direction/precision, evidence, tenant accounts, policy version and closed-period checks | Balanced/unbalanced/unsupported/stale/period/account/source tests |
| 7 Agent orchestration | Ten distinct specialist implementations running as ten actual LangGraph nodes | All-ten-node and persisted-output tests; live browser observatory |
| 8 Investigation | Scoped evidence retrieval, bank code dictionaries, ledger/candidate analysis, typed taxonomy, alternatives and uncertainty; optional OpenAI root-cause adapter | Agent/evidence-scope tests; no fabricated cause on insufficient evidence |
| 9 Recommendation | Typed target/current/proposed fields, risk, impact, date and approval; bank-charge journal drafts or category-specific manual recommendations | Provider/schema/financial-control tests |
| 10 Independent critic | Separate deterministic accounting/evidence checks and simulated attributable discrepancy recalculation | Critic rejection and source-integrity tests |
| 11 Self-correction | Targeted feedback loop, maximum three proposals, deadline checks, provider timeouts, node checkpoints and partial resume | Fault-repair, bounded failure, crash/resume and evidence-scope tests |
| 12 Approval/execution | Maker-checker, distinct dual approvals, idempotent append-only simulations/reversals, period rechecks, investigator assignment and evidence-anchored human resolution | End-to-end API and browser approval/simulation/reversal; anchored closure tests |
| 13 ML | TF-IDF pair similarity, Logistic/Random Forest ranking, held-out reviewed-run separation, model versions, Brier/reliability assessment and human feedback ingestion | Offline and API ranking tests; no automatic financial acceptance |
| 14 Audit/explanation | Immutable sources/canonical/files/decisions/agent/checkpoint/reflection/adjustment/audit records; source evidence, uncertainty, validation and decision histories | ORM/database-trigger tests and browser review |
| 15 UI | Overview; import/preview/templates; workspace and comparison/review; cases/investigation/self-correction; approvals; CSV/JSON/PDF reports; audit; specialized workflows; agent observatory; account/policy controls | TypeScript, three unit assertions, five browser workflows, responsive check and screenshots |
| 16 Testing | Unit, accounting, integration, schema, migration, security, worker, recovery, ML and full browser tests | 64 backend tests; 3 frontend tests; 5 browser tests passed |
| 17 Evaluation | Six ablation arms, separate ground truth, fixed seeds, matching/classification/validation/escalation/latency/attempt/token metrics; unavailable human/real-cost outcomes remain explicit | Six-arm mock study and evaluator assertions; no LLM superiority claim |
| 18 Delivery | Backend/frontend/worker Docker configuration, PostgreSQL/optional Redis, CI checks and PostgreSQL integration script, launch/stop scripts and rewritten documentation | Local API/frontend/worker run; frontend production build; Compose configuration parses; Linux engine unavailable |

## Concrete verification evidence

- `cd backend; python -m alembic upgrade head`: revisions 0001–0009 applied. Fresh SQLite migration test checks immutable audit protection. Migration 0007 backfills existing match membership without silently accepting conflicts.
- Final isolated `python -m pytest -q --tb=short --basetemp=.pytest-final`: **64 passed**, with two dependency deprecation warnings. Python compilation checks pass.
- `tsc -b`: passed. Vitest: **3 tests passed**. Production Vite build: passed; split bundles approximately 51/101/274/406 kB, eliminating the initial oversized single application bundle.
- Chromium: **5 browser tests passed** (AP three-way and human review/PDF export; fee proposal/checker approval/simulation/reversal; CSV preview/templates/partial import; durable queued ten-agent investigation; standard demo/investigation/mobile overflow).
- Queue/browser testing exposed and fixed missing automatic agent-output refresh. Checkpoint testing exposed and fixed replay of completed nodes. Worker tests cover exhausted abandoned leases. Match review tests cover released/restored counts and rejection of double consumption.
- PDF sample generated from actual synthetic AP results, rendered with Poppler, and visually inspected. Final artifact: `output/pdf/synthetic-ap-reconciliation.pdf`; supporting render in `docs/screenshots/pdf-report.png`.
- `python evaluation/study.py --count 50`: three fixed seeds, six arms. Exact baseline mean precision 1.0 / recall 0.9778; fuzzy and subsequent arms mean precision/recall 1.0 on that limited corpus. These are synthetic matching metrics, not evidence of LLM reasoning or self-correction superiority.
- OpenAI schemas and read-only function calls tested offline against a mocked SDK client. Out-of-scope evidence requests are rejected. No paid calls were made.
- `docker-compose config --quiet` passed with a temporary configuration-only password. Docker/Compose executables exist, but the Docker engine is unavailable and WSL is not installed. No container start/build or live PostgreSQL success is claimed.
- CI now defines backend/frontend tests, browser checks and a dedicated PostgreSQL synthetic integration. Remote CI has not been run in this session.

## What remains before claiming the entire specification complete

1. Supply a working Linux-capable Docker engine or PostgreSQL test environment. Run Compose builds/health checks and `scripts/verify_postgres.py`; validate concurrent PostgreSQL financial mutations in the intended deployment. Schema compilation and a planned CI job are not runtime proof.
2. If real LLM operation is intended, configure an API key/model and validate live structured diagnosis/tool/recommendation behavior, refusal/timeouts and actual token/cost traces. The deterministic mock workflow is already functional without paid access.
3. Run the six-arm study on representative independently labeled financial datasets and, where relevant, actual providers. Measure organization-specific human acceptance, operating cost, real resolution time and efficiency before any research improvement claim.
4. Configure real source integrations, account mappings, approval/period rules, currency conventions and deployment identity/storage/TLS/backup/retention controls. The included connectors read operator-selected HTTP JSON or read-only database export views; arbitrary ERP write/posting adapters are not enabled. Financial execution remains recommendation-only by default and internal simulation when explicitly enabled.
5. Narrow limitations: subset matching intentionally bounds candidate/group sizes; not every financial exception has an executable correction (unsupported amounts/currencies/mappings remain human review). Account/PO matching is based on canonical financial document amounts, not a full ERP inventory/tax/line-item purchasing system. List handling is bounded and requires deployment-scale performance/accessibility/security validation.

These outstanding checks are stated explicitly rather than presenting synthetic tests as production or research certification.

## Continue precisely

1. Read README and the specialized workflow, agent and financial-control docs.
2. Set up the missing Docker/Linux or dedicated PostgreSQL environment; do not install OS features or change real financial systems implicitly.
3. Run `docker-compose config --quiet`, `docker-compose up --build -d`, initialize identities and verify health. On a dedicated PostgreSQL database set RUN_FINANCIAL_SIMULATION_TESTS=1 and execute `python scripts/verify_postgres.py`.
4. Re-run backend, frontend and browser tests as documented. Run six-arm mock evaluation as a reproducibility check; only run a paid study when a provider is configured intentionally.
5. Record actual deployment/provider/research results here. Preserve immutable source records, distinct maker/checker approval, unique match membership, bounded recovery and append-only adjustments.

Final teardown: owned local frontend/API/worker preview processes stopped after verification. Source changes are left in the workspace; no commit, remote CI run or production deployment was performed.

## 10 November 2026: token-free local dashboard

User requested access without entering a token. Added explicitly enabled loopback-only local demo access scoped to one configured organization, automatic dashboard entry and a demo identity selector. Deployment authentication remains the default. Launcher now prefers the built dashboard preview to avoid the observed development-server timeout, with -Development and -TokenAuth options. Backend verification: 67 tests passed, including remote/origin/tenant boundary checks; TypeScript and production build passed. Chromium local-access test passed: dashboard opens without credentials, identity switching enables the selected role, and the selector remains usable on mobile. Services remain running for the requested dashboard access.

## 10 November 2026: Vercel deployment completed

- Live dashboard: https://reconcile-agentic-ai.vercel.app ; project: https://vercel.com/resum-projects/reconcile-agentic-ai . Final deployment `dpl_D9pvyHQRTFZdBVejtQ75Q9h6oMaX` reached READY and the production alias was assigned.
- Vercel Services hosts Vite and FastAPI behind one domain. A separate Neon Free database (`reconcile-agentic-ai-db`) was created and connected; all Alembic migrations applied successfully to actual PostgreSQL. PostgreSQL URLs are normalized for psycopg3 and pooled connections disable prepared statements.
- Explicit hosted demo mode opens without bearer-token entry. Each browser gets a separate organization with a signed, expiring Secure/HttpOnly/SameSite cookie. Identity selection is confined to that organization. Normal deployments retain token authentication unless hosted demo mode is explicitly enabled. This is a synthetic demonstration, not a production financial identity system.
- Mock provider and recommendation-only execution remain enabled. Hosted task submissions use the existing leased worker implementation inside the serverless invocation, scoped to the submitted task ID with bounded retries. Normal installations retain the independent worker. No paid always-on daemon was provisioned.
- Vercel environment secrets configure cookie signing and AES-GCM retained-file encryption. Decoder accepts standard and URL-safe base64 without changing key bytes. Existing keys were preserved. Local SQLite records, credentials, env files, caches and test data were excluded from deployment.
- Verification: TypeScript and Vite production build passed locally and on Vercel. Full backend suite: **69 passed**; subsequent hosted task/isolation and encryption compatibility checks: **5 passed**, including the added URL-safe-key test. Two upstream dependency deprecation warnings remain.
- Final unauthenticated public HTTP checks: dashboard, `/agents`, `/workflows`, health all 200; cookie session/me successful; independent browsers receive different organizations; cross-tenant access returns 404; synthetic bank run completed (64 records, 53 matched, 7 exceptions); durable investigation completed; all ten distinct agent outputs persisted; PDF export valid; encrypted CSV upload and original-file download round trip exact; AP, AR, gateway, intercompany and GL demos all completed against live PostgreSQL.
- Browser verified token-free dashboard entry and successful synthetic reconciliation. Proof: `output/vercel-dashboard.png`. The dashboard tab is retained as a deliverable. Local source remains uncommitted; no Git remote was configured.

Remaining research/integration limitations above still apply; hosting does not establish paid-provider performance, real ERP posting readiness or research superiority.

## 10 November 2026: username/password login and signup

- Replaced anonymous hosted entry with **Sign in** and **Create account** at the existing production URL. Username and password only; usernames allow spaces and are case-insensitive. Passwords require at least six characters, with no composition rules or confirmation field.
- Added `login_accounts` and Alembic revision `0010`; Vercel build applied the migration to Neon. New accounts own separate organizations. Passwords use per-account random salts and scrypt hashes. Sessions use random secrets stored only as hashes server-side, Secure/HttpOnly/SameSite cookies, seven-day expiry and immediate logout revocation. Origin checks protect authentication writes.
- `ACCOUNT_LOGIN_MODE=true` and `HOSTED_DEMO_MODE=false` on Vercel. Account mode rejects anonymous demo fallback, even if an old demo cookie remains. Existing demo data stays separate. Local demo access remains explicitly configured by the local launcher. Serverless task completion continues to work for signed-in accounts.
- Production deployment `dpl_8NmseLmDQW1oKvcCWiMdPBCYypYS` reached READY. Live HTTP verified signup, cookie properties, persisted identity, incorrect-password rejection, case-insensitive sign-in, sign-out, synthetic reconciliation and completed investigation. Synthetic test credentials were not printed or committed.
- Full backend regression suite: **72 passed** (two upstream dependency warnings). TypeScript and Vite build passed. Browser verified both login and create-account screens; proof saved to `output/vercel-create-account.png`.
- Password reset/email recovery is not part of this implementation. Independent human approval still requires a separate authorized checker; signing up does not bypass maker-checker controls.

## 10 November 2026: clean reconciliation URLs

- Reconciliation pages now use `/reconciliation/workspace` instead of a UUID in the browser address. Overview/list/report links and bank/specialized workflow navigation pass the selected record through navigation state. Session storage preserves selection across refresh; a new session without selection returns to the list.
- Old UUID links redirect with history replacement to the clean path. Internal API ownership checks and record identifiers remain unchanged.
- Local TypeScript check and Vercel production build passed. Deployment `dpl_4femo2qMWjMAJdquETCBrjaS1Set` reached READY. Browser confirmed the user's existing link redirects to the clean address, renders the same reconciliation, and survives refresh. Proof: `output/clean-reconciliation-url.png`.
