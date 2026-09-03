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

**This is the project skeleton only.** Routers, models, and graph nodes are
stubbed with `TODO(vX.X)` markers and `raise NotImplementedError` — nothing
here is wired to a real database, Razorpay, or an LLM yet. The one endpoint
that actually works is `GET /ping`.

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
    /frontend               Next.js dashboard (Nx project: "frontend")
      project.json            targets: dev, build, start, lint (via @nx/next)
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
`@agentic-merchant/shared-types` (see `apps/frontend/src/app/page.tsx`) instead
of redefining API shapes locally. Keep it in sync with the SQLAlchemy models
by hand for now; a later task can generate it from FastAPI's OpenAPI schema.

## Local setup

### 1. Environment

```bash
cp .env.example .env
# fill in Razorpay TEST-mode keys, DB URL, Langfuse keys, model provider key
```

Postgres is [Neon](https://neon.tech) (cloud-managed), not a local/Docker
container:

1. Create a Neon project and copy its connection string from the project
   dashboard → **Connection Details**.
2. Convert it into `.env`'s `DATABASE_URL`: use the `postgresql+asyncpg://`
   scheme (not the raw `psql` string) and drop any `channel_binding` query
   param — asyncpg doesn't support it.
3. Create the schema by running Alembic locally (not inside Docker):
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

## Non-negotiable design rule

**Policy before payment.** Every money-moving graph node must pass through
`check_policy_node` / `PolicyEngine.evaluate()` before any Razorpay call. No
graph node calls Razorpay directly — always through `razorpay_client.py`.
