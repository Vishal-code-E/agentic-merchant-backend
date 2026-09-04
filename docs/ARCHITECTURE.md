# Architecture (as-built)

Short and opinionated — this is the file to read for the *why* behind design
decisions, not an exhaustive reference. For the full request/response
contract, use FastAPI's auto-generated `/docs`. For the original planning
docs, see `03-dev-handoff-architecture-lld.md` and `04-graph-engineering.md`
— this file describes what actually shipped, which in a few places (auth,
idempotency, chat-checkout, the growth agent) goes beyond what those
planning docs anticipated.

## `checkout_graph`: node flow

```
                    ┌───────┐
                    │ Input │  fills CheckoutState defaults
                    └───┬───┘
                        ▼
                ┌───────────────┐
                │ ValidateCart  │  DB lookup: real prices, stock, one currency
                └───────┬───────┘
             failed ┌───┴───┐ ok
                     ▼       ▼
               ┌─────────┐ ┌───────────────┐
               │Finalize │ │ SuggestUpsell │  heuristic cross-sell, no LLM,
               └─────────┘ │  (never fails)│  never mutates cart_items
                            └───────┬───────┘
                                    ▼
                            ┌───────────────┐
                            │ CheckPolicy   │  ← the one gate everything
                            └───────┬───────┘    must clear before payment
                         failed ┌───┴───┐ ok
                                 ▼       ▼
                           ┌─────────┐ ┌─────────────┐
                           │Finalize │ │ CreateOrder │  idempotency check →
                           └─────────┘ └──────┬──────┘  Razorpay call
                                               ▼
                                         ┌─────────┐
                                         │Finalize │
                                         └─────────┘
```

`checkout_graph.py` wires this with `add_conditional_edges` after
`ValidateCart` and `CheckPolicy` (`_route_after_validate`,
`_route_after_policy`) — every failure path collapses straight to `Finalize`
rather than continuing, so a single function builds the response regardless
of which node stopped the run.

## Why policy sits between upsell and payment

`CheckPolicy` runs *after* `SuggestUpsell` and *before* `CreateOrder` — not
earlier, not later, and that position is load-bearing:

- **Not before SuggestUpsell.** Policy has to judge whatever might end up in
  front of the customer, and an upsell suggestion is exactly that. Running
  policy first would mean a suggested item — invented by the backend, not
  requested by the customer — could reach the response without ever being
  checked against the merchant's budget or category rules.
- **Not after CreateOrder.** That would mean money already moved before the
  check ran, which is the one thing this system is built to never do (see
  "Non-negotiable design rule" in the README).
- **Exactly here**, `check_policy_node` does two things in one pass:
  `PolicyEngine.filter_upsells()` drops any suggestion that would push the
  cart over budget or outside an allowed category, then
  `PolicyEngine.evaluate()` judges the customer's own cart on its own terms
  — a bad suggestion is *never* allowed to sink a valid cart, and a valid
  cart is never let through just because a suggestion attached to it looked fine.

This is also where the merchant's policy gets a durable, independent audit
record (`policy_check` event) — logged whether the decision is allow or
deny, since "the gate ran and here's what it saw" is itself evidence, not
just the outcome.

## Auth and idempotency model

**Auth** — every `/agent/*` call carries `X-Agent-Api-Key`. Keys are
generated once (at onboarding, or via the regenerate endpoint), returned in
plaintext exactly that one time, and stored server-side only as a sha256
hash (`agent_auth.py`) — comparison is `hmac.compare_digest`, not a
string `==`. A merchant onboarded before this feature existed has no hash on
record and fails closed: there is no key that satisfies an unset hash, by
design, the same posture `check_policy_node` takes toward a missing policy.

**Idempotency** — `POST /agent/checkout` requires an `Idempotency-Key`
header (missing → 400, checked before any DB/graph work starts).
`create_order_node` SELECTs for an existing `Order` with that
`(merchant_id, idempotency_key)` pair first; if none exists, it INSERTs with
`ON CONFLICT DO NOTHING` and re-SELECTs on a conflict — closing the race
between two concurrent requests carrying the same key without a second
Razorpay call. A replayed key is only honored if the cart signature
(sorted `(product_id, quantity)` pairs) matches the original request; a
mismatch is a 409, not a silent reuse of someone else's order.

