/**
 * Shared types between apps/frontend and apps/backend.
 *
 * These mirror the SQLAlchemy models in apps/backend/app/models/*.py and the
 * request/response shapes of the /agent/* endpoints. Keep both sides in sync
 * manually for now; a future task can generate these from the FastAPI
 * OpenAPI schema instead (see docs/03-dev-handoff-architecture-lld.md §6).
 */

export type MerchantStatus = "pending" | "active" | "disabled";

// snake_case: MerchantResponse has no camelCase alias generator (see OnboardMerchantRequest note below).
export interface Merchant {
  id: string;
  name: string;
  razorpay_key_id: string | null;
  status: MerchantStatus;
}

export interface Product {
  id: string;
  merchantId: string;
  name: string;
  description: string | null;
  price: number;
  currency: string;
  category: string | null;
  tags: string[];
  stock: number;
}

export type OrderStatus = "pending" | "success" | "failed";

export interface Order {
  id: string;
  merchantId: string;
  razorpayOrderId: string | null;
  status: OrderStatus;
  amount: number;
  currency: string;
}

export interface Policy {
  id: string;
  merchantId: string;
  maxAmount: number | null;
  allowedCategories: string[];
  perUserLimit: number | null;
  maxDiscountPct: number;
}

/** Request body for PATCH /merchant/{merchantId}/policy — partial update. */
export interface PolicyUpdate {
  maxAmount?: number;
  allowedCategories?: string[];
  perUserLimit?: number;
  maxDiscountPct?: number;
}

/**
 * Request body for POST /merchant/onboarding/keys.
 * NOTE: this endpoint is snake_case on the wire — unlike /agent/* and the
 * policy endpoints, OnboardMerchantRequest/MerchantResponse have no camelCase
 * alias generator. See docs/03-dev-handoff-architecture-lld.md (casing drift,
 * left as known tech debt).
 */
export interface OnboardMerchantRequest {
  name: string;
  razorpay_key_id: string;
  razorpay_key_secret: string;
  max_amount: number;
  allowed_categories: string[];
  per_user_limit?: number | null;
  max_discount_pct?: number;
}

export interface DeactivateMerchantRequest {
  reason?: string;
  anonymizeAuditLogs?: boolean;
}

export interface DeactivateMerchantResponse {
  merchantId: string;
  status: MerchantStatus;
  deactivatedAt: string;
  retainedRecords: {
    auditLogs: number;
    orders: number;
  };
  notice: string;
}

export interface OnboardMerchantResponse {
  merchant: Merchant;
  policy: Policy;
  keys_valid: boolean;
  /**
   * Plaintext agent API key — present in this response ONLY. It is never
   * returned again by any endpoint (only its hash is stored server-side);
   * losing it means re-onboarding for a new one. See AgentAuthHeader.
   */
  api_key: string;
}

/**
 * Response for POST /merchant/{merchant_id}/api-key/regenerate. Invalidates
 * the merchant's previous key immediately; same one-time-display contract as
 * OnboardMerchantResponse.api_key.
 */
export interface RegenerateApiKeyResponse {
  merchant_id: string;
  api_key: string;
}

/**
 * Required on every /agent/* call (GET /agent/catalog, POST /agent/checkout).
 * Value is OnboardMerchantResponse.api_key. A missing/invalid key gets a 401.
 */
export interface AgentAuthHeader {
  "X-Agent-Api-Key": string;
}

/**
 * Required in addition to AgentAuthHeader on POST /agent/checkout. A
 * caller-generated unique string per checkout attempt — retrying with the
 * same key returns the original order instead of creating a duplicate. A
 * missing header gets a 400.
 */
export interface IdempotencyHeader {
  "Idempotency-Key": string;
}

export type AgentRunType = "checkout" | "campaign";
export type AgentRunStatus = "running" | "success" | "failed";

export interface AgentRun {
  id: string;
  merchantId: string;
  type: AgentRunType;
  status: AgentRunStatus;
  langfuseTraceId: string | null;
  startedAt: string | null;
  endedAt: string | null;
}

export interface AuditLogEntry {
  id: string;
  agentRunId: string;
  eventType: string;
  payload: Record<string, unknown>;
  createdAt: string;
}

/**
 * Request body for POST /agent/checkout. The request also requires the
 * headers in AgentAuthHeader and IdempotencyHeader — neither is part of
 * this body shape, but both are required on every call.
 */
export interface CheckoutCartItem {
  productId: string;
  quantity: number;
}

export interface CheckoutRequest {
  merchantId: string;
  cartItems: CheckoutCartItem[];
  customerContext?: Record<string, unknown>;
}

export interface CheckoutResponse {
  status: OrderStatus;
  razorpayOrderId: string | null;
  amount: number;
  currency: string;
  upsellSuggestions: Product[];
  explanation: string;
}

/**
 * Request body for POST /agent/chat-checkout. Same auth header as
 * CheckoutRequest (AgentAuthHeader); Idempotency-Key is accepted but
 * optional here — omitting it means the server generates one per call, so a
 * retried message is NOT idempotent unless the caller supplies its own key.
 */
export interface ChatCheckoutRequest {
  message: string;
  merchantId: string;
  customerContext?: Record<string, unknown>;
}

export interface ChatCheckoutResponse {
  /** One-line human-readable interpretation of the message (or why it didn't match). */
  interpretation: string;
  /** Same shape as CheckoutResponse from POST /agent/checkout; null when matched is false. */
  checkoutResult: CheckoutResponse | null;
  /** False when no confident in-catalog match was found — a 200, not an error. */
  matched: boolean;
}

/** Request body for POST /internal/campaigns/run (dashboard-triggered, not agent-facing). */
export interface CampaignRunRequest {
  merchantId: string;
  windowHours?: number;
}

/**
 * Recommendation source — see docs/ARCHITECTURE.md's Growth Agent section.
 * Values are snake_case on the wire: Pydantic's camelCase alias_generator
 * renames field keys, not string literal values.
 */
export type CampaignActionPath = "llm_reasoning" | "rule_based_fallback";

/** One action that survived ApplyPolicy — order-level, expanded from a segment-level LLM/fallback recommendation. */
export interface CampaignActionResult {
  orderId: string;
  segment: string;
  action: string;
  amount: number;
  currency: string;
  /** Why this action was recommended — the explainability string, same role as ChatCheckoutResponse.interpretation. */
  reasoning: string;
  confidence: number;
  /** 0-30, or null for actions that don't involve a discount (e.g. price_alert). */
  suggestedDiscountPct: number | null;
  path: CampaignActionPath;
}

export interface CampaignRunResponse {
  actions: CampaignActionResult[];
}
