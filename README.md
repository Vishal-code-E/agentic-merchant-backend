# Razorpay Agentic Merchant Backend

An agentic backend that makes a Razorpay merchant **AI-sellable**: an agent
can discover its catalog, get relevant upsell suggestions, complete a
checkout — including via a plain chat message — and trigger a background
growth workflow, all against a real Postgres database and Razorpay
**test-mode** APIs. Every money-moving decision is explainable, bounded,
gated, and logged.

Full product/design docs live in [`/docs`](./docs):

- [`01-product-understanding.md`](./docs/01-product-understanding.md) — context, problem, solution, personas
- [`02-prd-agentic-merchant-backend.md`](./docs/02-prd-agentic-merchant-backend.md) — scope, requirements, delivery status
- [`03-dev-handoff-architecture-lld.md`](./docs/03-dev-handoff-architecture-lld.md) — original tech stack / LLD planning doc
- [`04-graph-engineering.md`](./docs/04-graph-engineering.md) — LangGraph design principles, node layouts
- [`ARCHITECTURE.md`](./docs/ARCHITECTURE.md) — **as-built** design: graph flow, why policy sits where it does, auth/idempotency, tracing
- [`DEMO.md`](./docs/DEMO.md) — the 5-minute, copy-paste, script-driven demo

## The problem this solves

A Razorpay merchant's catalog and checkout are built for a human clicking
through a web page. An AI shopping agent can't reliably browse or buy from
that — it would need to scrape HTML, guess at prices, and improvise its way
around whatever spending limits the merchant actually wants enforced. And
even where an agent *can* transact, the merchant has no record of what the
agent decided, why, or whether it stayed inside the rules.

This backend gives a merchant a machine-readable front door instead: a
catalog an agent can query directly, a checkout that only clears once it's
checked against the merchant's own spending ceiling and category rules, and
an audit trail that ties every decision — matched or denied — back to a
traceable run. Money only moves after policy says so, and every step of how
that decision was reached is written down.

## The 4 agentic directions, and what implements each

| Direction | Implementation |
|---|---|
| **Catalog discovery** | `GET /agent/catalog` ([`router_catalog.py`](./apps/backend/app/api/router_catalog.py)) — flat, agent-readable product list. `GET /.well-known/agent-manifest.json` ([`router_manifest.py`](./apps/backend/app/api/router_manifest.py)) publishes the whole contract (auth, idempotency, endpoints) so an agent can self-onboard. |
| **Upsell / cross-sell** | `suggest_upsell_node` + `PolicyEngine.filter_upsells` inside `checkout_graph` ([`checkout_graph.py`](./apps/backend/app/agents/checkout_graph.py)) — cheapest-first heuristic cross-sell, filtered against policy before it's ever offered. |
| **Conversational checkout** | `POST /agent/chat-checkout` ([`router_checkout.py`](./apps/backend/app/api/router_checkout.py)) + [`intent_parser.py`](./apps/backend/app/services/intent_parser.py) — an LLM turns a free-text message into a structured cart (product ids are schema-constrained to the merchant's real catalog, so it can't hallucinate one), then runs it through the exact same `checkout_graph` as a structured request. |
| **Campaign orchestrator** | `campaign_graph` ([`campaign_graph.py`](./apps/backend/app/agents/campaign_graph.py)) + `POST /internal/campaigns/run` ([`router_campaigns.py`](./apps/backend/app/api/router_campaigns.py)) — segments recent orders (failed / high-value), recommends actions, re-checks each against the merchant's *current* policy before logging it. |

See [`docs/ARCHITECTURE.md`](./docs/ARCHITECTURE.md) for how these fit together, and [`docs/DEMO.md`](./docs/DEMO.md) to see all four run in one sequence.

## Architecture overview