`POST /agent/chat-checkout` makes `Idempotency-Key` **optional** — a chat
message has no natural header to carry — and generates one internally per
call when it's absent. That is a deliberate trade: a retried chat message
without an explicit key is *not* idempotent and can create a second order.
Any caller that wants replay-safety on chat-checkout supplies its own key,
exactly like `/agent/checkout`.

## How chat-checkout reuses `checkout_graph`

`checkout_graph.py` was not touched to add conversational checkout.
`POST /agent/chat-checkout` (`router_checkout.py`) instead:

1. Loads the merchant's live, in-stock catalog.
2. Calls `intent_parser.parse_intent_to_cart(message, catalog, merchant_id)`
   — a call to whichever provider `settings.model_provider` names (Anthropic's
   Messages API `output_config.format`, or OpenAI's Chat Completions
   `response_format`), both constrained to the same JSON schema whose
   `product_id` field is an `enum` of that catalog's real ids. The model is
   *structurally* unable to return a product id that doesn't exist — not just
   instructed not to; verified empirically in the final test pass with
   prompt-injection attempts to force a fake id, an absurd quantity, and a
   fabricated price, all rejected by the schema/DB layer regardless of what
   the model did. No confident match → `(None, explanation)`, never an
   empty/best-guess cart.
3. Writes an `intent_parsed` audit row (raw message + interpretation) —
   *before* the checkout outcome is known, so the translation step itself is
   evidence, independent of whether the resulting cart succeeds.
4. On a match, hands the resulting `CheckoutRequest` to `_run_checkout_graph()`
   — the exact same helper `POST /agent/checkout` calls, which builds
   `CheckoutState` and invokes `checkout_graph.ainvoke()` unmodified. Same
   `ValidateCart → SuggestUpsell → CheckPolicy → CreateOrder → Finalize`,
   same `checkout_denied` auditing, same failure-stage → HTTP-status mapping.

A "no confident match" result is `matched: false` with HTTP **200** — the
agent asked for something this catalog can't satisfy, which is a normal
outcome the caller needs to see clearly, not a server error to retry.

## Growth Agent: `campaign_graph`'s RecommendActions

`campaign_graph.py`'s `RecommendActions` node reasons with an LLM instead of
a fixed rule map — `app/services/growth_agent.py`, same
Anthropic/OpenAI structured-output pattern as `intent_parser.py` (schema-
constrained JSON, provider chosen by `settings.model_provider`). Every other
node (`LoadOrders`, `SegmentCustomers`, `ApplyPolicy`, `EmitAudit`) is
unchanged.

**What it reasons over.** `SegmentCustomers`' output (which of
`failed_payment_recent`/`high_value_cart` currently have orders, as counts +
total amounts — not raw order data), the merchant's real in-stock catalog
(id/name/price/category), and its policy (`max_amount`,
`allowed_categories`, `per_user_limit`). Recommendations are grounded in
that real data, not generic marketing copy, and `target_segment` is
enum-constrained to segments that actually have orders this run — the model
is structurally unable to target an empty or nonexistent segment, the same
trick `intent_parser.py` uses for `product_id`.

**The discount guardrail.** `suggested_discount_pct` is constrained to
`0`-`30` twice: in the JSON schema handed to the model, and again as a
Pydantic field constraint (`ge=0, le=30`) on the parsed result — belt and
suspenders, since a schema is a request to the provider, not a guarantee.
Values outside that range fail validation and trigger the fallback below,
same as any other unparseable output.

**The fallback.** Any failure — missing/misconfigured provider key,
network error, truncated response, or a parsed result that fails
validation (an out-of-range discount, an unknown segment, a malformed
field) — is caught inside `recommend_campaign_actions()` and never
propagates: it falls back to the original v1.3 rule map
(`failed_payment_recent → retry_nudge`, `high_value_cart → loyalty_offer`)
so a campaign run degrades gracefully instead of failing outright. Which
path produced each action (`llm_reasoning` vs `rule_based_fallback`) is
recorded on the action itself and carried straight through to the
`campaign_recommendation` audit row and the API response
(`CampaignActionResult.path`) — this is deliberately visible, not swallowed,
because "how often is this feature actually reasoning vs falling back" is
itself operationally important to know.

