\# Dev Handoff & LLD – Razorpay Agentic Merchant Backend

\#\# 1\. Tech Stack Overview

\- Backend:  
  \- Python, FastAPI (HTTP APIs, validation, OpenAPI docs).\[cite:54\]  
  \- LangGraph (agent workflows, stateful turns).\[cite:44\]\[cite:53\]  
  \- Langfuse (agent tracing and analytics).\[cite:44\]  
\- Frontend:  
  \- Next.js (TypeScript, React) for merchant dashboard.  
\- Data:  
  \- Postgres via Neon or Supabase (cloud-managed).  
  \- Redis (caching, lightweight messaging).  
\- Background jobs:  
  \- Celery or equivalent worker (e.g., RQ, Dramatiq).  
\- Infra:  
  \- Docker for containerization.  
  \- GitHub for version control (feature branches, PRs).  
  \- CI/CD (GitHub Actions) for build/test/deploy.

\#\# 2\. Repository Layout (Monorepo)

\`\`\`text  
/agentic-merchant-backend  
  /apps  
    /backend  
      app/main.py  
      app/api/  
      app/models/  
      app/services/  
      app/agents/  
      app/config/  
      app/workers/  
    /frontend  
      next-app/  
  /docs  
    01-product-understanding.md  
    02-prd-agentic-merchant-backend.md  
    03-dev-handoff-architecture-lld.md  
  /infra  
    Dockerfile.backend  
    Dockerfile.frontend  
    docker-compose.yml  
    k8s/  
  .github/  
    workflows/  
\`\`\`

\#\# 3\. Backend LLD

\#\#\# 3.1 Modules

\- \`app/api/\`  
  \- \`router\_catalog.py\` – \`/merchant/products\`, \`/agent/catalog\`.  
  \- \`router\_checkout.py\` – \`/agent/checkout\`.  
  \- \`router\_onboarding.py\` – Razorpay key onboarding.  
  \- \`router\_observability.py\` – audit \+ traces endpoints.

\- \`app/models/\`  
  \- \`merchant.py\`, \`product.py\`, \`order.py\`, \`policy.py\`, \`agent\_run.py\`, \`audit\_log.py\`.

\- \`app/services/\`  
  \- \`razorpay\_client.py\` – wrapper for Orders, Payments APIs.  
  \- \`policy\_engine.py\` – evaluate mandates/limits.  
  \- \`audit\_service.py\` – write structured logs.

\- \`app/agents/\`  
  \- \`checkout\_graph.py\` – LangGraph graph definition for checkout.  
    \- Nodes: \`validate\_cart\`, \`suggest\_upsell\`, \`check\_policies\`, \`create\_order\`, \`finalize\`.  
  \- \`campaign\_graph.py\` – background revenue workflows.

\- \`app/workers/\`  
  \- \`tasks.py\` – Celery tasks for campaign runs, data sync.

\#\#\# 3.2 Data Model Sketch

\- \`Merchant\`  
  \- \`id\`, \`name\`, \`razorpay\_key\_id\`, \`razorpay\_key\_secret\`, \`status\`.

\- \`Product\`  
  \- \`id\`, \`merchant\_id\`, \`name\`, \`description\`, \`price\`, \`currency\`,  
    \`category\`, \`tags\`, \`stock\`.

\- \`Order\` (internal)  
  \- \`id\`, \`merchant\_id\`, \`razorpay\_order\_id\`, \`status\`, \`amount\`, \`currency\`,  
    \`cart\_snapshot\`, \`created\_at\`.

\- \`Policy\`  
  \- \`id\`, \`merchant\_id\`, \`max\_amount\`, \`allowed\_categories\`, \`per\_user\_limit\`,  
    \`rules\_json\`.

\- \`AgentRun\`  
  \- \`id\`, \`merchant\_id\`, \`type\` (checkout/campaign), \`status\`,  
    \`langfuse\_trace\_id\`, \`started\_at\`, \`ended\_at\`.

\- \`AuditLog\`  
  \- \`id\`, \`agent\_run\_id\`, \`event\_type\`, \`payload\_json\`, \`created\_at\`.

\#\#\# 3.3 LangGraph Agent Workflow (Checkout)

High-level flow:

1\. \*\*Input node\*\*: Receive \`CheckoutRequest\` (cart, constraints).  
2\. \*\*Validate cart node\*\*:  
   \- Load products from DB.  
   \- Return error if invalid.  
3\. \*\*Suggest upsell node\*\* (optional):  
   \- Run heuristics to add potential upsell items.  
4\. \*\*Check policy node\*\*:  
   \- Use \`policy\_engine\` to evaluate:  
     \- \`max\_amount\`, \`allowed\_categories\`, etc.  
   \- If failed: return error \+ explanation.  
5\. \*\*Create order node\*\*:  
   \- Call \`razorpay\_client.create\_order()\` (test mode).  
   \- Attach idempotency keys and error handling.  
6\. \*\*Finalize node\*\*:  
   \- Build response for caller (order details, explanation).  
   \- Log audit events.

Langfuse integration:

\- Wrap each run with a trace.  
\- Record nodes, tool calls, and outputs.

\#\#\# 3.4 Error and Disconnect Handling

Based on production FastAPI \+ LangGraph guidance:

\- Use idempotency keys on each external side-effect (order creation, campaigns).\[cite:56\]  
\- Design request handlers such that:  
  \- External effects (Razorpay calls) happen in background tasks when needed.  
  \- Agent state is checkpointed before and after side-effects.

\#\#\# 3.5 Security & Configuration

\- Use \`pydantic-settings\` for configuration (Razorpay keys, DB URLs, model provider keys).\[cite:54\]  
\- Store secrets via environment variables or cloud secret manager.  
\- Ensure no keys in logs or metrics.

\#\# 4\. Frontend LLD (Dashboard)

\- Next.js pages:  
  \- \`/onboarding\` – connect Razorpay keys.  
  \- \`/catalog\` – manage products.  
  \- \`/policies\` – configure limits and rules.  
  \- \`/observability\` – view agent runs and audit logs.  
\- Use a simple design system (Tailwind, shadcn/ui) and call backend APIs via REST/GraphQL.

\#\# 5\. Branching & Release Strategy

\- Branches:  
  \- \`feature/v1.0-foundations\`  
  \- \`feature/v1.1-catalog-checkout\`  
  \- \`feature/v1.2-revenue-agent\`  
  \- \`feature/v1.3-observability-dashboard\`  
\- Each feature branch:  
  \- Has its own short LLD section and checklist.  
  \- Merged into \`main\` when passing tests and review.

\#\# 6\. Handoff Notes

\- Include API examples (request/response JSON) in \`docs/api-examples.md\`.  
\- Link to FastAPI OpenAPI docs (\`/docs\`) for live testing.\[cite:54\]  
\- Keep LangGraph graphs small and composable to ease debugging.\[cite:53\]  