```text
 AI agent / chat client
        │  X-Agent-Api-Key, Idempotency-Key
        ▼
 FastAPI  ── /agent/catalog, /agent/checkout, /agent/chat-checkout,
             /merchant/*, /internal/campaigns/run, /observability/*
        │
        ├─▶ checkout_graph (LangGraph)  ── Input → ValidateCart → SuggestUpsell
        │                                   → CheckPolicy → CreateOrder → Finalize
        ├─▶ campaign_graph (LangGraph)  ── LoadOrders → SegmentCustomers
        │                                   → RecommendActions → ApplyPolicy → EmitAudit
        ├─▶ intent_parser.py  ── LLM (Anthropic), JSON-schema-constrained output
        │                        → feeds a CheckoutRequest into checkout_graph
        ├─▶ PolicyEngine  ── the one gate every money-moving path passes through
        ├─▶ RazorpayClient  ── the only thing allowed to call Razorpay (test-mode)
        └─▶ Langfuse + AuditService  ── every run traced, every decision logged
                     │
                     ▼
              Postgres (Neon) — merchants, products, orders, policies,
                                 agent_runs, audit_logs

 Next.js dashboard  ── onboarding / catalog / policies / observability
                        (talks to the same FastAPI surface, dashboard-facing routes)
```

- **FastAPI** — HTTP surface, request validation, OpenAPI docs.
- **LangGraph** — deterministic control flow for checkout and campaigns; the graph decides *whether* money moves, an LLM is only ever used for suggestion/interpretation (upsell heuristics, chat-checkout parsing), never for the policy decision itself.
- **Postgres (Neon)** — the system of record: merchants, products, orders, policies, agent runs, audit logs.
- **Langfuse** — a trace per `/agent/checkout`, `/agent/chat-checkout`, and `/internal/campaigns/run` call, with each graph node as a span.
- **Next.js** — merchant-facing dashboard for onboarding, catalog, policy, and observability.

## Repo layout (Nx workspace)

This is an **Nx monorepo**: one root `package.json`/`nx.json` orchestrates both
the Python backend and the TS frontend as Nx *projects*, each with its own
`project.json` declaring `serve`/`build`/`test`/`lint` targets. Nx's Python
support is via `nx:run-commands` wrapping pip/uvicorn/pytest — it doesn't need
the backend to be Node-based to get task caching and `nx affected` for free.

```text
/agentic-merchant-backend
  nx.json                 workspace config: target defaults, caching, plugins
  package.json             root deps: nx, @nx/next, @nx/js, @nx/eslint
  tsconfig.base.json        shared TS config + path alias for libs
  /apps
    /backend               FastAPI + LangGraph app (Nx project: "backend")
      project.json           targets: install, serve, build, test, lint, migrate
      app/main.py             entrypoint, router registration, /ping
      app/api/                router_catalog, router_checkout, router_onboarding,
                               router_policy, router_campaigns, router_observability,
                               router_manifest (agent discovery)
      app/models/             SQLAlchemy models: merchant, product, order, policy, agent_run, audit_log
      app/services/           razorpay_client, policy_engine, audit_service, agent_auth,
                               intent_parser (chat-checkout's LLM call)
      app/agents/             checkout_graph, campaign_graph, state (LangGraph)
      app/config/             settings.py (pydantic-settings)
      app/workers/            tasks.py (Celery — stub, see Known Gaps)
      scripts/                ai_buyer_demo.py, setup_demo_merchant.py — see docs/DEMO.md
    /frontend               Next.js dashboard (Nx project: "frontend")
      project.json            targets: dev, build, start, lint (via @nx/next)
      src/lib/                 api.ts (fetch helper), merchant-context.tsx (active merchant_id)
      src/app/                /onboarding /catalog /policies /observability
  /libs
    /shared-types           TS types shared by frontend <-> backend contracts
      src/index.ts             Merchant, Product, Order, Policy, CheckoutRequest/Response, ChatCheckoutRequest/Response, etc.
  /docs                    product + engineering docs (see above)
  /infra                   Dockerfiles + docker-compose
  .github/workflows/       CI (Nx affected + backend pytest)
  .env.example
```

