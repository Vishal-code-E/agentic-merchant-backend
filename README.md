# Razorpay Agentic Merchant Backend

An agentic backend that makes a Razorpay merchant AI-sellable: an agent-readable
catalog, a policy-gated checkout API, a LangGraph-based revenue agent (upsell +
campaigns), and full observability (Langfuse traces + audit logs) — built on
Razorpay **test-mode** APIs.

Full product/design docs live in [`/docs`](./docs):

- [`01-product-understanding.md`](./docs/01-product-understanding.md) — context, problem, solution, personas
- [`02-prd-agentic-merchant-backend.md`](./docs/02-prd-agentic-merchant-backend.md) — scope, requirements, v1.0–v1.4
- [`03-dev-handoff-architecture-lld.md`](./docs/03-dev-handoff-architecture-lld.md) — tech stack, repo layout, data model
- [`04-graph-engineering.md`](./docs/04-graph-engineering.md) — LangGraph design principles, node layouts

## Status

**v1.4.** Catalog CRUD, policy-gated checkout, upsell suggestions, Langfuse
tracing, audit logging, `campaign_graph`, the observability API, and the
dashboard (onboarding/catalog/policies/observability pages) are all wired up
against a real Postgres (Neon) database and Razorpay test-mode. See the build
roadmap below for what shipped in each version.

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
      app/api/                router_catalog, router_checkout, router_onboarding, router_observability
      app/models/             SQLAlchemy models: merchant, product, order, policy, agent_run, audit_log
      app/services/           razorpay_client, policy_engine, audit_service
      app/agents/             checkout_graph, campaign_graph, state (LangGraph)
      app/config/             settings.py (pydantic-settings)
      app/workers/            tasks.py (Celery)
      scripts/                ai_buyer_demo.py — standalone AI-buyer demo (see below)
    /frontend               Next.js dashboard (Nx project: "frontend")
      project.json            targets: dev, build, start, lint (via @nx/next)
      src/lib/                 api.ts (fetch helper), merchant-context.tsx (active merchant_id)
      src/app/                /onboarding /catalog /policies /observability
  /libs
    /shared-types           TS types shared by frontend <-> backend contracts
      src/index.ts             Merchant, Product, Order, Policy, CheckoutRequest/Response, etc.
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

## Setting up Neon

