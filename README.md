***

# Razorpay Agentic Merchant Backend & Copilot

> A production‑grade backend and workflow layer that makes a Razorpay merchant **AI‑sellable** and **revenue‑optimised**: AI agents can discover the catalog, orchestrate checkout over Razorpay test‑mode, and run growth campaigns, with every money action explainable, bounded, gated, and auditable. [razorpay](https://razorpay.com/agentic-payments/)

***

## 1. Overview

Agentic payments are moving commerce from **click‑based checkout** to **conversation and agent‑led flows**: users express intent, AI agents decide what to buy, and payments complete inside the flow without redirecting to external apps. Razorpay and NPCI have already proven this with Agentic Payments on Claude and ChatGPT; AI can now securely complete UPI transactions end‑to‑end. [razorpay](https://razorpay.com/blog/agentic-payments-the-future-of-in-app-commerce/)

This project implements the **merchant‑side counterpart**:

- A **FastAPI + LangGraph backend** that exposes agent‑ready catalog and checkout APIs on top of Razorpay test‑mode.
- A **Next.js frontend** that gives merchants onboarding, catalog, policy, observability, and growth views.
- A **FastMCP server** that wraps these APIs as MCP tools (for Claude Desktop and other MCP hosts).
- A **legal/compliance and governance layer**: sanitisation, retention, deactivation, safety rails, and clear liability framing.

You can treat this as a **reference architecture** for an AI‑native merchant backend compatible with Razorpay’s agentic ecosystem. [razorpay](https://razorpay.com/sprint/26)

***

## 2. Problem Statement

Typical Razorpay merchants today:

- Have human‑facing catalogs (web/app) but **no agent‑readable APIs** for AI buyers to discover products safely.
- Cannot easily expose **structured checkout APIs** for agents that respect spending limits, categories, and mandates.
- Lack a unified **growth agent** that runs upsell/cross‑sell and campaigns over existing payment flows.
- Do not have a comprehensive **audit trail** of AI‑initiated money actions suitable for emerging agentic payment standards (UAP/AP2). [razorpay](https://razorpay.com/blog/agentic-payments-and-npci/)

The project solves:

> How to turn a Razorpay merchant into an AI‑ready, revenue‑optimised endpoint where agents can discover catalog, orchestrate checkout, and run growth workflows, with all money actions **explainable, bounded, gated, and auditable**, starting on Razorpay test‑mode.

***

## 3. Solution Architecture

### 3.1 High‑Level Components

- **Backend (apps/backend)**
  - FastAPI (Python) – HTTP API layer. [activewizards](https://activewizards.com/blog/fastapi-for-llm-systems-production-langchain-template/)
  - LangGraph – stateful, turn‑based agent workflows. [onegen](https://onegen.ai/project/building-ai-agent-applications-with-fastapi-a-comprehensive-guide-to-the-langgraph-agent-template/)
  - SQLAlchemy + Alembic – Postgres persistence and migrations.
  - Neon (cloud Postgres) – production‑grade managed database. [kunalganglani](https://www.kunalganglani.com/blog/neon-vs-supabase-2026)
  - Langfuse – observability and tracing for agent runs. [onegen](https://onegen.ai/project/building-ai-agent-applications-with-fastapi-a-comprehensive-guide-to-the-langgraph-agent-template/)

- **Frontend (apps/frontend)**
  - Next.js (TypeScript/React) – merchant dashboard UI.
  - Nx – monorepo orchestration and build tooling. [machinelearningplus](https://machinelearningplus.com/gen-ai/langgraph-project-fullstack-ai-application-fastapi/)

- **MCP Server (apps/mcp-server)**
  - Python FastMCP – MCP server exposing `catalog_tool`, `checkout_tool`, `chat_checkout_tool` for Claude Desktop and other MCP clients. [github](https://github.com/softaworks/agent-toolkit/blob/main/skills/session-handoff/README.md)

- **Infra (infra/)**
  - Docker & Docker Compose – containerised backend, frontend, MCP server, Redis.
  - Redis – rate limiting and simple messaging.
  - Nx CI – `ci.yml`, `promote.yml`, `tag-release.yml` for tests and releases.

### 3.2 Core Services

- **Razorpay Integration**
  - Uses Razorpay **test‑mode** Orders and Payments APIs for all transaction flows. [razorpay](https://razorpay.com/docs/payments/payment-gateway/web-integration/standard/integration-steps/)
  - Idempotent order creation with `Idempotency-Key` header and DB‑level safeguards. [ranjankumar](https://ranjankumar.in/fastapi-langgraph-client-disconnect-durability)
  - Webhook‑style status updates (configurable) to keep order and agent state in sync.

- **Policy & Mandate Engine**
  - Per‑merchant `Policy` model with:
    - `max_amount`
    - `allowed_categories`
    - `per_user_limit` (best‑effort, single‑cart)
    - `max_discount_pct` (safe ceiling, constrained to 0–50%)
  - Fail‑closed behaviour if key limits are missing.
  - Guardrail that `per_user_limit <= max_amount` and discounts never exceed `max_discount_pct`.

- **Audit & Explainability Layer**
  - `audit_logs` table with structured events:
    - Intent, cart, upsell decisions.
    - Policy evaluations (pass/fail + reasons).
    - Razorpay API calls and responses.
    - Final outcomes (success, failure, fallback).
  - Langfuse traces capturing:
    - Prompt/tool calls.
    - Node transitions.
    - Metadata such as `X-Agent-Name`, `X-Agent-Version`, request IDs, environment, idempotency keys.

***

## 4. Agent Workflows

### 4.1 Checkout Graph (LangGraph)

**Purpose:** Handle end‑to‑end structured checkout requests from an AI buyer or client.

**State (CheckoutState):**

- Merchant, cart items, constraints.
- Upsell suggestions (optional).
- Policy result (allowed/denied).
- Razorpay order ID and status.
- Explanation string.

**Nodes:**

1. **InputNode** – Initialise state from API request.
2. **ValidateCartNode** – Re‑price and validate cart from server‑side catalog (no trust in client‑supplied prices).
3. **SuggestUpsellNode** – Recommend upsell/cross‑sell items based on same category, availability, and simple heuristics.
4. **CheckPolicyNode** – Enforce per‑merchant policies and limits; deny if violated.
5. **CreateOrderNode** – Create Razorpay test‑mode order with idempotency semantics.
6. **FinalizeNode** – Build response: cart, upsell, order details, and explanations.

All money‑moving actions go through **CheckPolicyNode** first, satisfying “bounded and gated” requirements. [cloud.google](https://cloud.google.com/blog/products/ai-machine-learning/announcing-agents-to-payments-ap2-protocol)

### 4.2 Chat Checkout Graph

**Endpoint:** `POST /api/v1/agent/chat-checkout`

**Flow:**

- Accepts free‑text shopper request (≤ 500 chars).
- Uses LLM structured output to map intent to catalog items:
  - `product_id` constrained to real catalog enums, so hallucinated IDs are structurally impossible.
- Reuses the same **checkout_graph** for validation, policy, and order creation.
- Sanitises input before logging/tracing.

This mirrors Razorpay’s agentic in‑app and LLM flows: user intent → AI curation → checkout inside the conversation. [razorpay](https://razorpay.com/blog/agentic-payments-the-future-of-in-app-commerce/)

### 4.3 Campaign / Growth Graph

**Endpoint:** `POST /internal/campaigns/run`

**Flow:**

- `LoadOrdersNode` – Fetch recent orders.
- `SegmentCustomersNode` – Segment into high‑value, dormant, failed‑payment, etc.
- `RecommendActionsNode` – Uses LLM reasoning to propose campaigns; has a guaranteed rule‑based fallback if the LLM fails.
- `ApplyPolicyNode` – Filter actions through policy engine:
  - Enforce `max_discount_pct` and `max_amount`.
- `EmitAuditNode` – Write campaign recommendations into audit logs.

Frontend **Growth page** groups recommendations by segment and action, shows reasoning as primary text, confidence bars, and discount badges, with explicit “via LLM reasoning” vs “via rule‑based fallback” tags.

***

## 5. External Agent Integration (MCP)

Located in `apps/mcp-server/`, the MCP server exposes your backend’s capabilities to MCP‑compatible clients.

### 5.1 Tools

- **`catalog_tool`**
  - Calls `/api/v1/agent/catalog` with filters (category, max price).
  - Returns agent‑readable product listings.

- **`checkout_tool`**
  - Calls `/api/v1/agent/checkout` with structured cart.
  - Generates UUID idempotency keys if not provided.
  - Returns order details, explanations, and upsell info.

- **`chat_checkout_tool`**
  - Calls `/api/v1/agent/chat-checkout` with free‑text request.
  - Returns matched status and checkout results.

### 5.2 Auth Modes

- **Single‑tenant (Claude Desktop)**
  - `DEFAULT_MERCHANT_ID` and `DEFAULT_AGENT_API_KEY` set via env; MCP server holds one merchant’s credentials and tools work seamlessly for that context.

- **Multi‑tenant (orchestrators)**
  - Tool inputs can pass `merchant_id` and `agent_api_key` per call; MCP server forwards them.

### 5.3 Deployment

- **FastMCP server** (`server.py`) run with SSE transport:
  - `fastmcp --transport sse --port 8001`
- **Docker Compose** integration:
  - MCP server container alongside `backend`, `frontend`, `redis`.

This design keeps the MCP layer thin and delegates all business logic and policy enforcement to the FastAPI backend. [claudecowork](https://claudecowork.im/resources/session-handoff-prompt)

***

## 6. Legal, Compliance & Safety

### 6.1 Payment & Credential Sanitisation

- `data_sanitizer.py`:
  - Masks PANs (13–19 digits) to `XXXX-XXXX-XXXX-1234`.
  - Redacts CVV and expiry patterns.
  - Scrubs keys and secrets (`razorpay_key_secret`, `api_key`, auth headers).
- Global logging filter:
  - Attached in `app/main.py` to sanitize all logs.
- `AuditService.log_event()`:
  - Sanitises payloads before DB writes.
- Langfuse:
  - Free‑text shopper messages are sanitised before span attributes are recorded.

### 6.2 Retention & Cleanup

- Config: `data_retention_days` (default 90).
- Migration 0008:
  - Indexes on `audit_logs(created_at)` and `agent_runs(created_at)` for efficient purges.
- `cleanup_retention.py`:
  - CLI for manual or cron‑driven purges (with `--dry-run`).
- `router_retention.py`:
  - `POST /internal/retention/cleanup` for admin scheduling.

### 6.3 Merchant Deactivation & Data Rights

- `POST /merchant/{merchant_id}/deactivate`:
  - Sets `status="disabled"` and `deleted_at`.
  - Deletes API key hash; wipes encrypted Razorpay keys.
  - Zeros product stock.
  - Anonymises customer identifiers in past `audit_logs`.
  - Retains minimal transaction summaries to satisfy accounting/tax needs.
- `verify_agent_api_key`:
  - Rejects any deactivated merchant with HTTP 403.

### 6.4 Terms, Liability & Safety Rails

- `docs/05-terms-and-compliance.md`:
  - Documents:
    - Test‑mode scope.
    - Merchant responsibility for live deployments and PCI/RBI/NPCI/DPDP/GDPR compliance.
    - Autonomous agent liability boundaries.
- `compliance_banner.tsx`:
  - Dashboard banner reminding users that:
    - Agents act within configured limits.
    - Merchants must set policies correctly.
- Policy safety rails:
  - `max_discount_pct` enforced on campaigns.
  - `per_user_limit <= max_amount` validated on backend and frontend.

This positions the project as a **good‑faith agentic payments prototype** with clear compliance posture, not a misrepresented “fully certified” system. [cloudsecurityalliance](https://cloudsecurityalliance.org/blog/2026/06/23/is-financial-services-ready-for-agentic-payments)

***

## 7. Running the Project

From repo root:

```bash
# Backend
npx nx serve backend

# Frontend
npx nx serve frontend

# MCP server (if using Nx)
npx nx serve mcp-server
```

Or directly:

```bash
# Backend FastAPI
cd apps/backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Frontend Next.js
cd apps/frontend
npm install
npm run dev

# MCP server
cd apps/mcp-server
python server.py  # or fastmcp CLI, depending on setup
```

***

## 8. Testing & Quality

Examples (adapt to your actual commands):

```bash
# Backend tests
npx nx test backend

# Frontend tests
npx nx test frontend

# MCP server tests
npx nx test mcp-server

# Full workspace test run
npx nx run-many -t test
```

Static analysis:

```bash
ruff check apps/backend
ruff check apps/mcp-server
```

Build:

```bash
npx nx build frontend
npx nx build backend
```

***

## 9. Roadmap & Known Gaps

Deliberately deferred (documented in `ARCHITECTURE.md`):

- No Celery Beat / scheduled campaigns (manual trigger only).
- No per‑customer spend ledger (per‑user limits are single‑cart best‑effort).
- No OAuth2/JWT; auth is per‑merchant API key.
- No WAF/mTLS or least‑privilege DB roles yet.
- Rate limiter fails open on Redis failure (availability over strict enforcement).

These are intentional trade‑offs for the buildathon scope; the architecture is ready to accept these enhancements in future iterations.

***

## 10. Credits & Inspiration

This project draws architectural inspiration from:

- Razorpay’s **Agentic Payments** and **Agentic Platform**, which show what AI‑native payments and merchant experiences can look like at scale. [razorpay](https://razorpay.com/blog/razorpay-agentic-platform/)
- FastAPI + LangGraph production templates and guides for robust agent backends. [zestminds](https://www.zestminds.com/blog/build-ai-workflows-fastapi-langgraph/)
- Emerging standards for agentic payments (AP2/UCP/UAP) and design patterns for reliable agentic AI systems. [ucp](https://ucp.md/en/docs/ap2-integration/)

***
