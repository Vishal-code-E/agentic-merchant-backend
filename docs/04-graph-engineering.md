\# Graph Engineering – Razorpay Agentic Merchant Backend

\#\# 1\. Purpose of This Document

This document defines how we design, evolve, and operate LangGraph-based agent  
workflows in the Razorpay Agentic Merchant Backend.

It ties together:

\- Product goals (AI-sellable merchant, revenue growth agent).  
\- Tech stack choices (FastAPI \+ LangGraph \+ Langfuse \+ Postgres).  
\- Concrete graph patterns for checkout and revenue workflows.

The goal is to keep graph design disciplined, testable, and easy to extend.

\#\# 2\. Graph Design Principles

1\. \*\*Backend-first, graph-second\*\*  
   \- Graphs are built on top of well-defined services and APIs:  
     \- Catalog service (DB \+ REST/GraphQL).  
     \- Razorpay client (Orders, Payments).  
     \- Policy engine and audit logger.  
   \- No graph node should directly talk to external systems without going through  
     these services.

2\. \*\*Deterministic skeleton, non-deterministic reasoning\*\*  
   \- Control flow (which nodes exist, their order, and transitions) is deterministic.  
   \- LLM-based nodes are used for reasoning and suggestion (e.g., upsell choices),  
     not for core control decisions like “should we charge or not”.

3\. \*\*Policy before payment\*\*  
   \- Every money-related tool call must pass through a policy-check node first.  
   \- This enforces “bounded and gated” behaviour.

