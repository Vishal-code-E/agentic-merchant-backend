# Demo: see it work in 5 minutes

Script-driven, copy-paste-ready — no UUIDs or keys to paste by hand. Each
command below either produces the next one's input as a shell env var, or
needs nothing but Razorpay test-mode credentials you already have.

## Prerequisites

- The backend running locally (`nx serve backend`, or `docker compose -f infra/docker-compose.yml up`) at `http://localhost:8000`.
- `.env` filled in per the [README setup section](../README.md#local-setup) — `DATABASE_URL`, `LANGFUSE_PUBLIC_KEY`/`SECRET_KEY`, `ANTHROPIC_API_KEY`, `ENCRYPTION_KEY`.
- Razorpay **test-mode** key id + secret (from [dashboard.razorpay.com](https://dashboard.razorpay.com), Test Mode → Settings → API Keys).
- `apps/backend/requirements.txt` installed (`nx run backend:install`).
- `jq` is used below for pretty-printing; drop `| jq` from any command if you don't have it, or swap in `python3 -m json.tool`.

All commands assume you're at the repo root, in a shell that keeps exported
env vars across commands (regular bash/zsh — nothing exotic).

## 1. Set up a demo merchant + catalog

```bash
export RAZORPAY_KEY_ID=<your test key id>
export RAZORPAY_KEY_SECRET=<your test key secret>

cd apps/backend
eval "$(python scripts/setup_demo_merchant.py)"
cd ../..
```

This onboards a merchant ("Demo Skincare Co"), sets its policy (`max_amount=700`,
no category restriction), seeds two products (Face Wash ₹380, Moisturizer
₹420), and exports `MERCHANT_ID`, `AGENT_API_KEY`, and `BASE_URL` into your
shell — every command after this one uses those, not literal values.

```bash
echo "Merchant: $MERCHANT_ID"
```

## 2. Fetch the agent discovery manifest

No auth needed — this is what an agent reads *before* it has an API key, to learn the contract.

```bash
curl -s http://localhost:8000/.well-known/agent-manifest.json | jq
```

Look at `endpoints.catalog`, `endpoints.checkout`, and `endpoints.chat_checkout` — every `/agent/*` route is self-described here.

## 3. Run the AI-buyer script

Plays an external AI shopping agent over plain HTTP — the same contract any
third-party integration would use. Walks catalog discovery, a compliant
checkout, a deliberate policy denial, and two conversational-checkout
messages (one that matches a product, one that doesn't).

```bash
cd apps/backend
python scripts/ai_buyer_demo.py
cd ../..
```

Expect, in order:

1. 🔍 the two seeded products
2. 📜 the policy (`max_amount=700`)
3. 🛒✅ a successful checkout of the cheaper item (Face Wash, ₹380)
4. 🛒❌ a checkout for a cart over ₹700 — denied with the policy's own reason
5. 💬✅ `"1x Face Wash"` interpreted and checked out via `/agent/chat-checkout`
6. 💬 `"buy me a spaceship"` — `matched=false`, HTTP 200, not an error

## 4. Inspect the audit trail

```bash
curl -s "http://localhost:8000/api/v1/observability/agent-runs?merchant_id=$MERCHANT_ID" | jq
```

Pick any `id` from the list and pull its audit log — this is the
explainability layer: every policy check, denial, idempotency replay, and
(for the chat-checkout runs) the raw message alongside its interpretation.

```bash
RUN_ID=$(curl -s "http://localhost:8000/api/v1/observability/agent-runs?merchant_id=$MERCHANT_ID" | jq -r '.[0].id')
curl -s "http://localhost:8000/api/v1/observability/agent-runs/$RUN_ID/audit-logs" | jq
```

Or open the dashboard instead: http://localhost:3000/observability (paste `$MERCHANT_ID` into the merchant switcher once, or onboard through the UI directly).

## 5. Run the campaign orchestrator

```bash
curl -s -X POST http://localhost:8000/api/v1/internal/campaigns/run \
  -H "Content-Type: application/json" \
  -d "{\"merchant_id\": \"$MERCHANT_ID\"}" | jq
```

The Face Wash purchase from step 3 (₹380) clears `campaign_graph`'s
high-value threshold (half of `max_amount`, i.e. ₹350) — that's not a
coincidence, `setup_demo_merchant.py`'s numbers are chosen so this step has
something real to recommend, not an empty `{"actions": []}`. Expect one
`upsell_followup` action, re-validated against the merchant's current policy
before being returned.

## What you just saw

| Step | Agentic direction |
|---|---|
| 2 | **Catalog discovery** — the manifest + `GET /agent/catalog` |
| 3.3–3.4 | **Policy-gated checkout** — the non-negotiable gate everything else sits behind |
| 3.5–3.6 | **Conversational checkout** — free text → structured cart → same checkout path |
| 5 | **Campaign orchestrator** — background segmentation + recommendation |
| 4 | **Observability** — every one of the above, traced and audited |

`suggest_upsell_node` (the **upsell/cross-sell** direction) runs on every
checkout in step 3, but with this demo's numbers Moisturizer (₹420) doesn't
fit in the ₹320 left after buying Face Wash, so `filter_upsells` withholds it
and no suggestion prints — the code path ran, it just had nothing
policy-compliant to offer. To see a suggestion, either raise `max_amount` or
lower `Moisturizer`'s price in `setup_demo_merchant.py` and re-run from step 1.

For the "why" behind each design decision, see [`ARCHITECTURE.md`](./ARCHITECTURE.md).