**Why a shared-types lib:** `apps/frontend` imports from
`@agentic-merchant/shared-types` (see e.g. `apps/frontend/src/app/catalog/page.tsx`)
instead of redefining API shapes locally. Keep it in sync with the SQLAlchemy
models by hand for now; a later task can generate it from FastAPI's OpenAPI
schema.

## Local setup

### 1. Set up Neon (Postgres)

Postgres is [Neon](https://neon.tech) (cloud-managed), not a local/Docker container:

1. Create a Neon project at [neon.tech](https://neon.tech) (or `neon.new` for
   a throwaway, no-signup project you can claim later).
2. Copy its connection string from the project dashboard → **Connection Details**.
3. Convert it into `.env`'s `DATABASE_URL`: use the `postgresql+asyncpg://`
   scheme (not the raw `psql` string) and drop any `channel_binding` query
   param — asyncpg doesn't support it. `sslmode=require` is fine;
   `app/db/session.py` converts it to the `ssl=` param asyncpg expects.

Neon's branching model is also useful here: cut a branch per feature/PR to
test schema migrations against a copy of real data without touching the
primary branch, then delete it once merged.

### 2. Set up Langfuse

Traces (checkout, chat-checkout, and campaign runs) and audit logs are sent to [Langfuse](https://langfuse.com):

1. Create a Langfuse project (cloud.langfuse.com, or self-hosted).
2. From the project's **Settings → API Keys**, copy the public and secret
   keys into `.env`'s `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY`.
3. Leave `LANGFUSE_BASE_URL` as `https://cloud.langfuse.com` unless self-hosting.

`app/observability/langfuse_client.py` builds a single process-wide `Langfuse`
client from these settings; `app/main.py`'s startup `lifespan` calls
`auth_check()` and logs a warning (not a hard failure) if the keys are
missing or invalid — the app still starts, but traces silently won't arrive.
Every `/agent/checkout`, `/agent/chat-checkout`, and `/internal/campaigns/run`
call gets an `AgentRun` row whose `langfuse_trace_id` links straight to the
trace (see the Observability dashboard page, and `/observability/*` below).

### 3. Get Razorpay test-mode keys

1. Sign up at [dashboard.razorpay.com](https://dashboard.razorpay.com) and switch to **Test Mode**.
2. **Settings → API Keys → Generate Test Key** gives you a key id + secret.
3. These go into a merchant's `razorpay_key_id`/`razorpay_key_secret` at
   onboarding time (`POST /merchant/onboarding/keys`) — not into `.env`
   directly, since keys are per-merchant, not global. `.env`'s
   `RAZORPAY_KEY_ID`/`RAZORPAY_KEY_SECRET` are only a local-dev convenience
   the onboarding dashboard page pre-fills from (see `NEXT_PUBLIC_TEST_RAZORPAY_KEY_ID`
   in `apps/frontend/.env.local`).

### 4. Get an Anthropic API key (for conversational checkout)

`POST /agent/chat-checkout` calls an LLM to turn a free-text message into a
structured cart (see [`intent_parser.py`](./apps/backend/app/services/intent_parser.py)).
Get a key at [console.anthropic.com](https://console.anthropic.com) and put
it in `.env`'s `ANTHROPIC_API_KEY`. Every other endpoint works without it —
only chat-checkout needs it.

### 5. Environment

```bash
cp .env.example .env
# fill in: DATABASE_URL, LANGFUSE_PUBLIC_KEY/SECRET_KEY, ANTHROPIC_API_KEY,
# RAZORPAY_KEY_ID/SECRET (local-dev convenience only — see step 3), ENCRYPTION_KEY
```

`ENCRYPTION_KEY` encrypts merchant Razorpay secrets at rest — generate one with:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### 6. Apply migrations

```bash
cd apps/backend
alembic upgrade head
```

### 7. Install the Nx workspace (frontend + shared-types)

```bash
npm install
```

### 8. Run everything via Docker

```bash
docker compose -f infra/docker-compose.yml up --build
```

This only starts `backend`, `frontend`, and `redis` — Postgres lives on Neon, outside Docker entirely.

- Backend: http://localhost:8000/ping (liveness — no DB call) and http://localhost:8000/health/db (`SELECT 1` against Postgres)
- Backend docs: http://localhost:8000/docs
- Frontend: http://localhost:3000

### 9. Or run projects individually via Nx

```bash
# backend (Python, wrapped as an Nx target)
nx run backend:install   # pip install -r apps/backend/requirements.txt
nx serve backend         # uvicorn app.main:app --reload

# frontend (native @nx/next executor)
nx dev frontend

# both, in parallel, respecting the dependency graph
nx run-many -t build

# only what changed since main
nx affected -t lint test build
```

Visualize the project graph (backend, frontend, shared-types + their edges):

```bash
nx graph
```

## See it work in 5 minutes

[`docs/DEMO.md`](./docs/DEMO.md) is a copy-paste, script-driven sequence —
onboard a merchant, seed a catalog, hit the discovery manifest, run the
AI-buyer script (catalog discovery, checkout, policy denial, conversational
checkout), inspect the audit trail, and trigger the campaign orchestrator.
No placeholders to fill in by hand.

## API overview

Everything below is served under `settings.api_v1_prefix` (default `/api/v1`),
except the discovery manifest and health checks. The full, always-current
list of routes, request/response schemas, and models is auto-generated by
FastAPI at **http://localhost:8000/docs** (Swagger UI) and
**http://localhost:8000/openapi.json** — that's the source of truth; this
section just orients you.

- `GET /ping` — liveness check, no DB call. `GET /health/db` — runs `SELECT 1` against Postgres.
- `GET /.well-known/agent-manifest.json` — unauthenticated discovery document:
  every `/agent/*` endpoint, its schema, and the auth/idempotency contract.
  An agent can learn everything it needs before it even has an API key.
- `POST /merchant/onboarding/keys` — onboard a merchant. A merchant cannot
  exist without a policy: the request body includes `max_amount` (required),
  `allowed_categories`, and `per_user_limit` alongside the Razorpay keys, and
  the `Merchant` + `Policy` rows are created atomically. Returns a one-time
  agent API key.
- `POST /merchant/{merchant_id}/api-key/regenerate` — issue a new agent API
  key, invalidating the previous one immediately.
- `GET /merchant/{merchant_id}` — fetch a merchant.
- `GET/POST/PATCH/DELETE /merchant/products` — catalog CRUD (dashboard-facing).
- `GET /agent/catalog` — flat, agent-readable catalog (external AI buyers). Requires `X-Agent-Api-Key`.
- `POST /agent/checkout` — policy-gated checkout for a structured cart.
  Requires `X-Agent-Api-Key` and `Idempotency-Key`.
- `POST /agent/chat-checkout` — the same checkout, but starting from a
  free-text message instead of a structured cart (see intent_parser.py).
  Requires `X-Agent-Api-Key`; `Idempotency-Key` is optional (one is generated
  per call if omitted — see the manifest's `idempotency_note`).
- `GET/PATCH /merchant/{merchant_id}/policy` — read/update a merchant's guardrails.
- `POST /internal/campaigns/run` — manually trigger `campaign_graph` for a
  merchant (no scheduler yet; Celery Beat is a known gap — see below).
- `GET /observability/agent-runs` — list `AgentRun` rows (checkout, chat-checkout,
  or campaign executions), most recent first; optional `?merchant_id=` filter.
  Each row carries `langfuse_trace_id`, so it links directly to its trace.
- `GET /observability/agent-runs/{agent_run_id}/audit-logs` — the structured
  audit trail (`policy_check`, `checkout_denied`, `intent_parsed`, etc.) for
  one run, oldest first. Powers the expandable rows on `/observability`.

## What's implemented

- **Agent-readable catalog** — `GET /agent/catalog`, discovery manifest, category/price filters.
- **Policy-gated checkout** — `checkout_graph` (Input → ValidateCart →
  SuggestUpsell → CheckPolicy → CreateOrder → Finalize), fail-closed on any
  missing/misconfigured policy, real Razorpay test-mode order creation.
- **Upsell / cross-sell** — heuristic, cheapest-first, filtered by policy before it's ever surfaced.
- **Conversational checkout** — LLM-parsed natural language → structured
  cart, schema-constrained to the merchant's real product ids, reusing
  `checkout_graph` unmodified.
- **Campaign orchestrator** — `campaign_graph` segments recent orders
  (failed / high-value), recommends actions, re-validates each against the
  *current* policy before logging.
- **Idempotency** — `Idempotency-Key`-based replay safety on checkout, with
  cart-mismatch detection (409) and an atomic INSERT..ON CONFLICT to close
  the concurrent-request race.
- **Auth** — per-merchant agent API keys (sha256-hashed, never stored
  plaintext, one-time display, regenerable).
- **Observability** — Langfuse trace per agent run, `AgentRun` + `AuditLog`
  rows for every checkout/chat-checkout/campaign call, a dashboard page to browse both.
- **Dashboard** — onboarding, catalog, policy, and observability pages, with
  a persisted active-merchant switcher.

## Known gaps (deliberately deferred)

Being upfront about these is the point — each one was a scope call, not an oversight:

- **No campaign scheduler.** `POST /internal/campaigns/run` is a manual
  trigger; `app/workers/tasks.py` is an unfilled Celery stub. Celery Beat (or
  an equivalent cron) is the natural fast-follow.
- **No persistent per-customer spend ledger.** `PolicyEngine.evaluate()`
  checks `per_user_limit` against the *current* cart only — `Order` has no
  `customer_id` column and nothing aggregates historical spend, so a customer
  could stay under the limit on every individual checkout while exceeding it
  in aggregate. Closing this needs a `customer_id` column plus a
  rolling-window spend query (see the `KNOWN GAP` comment in `policy_engine.py`).
- **No automated test suite yet.** CI runs `pytest` but there are currently
  no test files (`ci.yml` keeps this non-blocking with `|| true` until that
  changes). Verification today is script-driven — see `docs/DEMO.md`.
- **No webhook handling.** `RazorpayClient.verify_webhook_signature()`
  exists but nothing calls it — checkout is synchronous request/response
  only; an async payment-status change from Razorpay (e.g. a delayed
  failure) isn't picked up.
- **No graph checkpointing across turns.** `checkout_graph` and
  `campaign_graph` run to completion synchronously within one HTTP request;
  there's no LangGraph checkpointer, so a mid-run client disconnect doesn't
  resume from a saved state (it just fails the request — no partial side effects).
- **Two of three LLM providers wired up.** `settings.model_provider` is
  config-driven; `intent_parser.py` implements `anthropic` (Messages API) and
  `openai` (Chat Completions) — both use the same JSON-schema-constrained
  structured output. `gemini` raises `IntentParserUnavailable` (a clean 503)
  rather than silently miscalling an unconfigured provider.
- **Test-mode only.** No live-mode settlements/reconciliation — by design (see the PRD's out-of-scope section).
- **No AP2/UCP/UAP conformance.** The discovery manifest is loosely inspired
  by that shape (self-describing, agent-parseable) but isn't a protocol implementation.

## Non-negotiable design rule

**Policy before payment.** Every money-moving graph node must pass through
`check_policy_node` / `PolicyEngine.evaluate()` before any Razorpay call. No
graph node calls Razorpay directly — always through `razorpay_client.py`. See
[`docs/ARCHITECTURE.md`](./docs/ARCHITECTURE.md) for why the checkout graph
places this exact gate where it does.
