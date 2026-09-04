# Terms of Service, Legal Framing & Compliance Architecture

This document establishes the compliance posture, regulatory responsibilities, and liability framework for the **Razorpay Agentic Merchant Backend & Copilot**.

---

## 1. Operating Environment & Test-Mode Boundary

### 1.1 Test-Mode Operational Scope
The system operates **exclusively against Razorpay Test Mode APIs** using test credentials (`rzp_test_*`). 
- **No Real Fiat Transactions**: No real currency, bank accounts, UPI rails, or credit/debit facilities are charged, captured, or settled.
- **Simulated Order Fulfillment**: All order IDs (e.g., `order_test_*`), payment IDs, and transaction states represent sandbox entities generated for developer integration, testing, and agentic capability demonstrations.
- **No Production Secrets**: Storing live Razorpay production API keys (`rzp_live_*`) in this repository or its configuration environments is strictly prohibited.

---

## 2. Regulatory Responsibilities for Live-Mode Deployment

While this software is architected for hackathon demonstrations, sandboxed evaluation, and prototype integrations, moving any agentic payment backend to a live production environment requires adherence to stringent legal and financial standards:

### 2.1 PCI DSS (Payment Card Industry Data Security Standard)
- **Zero Cardholder Data Storage**: This backend does **not** collect, process, or store Primary Account Numbers (PANs), CVVs, or cardholder magnetic stripe data.
- **Hosted Fields / Tokenization Requirement**: Any merchant deploying a consumer-facing payment interface must use Razorpay Standard Checkout or hosted fields to ensure all payment card entry occurs within PCI DSS Level 1 certified iframe boundaries (reducing merchant audit scope to SAQ A).
- **Sanitization Safeguards**: All inputs, outputs, log records, and Langfuse tracing spans pass through an automated `data_sanitizer` filter (`app/services/data_sanitizer.py`) that redacts PAN patterns (13–19 digits), CVVs, expiry dates, and secret tokens before they can be written to disk, console, or external observability providers.

### 2.2 Reserve Bank of India (RBI) & NPCI Directives
Merchants operating in India or handling Indian payment instruments are subject to regulatory mandates enforced by the RBI:
- **Card-on-File Tokenization (CoFT)**: Storing actual card details on merchant servers is prohibited. All card-based payments must utilize network tokens issued by authorized card networks.
- **Additional Factor of Authentication (AFA / 2FA)**: Autonomous agents **cannot** bypass mandatory two-factor authentication (OTP or biometric verification) for customer payments, except within regulatory exemptions (e.g. e-mandates up to ₹15,000 with pre-debit notifications).
- **Pre-Debit Notifications**: Any recurring subscription or automated debit initiated through agentic campaign recommendations must trigger customer notification at least 24 hours prior to debit.

### 2.3 GDPR & Digital Personal Data Protection (DPDP) Act 2023
- **Data Minimization**: Shopper data accepted via `customer_context` (e.g. `customer_id`) is strictly used for evaluating per-user spending limits and linking traces. No extraneous PII is persisted in transactional models.
- **Configurable Data Retention (Default 90 Days)**: Audit trails (`audit_logs`) and agent execution telemetry (`agent_runs`) are governed by a configurable retention policy (`settings.data_retention_days`, default: 90 days). An automated purge script (`app/scripts/cleanup_retention.py`) and administrative endpoint (`POST /internal/retention/cleanup`) purge historical records once their retention window expires.
- **Merchant Deactivation & Data Subject Rights**:
  - A merchant can request complete deactivation via `POST /api/v1/merchant/{merchant_id}/deactivate` or `DELETE /api/v1/merchant/{merchant_id}`.
  - **Immediate Revocation**: The merchant's API key hash (`api_key_hash`) is wiped, encrypted Razorpay credentials are set to null, and catalog items are marked with zero stock. Subsequent `/agent/*` calls fail immediately with HTTP 403 Forbidden.
  - **Audit Anonymization**: Customer identifiers inside historical `AuditLog.payload_json` are scrubbed to `[ANONYMIZED_CUSTOMER]`.
  - **Accounting Exception**: Aggregate transaction totals and timestamps are retained in anonymized format solely to comply with statutory accounting, tax, and dispute resolution retention requirements (e.g. Companies Act / GST auditing rules).

---

## 3. Autonomous Agent Decisioning & Liability Framing

### 3.1 Probabilistic Models vs. Deterministic Policy Gates
The platform employs large language models (LLMs) via Anthropic, OpenAI, or Google Gemini for:
1. **Conversational Intent Translation**: Parsing unstructured shopper requests into catalog product candidates.
2. **Upsell & Cross-Sell Suggestions**: Heuristic and contextual product recommendations.
3. **Autonomous Growth Campaigns**: Segmenting order patterns and proposing targeted discounts or nudges.

> [!IMPORTANT]
> **Policy Before Payment**:
> LLM outputs are treated as untrusted suggestions. Every money-moving path is deterministically gated by `PolicyEngine.evaluate()` and `check_policy_node` in code:
> - **Max Amount Ceiling**: Checkout requests exceeding `policy.max_amount` are blocked with HTTP 403.
> - **Discount Safety Rail**: Campaign discounts cannot exceed `policy.max_discount_pct` (strictly capped between 0% and 50%).
> - **Category Filtering**: Products outside `policy.allowed_categories` are automatically denied.
> - **Idempotency Protection**: `Idempotency-Key` guarantees that network retries never produce duplicate charges.

### 3.2 Allocation of Responsibility
- **Merchant Responsibility**: The merchant is solely responsible for defining accurate guardrails (`max_amount`, `allowed_categories`, `per_user_limit`, and `max_discount_pct`) reflecting their operational risk tolerance.
- **Platform Disclaimers**: The software is provided "as is" without warranty of any kind. Operators must conduct end-to-end integration testing against their own Razorpay test dashboard before enabling agent access.

---

## 4. Dashboard Disclaimers & Operator Consent

All operators accessing the Next.js merchant dashboard are presented with the persistent `ComplianceBanner` component informing them that:
1. Transactions operate in simulated test mode.
2. External agents act autonomously based on LLM interpretation.
3. Policies must be actively maintained to constrain agent operations.