4\. \*\*State is explicit, not implicit\*\*  
   \- Graph state is a typed object (e.g., \`CheckoutState\`) persisted via  
     LangGraph checkpointers \+ Postgres.  
   \- Nodes read and write to this state; they do not rely on hidden globals.

5\. \*\*Logs and traces are first-class\*\*  
   \- Every graph run is traced in Langfuse.  
   \- Critical steps write audit entries to \`audit\_logs\`.

\#\# 3\. Key Graphs in This Project

We define two primary graphs for v1.x:

\- \`checkout\_graph\` – orchestrates agent-led checkout.  
\- \`campaign\_graph\` – runs background revenue workflows.

Additional graphs (e.g., support, onboarding) may be added later.

\#\#\# 3.1 Checkout Graph

\#\#\#\# 3.1.1 Purpose

Handle an incoming \*\*checkout request\*\* from an AI buyer or client:

\- Validate cart and constraints.  
\- Optionally suggest upsell/cross-sell within defined limits.  
\- Enforce policies/mandates.  
\- Create a Razorpay test order and return an explainable response.

\#\#\#\# 3.1.2 State Model

\`CheckoutState\` (conceptual):

\- \`merchant\_id\`  
\- \`customer\_context\` (if any)  
\- \`cart\_items\` (list of products \+ quantities)  
\- \`constraints\` (max\_amount, currency, meta)  
\- \`upsell\_suggestions\` (optional list)  
\- \`policy\_result\` (allowed/denied, reason)  
\- \`razorpay\_order\_id\` (after creation)  
\- \`status\` (pending, success, failed)  
\- \`explanation\` (human-readable string)

\#\#\#\# 3.1.3 Node Layout

1\. \*\*InputNode\*\*  
   \- Initializes \`CheckoutState\` from HTTP request.  
   \- Validates basic shape (required fields, types).

2\. \*\*ValidateCartNode\*\*  
   \- Queries catalog service for product IDs and prices.  
   \- Updates \`cart\_items\` with canonical data.  
   \- On failure: sets \`status="failed"\`, \`explanation\`, and terminates.

3\. \*\*SuggestUpsellNode\*\* (optional but enabled in v1.2+)  
   \- Uses simple heuristics or an LLM tool to propose additional items.  
   \- Writes \`upsell\_suggestions\` to state.  
   \- Does not modify \`cart\_items\` directly; requires explicit acceptance via policy.

4\. \*\*CheckPolicyNode\*\*  
   \- Calls \`policy\_engine\` with:  
     \- Current cart and upsell suggestions.  
     \- Merchant’s \`Policy\`.  
   \- Sets \`policy\_result\`:  
     \- If denied: \`status="failed"\`, \`explanation\`, terminate.  
     \- If allowed: proceed.

5\. \*\*CreateOrderNode\*\*  
   \- Calls \`razorpay\_client.create\_order()\` in test mode.  
   \- On success: sets \`razorpay\_order\_id\`, \`status="success"\`.  
   \- On error: sets \`status="failed"\`, \`explanation\` and may tag error type  
     (e.g., transient vs hard).

6\. \*\*FinalizeNode\*\*  
   \- Builds the final response payload for HTTP caller:  
     \- Cart summary.  
     \- Upsell suggestions (if any and allowed).  
     \- Razorpay order details (ID, amount, currency).  
     \- Explanation string (policies applied, upsell reasoning, any constraints).

\#\#\#\# 3.1.4 Error & Failure Handling

\- \*\*Cart validation errors\*\* → early termination with detailed explanation.  
\- \*\*Policy denial\*\* → safe failure; no external side-effect executed.  
\- \*\*Razorpay/API errors\*\* → log error, return fallback suggestions:  
  \- Try again later, adjust cart, or use different payment method.

At least one robust failure path (payment failure) is implemented and tested.

\#\#\# 3.2 Campaign Graph

\#\#\#\# 3.2.1 Purpose

Run periodic background jobs that:

\- Analyze recent orders.  
\- Identify opportunities for post-purchase offers, cart recovery, or reactivation.  
\- Emit events or instructions (e.g., create coupon, send notification).

\#\#\#\# 3.2.2 State Model

\`CampaignState\`:

\- \`merchant\_id\`  
\- \`time\_window\`  
\- \`orders\` (collection)  
\- \`segments\` (high-value, dormant, recent-failure)  
\- \`actions\` (recommended campaigns)  
\- \`status\`

\#\#\#\# 3.2.3 Node Layout

1\. \*\*LoadOrdersNode\*\*  
   \- Queries DB/Razorpay for orders in time window.

2\. \*\*SegmentCustomersNode\*\*  
   \- Simple rules to classify customers into segments (e.g., high-value, at-risk).

3\. \*\*RecommendActionsNode\*\*  
   \- Uses rules or LLM-based reasoning to propose campaigns:  
     \- E.g., “10% off for high-value customers with no purchase in 30 days.”

4\. \*\*ApplyPoliciesNode\*\*  
   \- Ensures campaigns respect merchant policy limits.

5\. \*\*EmitEventsNode\*\*  
   \- Logs recommended actions in DB/audit.  
   \- Optionally enqueues tasks to send notifications or create coupons.

\#\# 4\. Context Management

\#\#\# 4.1 Checkpointing and Persistence

\- Use LangGraph’s checkpointer integration with Postgres:  
  \- Persist \`CheckoutState\` and \`CampaignState\` across turns.  
  \- Enable retries and long-running workflows without state loss.

\- Design handlers so a \*\*client disconnect\*\* does not erase important state:  
  \- Commit state before external side-effects.  
  \- Resume from last checkpoint when needed.

\#\#\# 4.2 Limiting Context Size

\- Maintain small, structured state objects.  
\- Avoid dumping full chat transcripts into state; store only relevant signals:  
  \- Cart, policies, decisions, Razorpay events.  
\- Use Langfuse for detailed traces, but keep core state light for performance.

\#\# 5\. Tools and External Services

Graph nodes use tools that wrap external services:

\- \`catalog\_tool\` → queries product catalog.  
\- \`policy\_tool\` → evaluates policies.  
\- \`razorpay\_order\_tool\` → creates orders.  
\- \`audit\_tool\` → writes logs.  
\- \`metrics\_tool\` → optional metrics push.

Each tool:

\- Is a pure function from input → output \+ side-effect.  
\- Handles its own retries and error mapping.

\#\# 6\. Model Provider Strategy

We define a \*\*universal model provider\*\* abstraction:

\- Config-based selection between multiple LLMs (Claude, OpenAI, Gemini).  
\- Tool/graph nodes receive a \`model\_client\` via dependency injection.  
\- Changing models should not require rewriting graph structure.

In this project:

\- Use lightweight, deterministic or low-variance models for internal reasoning  
  (e.g., upsell suggestions).  
\- Reserve heavier models for user-facing narrative if needed.

\#\# 7\. Versioning of Graphs (v1 – v1.4)

\- v1.0:  
  \- Minimal \`checkout\_graph\` with Input → ValidateCart → CreateOrder → Finalize.  
  \- No upsell, simple policy checks.

\- v1.1:  
  \- Add \`SuggestUpsellNode\` and basic \`CheckPolicyNode\`.

\- v1.2:  
  \- Integrate Langfuse tracing around all nodes.  
  \- Add \`AuditLog\` writes at key events.

\- v1.3:  
  \- Introduce \`campaign\_graph\` for background jobs.  
  \- Enhance failure handling and explanations.

\- v1.4:  
  \- Refine manifests and responses for external AI clients.  
  \- Prepare structure for AP2/UCP/UAP alignment (non-breaking changes).

\#\# 8\. Testing & Validation

\- Unit tests for:  
  \- Node functions (validate cart, policy checks).  
  \- Tools (Razorpay client stub).  
\- Integration tests using:  
  \- Local Postgres (Neon/Supabase dev instances).  
  \- Razorpay test-mode APIs.  
\- Scenario tests for:  
  \- Successful checkout.  
  \- Policy denial.  
  \- Razorpay failure and graceful fallback.

\#\# 9\. Open Questions & Future Work

\- When to introduce complex recommendation models vs rules?  
\- How to integrate AP2/UCP/UAP mandates directly into graph state?  
\- How deep multi-agent orchestration should go (e.g., dedicated “policy agent”)?

These will be revisited after the initial 4-day buildathon.