**ApplyPolicy is still the only gate.** The growth agent (or its fallback)
only ever *proposes* — `RecommendActions` expands each segment-level
recommendation into one candidate action per order in that segment, and
`ApplyPolicy` (byte-for-byte unchanged) re-runs `PolicyEngine.evaluate()`
against each order's real cart before anything survives to `EmitAudit`.
Smarter reasoning about *which* action to propose changes nothing about
*whether* it's allowed to reach the merchant — that check doesn't know or
care whether an action came from the LLM or the rule-based fallback.

## How tracing and audit logging plug in

**Langfuse** — each of `/agent/checkout`, `/agent/chat-checkout`, and
`/internal/campaigns/run` is wrapped in `@observe()` (capture_input/output
disabled and set explicitly, so the raw `AsyncSession` argument never leaks
into a trace) inside a `propagate_attributes(trace_name=..., tags=[...],
metadata={...}, environment=...)` block, all three carrying the same
`merchant_id`/`endpoint`/`request_id` metadata and `environment` tag — the
checkout endpoints add `agent_name`/`agent_version`/`idempotency_key` on top
(see Security Model above). The LangGraph `CallbackHandler` is passed as the
graph's `config`, so every node in the run becomes a child span under that
same trace automatically — chat-checkout's trace is tagged `["checkout",
"chat"]` so it's identifiable as chat-originated without a separate
dashboard.

**`AgentRun`** — one row per call, created before the graph runs and updated
(`status`, `ended_at`) after. `langfuse_trace_id` is the *real* trace id from
the Langfuse SDK, not a locally invented label, so an `AgentRun` row and its
Langfuse trace look each other up directly.

**`AuditLog`** — structured rows keyed to an `agent_run_id`, written at the
specific decision points that need to be independently reconstructable:
`policy_check` (every policy evaluation, allow or deny), `checkout_denied`,
`checkout_idempotent_replay` / `checkout_idempotency_conflict`,
`razorpay_order_created` / `razorpay_order_failed`, `intent_parsed`
(chat-checkout only), `suspicious_input_detected` (chat-checkout only — see
Security Model below), and `campaign_recommendation` (now also carrying
`reasoning`/`confidence`/`path` per action — see Growth Agent above). These are `flush()`ed,
not `commit()`ed, inside `AuditService` — they ride the caller's own
transaction, and become durable exactly when that transaction does. Anywhere
a row needs to survive an `HTTPException` that follows it, the router
commits explicitly first — `get_db()` rolls back the whole session on any
exception, so an uncommitted "we're about to raise" write would otherwise be
the first thing discarded.

## Security Model

**Auth.** See "Auth and idempotency model" above for the hashing/compare
details. Added on top of that: `verify_agent_api_key` also stamps
`Merchant.last_used_at` on every successful check — a mutation on the
already-loaded row, no extra query or commit of its own, so it's free
(rides whatever commit the request was already going to do). Regenerating a
key (`POST /merchant/{id}/api-key/regenerate`) overwrites `api_key_hash` in
place — confirmed there is no code path that keeps the old hash valid
alongside the new one, so regeneration *is* revocation; no separate
DELETE/revoke endpoint was needed.

**Rate limiting.** Every `/agent/*` call is capped per API key via Redis
(`app/services/rate_limiter.py`): 60/min on `agent/catalog`, 20/min on
`agent/checkout`, 10/min on `agent/chat-checkout` (tightest because it's the
one endpoint that costs an LLM call per request). Fixed-window counter, not
a sliding log — cheaper, at the cost of allowing a burst across a window
boundary; see that module's docstring. Fails **open**: if Redis is down or
misconfigured, requests proceed unlimited and a warning is logged, rather
than a side-car cache outage taking every agent endpoint down with it. That
is a deliberate availability-over-strictness call for v1, not an oversight —
it means the rate limit is a cost/abuse control, not something callers (or
this system) should treat as a hard guarantee.

**Chat-checkout's defense against prompt injection is layered, and the
layers are not equally load-bearing:**

1. *Structured output, enum-constrained to the real catalog*
   (`intent_parser.py`) — the model is structurally unable to return a
   `product_id` that doesn't exist in this merchant's catalog. This narrows
   what a manipulated model *can* claim, but it is **not** the security
   boundary — it's defense-in-depth.
2. *The actual boundary*: `checkout_graph.validate_cart_node` re-derives
   price, currency, and stock from the DB for every `product_id` regardless
   of where the request came from (structured `/agent/checkout` or
   LLM-parsed `/agent/chat-checkout`) — the request schema doesn't even have
   a price field for the model to populate. `create_order_node` only ever
   spends `state["amount"]`, which came from that DB lookup, never from
   anything the model said. A compromised or successfully-jailbroken model
   can at most cause a *legitimate, in-catalog, correctly-priced* cart to be
   proposed — it cannot make the system charge an invented amount or a
   nonexistent product.
3. *Detection, not blocking*, on top of both: `intent_parser.py` rejects
   messages over 500 chars before any model call (cost/DoS guard), and
   flags known jailbreak phrasings (`"ignore previous instructions"`,
   `"system prompt"`, etc.) via substring match. A match tags the Langfuse
   trace (`suspicious_input=true`) and writes an `audit_logs` row
   (`suspicious_input_detected`) — but does **not** refuse the request.
   Blocking on a heuristic string match would false-positive on legitimate
   text (e.g. "acting as a gift" contains no listed phrase, but a stricter
   list easily catches innocent orders) and provides no real safety margin
   anyway, since layer 2 doesn't trust the model's output regardless of
   whether the message looked suspicious.

**DB constraints.** `policies.max_amount`/`per_user_limit` (`> 0` when not
NULL), `products.price`/`stock` (`>= 0`), `orders.amount` (`> 0`) are all
enforced with `CHECK` constraints (migration `0007`), independent of the
Pydantic layer above them — these hold even against a bug, a script, or a
future admin tool that reaches the DB directly.

**Agent identity.** `X-Agent-Name`/`X-Agent-Version` (optional, default
`"unknown"`) are informational only — never checked, never a trust
boundary — and are recorded three places for correlation: the `AgentRun`
row (`agent_name`/`agent_version` columns, migration `0006`), the Langfuse
trace metadata, and (alongside a fresh per-request `request_id` and
`idempotency_key` when present) every propagated span under that trace.

**Checked for secret leakage into logs/traces** (a real grep, not a
formality): every `AuditService.log_event()` call site and every
`langfuse.update_current_span()`/`propagate_attributes()` call in
`app/agents/` and `app/api/` were read directly. None pass
`Merchant.razorpay_key_secret`, `Merchant.api_key_hash`, the plaintext
agent API key, `settings.encryption_key`, or any model-provider key into a
payload/input/metadata dict — `@observe(capture_input=False,
capture_output=False)` also means neither checkout endpoint's raw
`AsyncSession`/header arguments get auto-captured. The one place an
externally-sourced error string reaches an audit payload is
`razorpay_order_failed`'s `"error": str(e)` — this wraps Razorpay's own API
response body (auth is HTTP Basic via `razorpay.Client(auth=(key_id,
key_secret))`, not echoed back in error text), not anything this codebase
constructs from the secret itself; residual risk here is bounded by the
Razorpay/Anthropic/OpenAI SDKs' own error-formatting behavior, not by
application code.

**Known gaps, not addressed tonight** (same honest framing as the
`per_user_limit` gap above — a scope call, not an oversight):

- **No least-privilege DB role.** The app connects as whatever role
  `DATABASE_URL` names, with no separate read-only/limited role for anything.
- **No OAuth/JWT.** Auth is a single static bearer key per merchant, not a
  token with expiry, scopes, or refresh.
- **No per-agent scoped permissions.** One API key authorizes everything a
  merchant's agent integration can do; there's no narrower scope (e.g.
  catalog-read-only) beneath the merchant level.
- **No WAF/mTLS.** Nothing in front of the app enforces network-layer
  identity or filters malicious traffic beyond the app-level rate limiter.
- **Rate limiting fails open.** By design (see above) — an outage of Redis
  itself is not a path to unlimited spend, since every checkout still goes
  through policy + real Razorpay calls, but it does remove the abuse/cost
  guard on `chat-checkout` specifically for as long as Redis is down.
