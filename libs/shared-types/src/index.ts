/**
 * Shared types between apps/frontend and apps/backend.
 *
 * These mirror the SQLAlchemy models in apps/backend/app/models/*.py and the
 * request/response shapes of the /agent/* endpoints. Keep both sides in sync
 * manually for now; a future task can generate these from the FastAPI
 * OpenAPI schema instead (see docs/03-dev-handoff-architecture-lld.md §6).
 */

export type MerchantStatus = "pending" | "active" | "disabled";

export interface Merchant {
  id: string;
  name: string;
  razorpayKeyId: string | null;
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

/** Request body for POST /agent/checkout */
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
