\# PRD – Razorpay Agentic Merchant Backend

\#\# 1\. Product Goal

Build an agentic backend that:

\- Makes Razorpay merchants discoverable and transactable by AI agents via  
  agent-readable catalog and checkout APIs.  
\- Runs a safe, explainable revenue agent on top of Razorpay test-mode APIs.  
\- Provides observability and auditability of agent actions and money flows.

\#\# 2\. Scope (v1 – v1.4 over 4 days)

\#\#\# v1.0 – Foundations (Day 1\)

\- Razorpay test-mode integration:  
  \- Store test API keys securely.  
  \- Create and fetch Orders via FastAPI endpoints.\[cite:20\]\[cite:21\]  
\- Basic Postgres schema:  
  \- \`merchants\`, \`products\`, \`orders\`, \`policies\`, \`agent\_runs\`, \`audit\_logs\`.  
\- Health checks and simple “ping” endpoint.

\#\#\# v1.1 – Agent-Readable Catalog & Checkout API (Day 2\)

\- Catalog module:  
  \- CRUD for \`products\` via merchant dashboard (Next.js).  
  \- \`/agent/catalog\` endpoint (REST/GraphQL) with filter params.

\- Checkout module:  
  \- \`/agent/checkout\` endpoint that accepts a structured cart request.  
  \- Validates items against catalog.  
  \- Creates Razorpay test Order and returns a checkout object (order\_id, URL, amount).

\#\#\# v1.2 – Revenue Agent \+ Policy Guard (Day 3\)

\- LangGraph agent:  
  \- Nodes for: \`validate\_cart\`, \`suggest\_upsell\`, \`check\_policies\`, \`create\_order\`.  
  \- Turn-based workflow with clear termination.

\- Policy engine:  
  \- Define \`policies\` per merchant (max\_amount, allowed\_categories, per-user limits).  
  \- Enforce policy before order creation.

\- Background jobs:  
  \- Celery/worker or equivalent for simple campaign (e.g., post-purchase coupon suggestion).

\#\#\# v1.3 – Observability & Audit (Day 3–4)

\- Langfuse integration:  
  \- Capture traces for agent runs (inputs, tool calls, outputs).\[cite:44\]

\- Audit log:  
  \- Persist agent decisions, Razorpay API calls, and outcomes in \`audit\_logs\`.

\- Dashboard views:  
  \- Timeline view of orders and agent actions.  
  \- Detail view for a single agent run.

\#\#\# v1.4 – Demo-Ready UX & Docs (Day 4\)

\- Clean Next.js dashboard:  
  \- Connect Razorpay, manage catalog, configure policies, view metrics.

\- Sample “AI buyer” client or script showcasing:  
  \- Catalog discovery.  
  \- Checkout request.  
  \- Successful and failed flows.

\- Documentation:  
  \- README for product overview.  
  \- API docs (OpenAPI from FastAPI).  
  \- Setup and deployment guide.

\#\# 3\. Functional Requirements

\#\#\# 3.1 Merchant Onboarding

\- Ability to add/update Razorpay test keys.  
\- Validation of keys through a test API call.\[cite:19\]\[cite:20\]  
\- Secure storage (no plaintext keys in logs).

\#\#\# 3.2 Catalog Management

\- Create/edit/delete products with:  
  \- Name, description, price, currency, category, stock, tags.  
\- Agent catalog endpoint:  
  \- Returns JSON or GraphQL schema suitable for LLM/agent consumption.

\#\#\# 3.3 Checkout Orchestration

\- Accept cart payload from external agents.  
\- Validate catalog and policies.  
\- Create Razorpay Order (test).  
\- Return enriched response with:  
  \- Payment info.  
  \- Applied offers.  
  \- Explanation string.

\#\#\# 3.4 Revenue Agent

\- For an incoming checkout:  
  \- Optionally suggest upsell/cross-sell items given a cart and rules.  
\- For completed orders:  
  \- Optionally schedule a follow-up campaign (log-only in v1).

\#\#\# 3.5 Observability

\- Langfuse traces for agent runs.  
\- Audit logs linking:  
  \- Intent, policy checks, external calls, outcomes.

\#\#\# 3.6 Failure Handling

\- Explicit flow for payment failure:  
  \- Recognize failure via webhook.  
  \- Log reason.  
  \- Respond with fallback suggestion (e.g., different payment method, reduced cart).

\#\# 4\. Non-Functional Requirements

\- \*\*Security:\*\* API keys stored via environment or secrets manager; no keys in code.\[cite:54\]  
\- \*\*Reliability:\*\* Idempotent order creation and webhook processing.  
\- \*\*Scalability:\*\* Horizontally scalable FastAPI \+ Postgres architecture.  
\- \*\*Maintainability:\*\* Monorepo with clear module boundaries and documentation.

\#\# 5\. Out-of-Scope (for v1)

\- Real live-mode settlements and reconciliation.  
\- Complex recommendation models (use heuristics initially).  
\- Full AP2/UCP/UAP integration (only design alignment).  