Postgres is [Neon](https://neon.tech) (cloud-managed), not a local/Docker
container:

1. Create a Neon project at [neon.tech](https://neon.tech) (or `neon.new` for
   a throwaway, no-signup project you can claim later).
2. Copy its connection string from the project dashboard → **Connection
   Details**.
3. Convert it into `.env`'s `DATABASE_URL`: use the `postgresql+asyncpg://`
   scheme (not the raw `psql` string) and drop any `channel_binding` query
   param — asyncpg doesn't support it. `sslmode=require` is fine;
   `app/db/session.py` converts it to the `ssl=` param asyncpg expects.
4. Apply migrations locally (not inside Docker): `cd apps/backend && alembic
   upgrade head`.

Neon's branching model is also useful here: cut a branch per feature/PR to
test schema migrations against a copy of real data without touching the
primary branch, then delete it once merged.

## Setting up Langfuse

Traces (checkout runs, campaign runs) and audit logs are sent to
[Langfuse](https://langfuse.com):

1. Create a Langfuse project (cloud.langfuse.com, or self-hosted).
2. From the project's **Settings → API Keys**, copy the public and secret
   keys into `.env`'s `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY`.
3. Leave `LANGFUSE_BASE_URL` as `https://cloud.langfuse.com` unless
   self-hosting.

`app/observability/langfuse_client.py` builds a single process-wide `Langfuse`
client from these settings; `app/main.py`'s startup `lifespan` calls
`auth_check()` and logs a warning (not a hard failure) if the keys are
missing or invalid — the app still starts, but traces silently won't arrive.
Every `/agent/checkout` and `/internal/campaigns/run` call gets an `AgentRun`
row whose `langfuse_trace_id` links straight to the trace in Langfuse (see
the Observability dashboard page, and the `/observability/*` API below).

## Local setup

### 1. Environment

```bash
cp .env.example .env
# fill in Razorpay TEST-mode keys, DB URL, Langfuse keys, model provider key
```

See **Setting up Neon** and **Setting up Langfuse** below for the two
external services `.env` needs. Once both are filled in, create the schema by
running Alembic locally (not inside Docker):

```bash
cd apps/backend
alembic upgrade head
```

### 2. Install the Nx workspace (frontend + shared-types)

```bash
npm install
```

### 3. Run everything via Docker

```bash
docker compose -f infra/docker-compose.yml up --build
```

This now only starts `backend`, `frontend`, and `redis` — Postgres lives on
Neon, outside Docker entirely.

- Backend: http://localhost:8000/ping
- Backend docs: http://localhost:8000/docs
- Frontend: http://localhost:3000

### 4. Or run projects individually via Nx

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

## Build roadmap (v1.0 – v1.4)

| Version | Day | Focus |
|---|---|---|
| v1.0 | 1 | Razorpay test-mode integration, Postgres schema, health checks |
| v1.1 | 2 | Catalog CRUD + `/agent/catalog`, minimal `checkout_graph` (Input→ValidateCart→CreateOrder→Finalize) |
| v1.2 | 3 | `SuggestUpsellNode` + `CheckPolicyNode`, policy engine, background worker |
| v1.3 | 3–4 | Langfuse tracing, audit logging, `campaign_graph`, dashboard observability views |
| v1.4 | 4 | Demo-ready dashboard UX, AI-buyer sample script, docs polish |

Each version maps to a feature branch (see `03-dev-handoff-architecture-lld.md` §5).

## API overview

Everything below is served under `settings.api_v1_prefix` (default `/api/v1`).
The full, always-current list of routes, request/response schemas, and models
is auto-generated by FastAPI at **http://localhost:8000/docs** (Swagger UI)
and **http://localhost:8000/openapi.json** — that's the source of truth; this
section just orients you.

- `POST /merchant/onboarding/keys` — onboard a merchant. As of v1.2, a
  merchant cannot exist without a policy: the request body includes
  `max_amount` (required), `allowed_categories`, and `per_user_limit`
  alongside the Razorpay keys, and both the `Merchant` and its `Policy` row
  are created atomically in one transaction.
- `GET /merchant/{merchant_id}` — fetch a merchant.
- `GET/POST/PATCH/DELETE /merchant/products` — catalog CRUD (dashboard-facing).
- `GET /agent/catalog` — flat, agent-readable catalog (external AI buyers).
- `POST /agent/checkout` — policy-gated checkout for external AI buyers.
- `GET/PATCH /merchant/{merchant_id}/policy` — read/update a merchant's guardrails.
- `POST /internal/campaigns/run` — manually trigger `campaign_graph` for a
  merchant (no scheduler yet; Celery Beat is a fast-follow).
- `GET /observability/agent-runs` — list `AgentRun` rows (checkout or
  campaign executions), most recent first; optional `?merchant_id=` filter.
  Each row carries `langfuse_trace_id`, so it links directly to its trace.
- `GET /observability/agent-runs/{agent_run_id}/audit-logs` — the structured
  audit trail (`policy_check`, `checkout_denied`, etc.) for one run, oldest
  first. Powers the expandable rows on the `/observability` dashboard page.

## Running the AI-buyer demo script

`apps/backend/scripts/ai_buyer_demo.py` plays the role of an external AI
shopping agent purely over HTTP — no imports from `app` — so it's a good
smoke test for a freshly onboarded merchant, and a live demo of both the
success and policy-denial paths:

```bash
cd apps/backend
python scripts/ai_buyer_demo.py --merchant-id <uuid> --base-url http://localhost:8000
# or: MERCHANT_ID=<uuid> BASE_URL=http://localhost:8000 python scripts/ai_buyer_demo.py
```

Get a `merchant_id` from the `/onboarding` dashboard page (or `POST
/merchant/onboarding/keys` directly). The script:

1. Discovers the catalog via `GET /agent/catalog`.
2. Reads the merchant's policy to know its `max_amount`.
3. Builds a compliant cart (cheapest product, qty 1) and checks out —
   the success path.
4. Builds a cart that deliberately exceeds `max_amount` and checks out
   again — the policy-denial path — and prints the denial reason from the
   403 response.

Requires `apps/backend/requirements.txt` to already be installed (it uses
`httpx`, already a backend dependency) and the backend running locally.

## Non-negotiable design rule

**Policy before payment.** Every money-moving graph node must pass through
`check_policy_node` / `PolicyEngine.evaluate()` before any Razorpay call. No
graph node calls Razorpay directly — always through `razorpay_client.py`.
