import type { Merchant } from "@agentic-merchant/shared-types";

// Placeholder data shaped by the shared type — proves frontend/backend share
// a single source of truth for the Merchant contract. Real fetch wiring is v1.4.
const placeholderMerchant: Merchant = {
  id: "merchant_demo",
  name: "Demo Merchant",
  razorpayKeyId: null,
  status: "pending",
};

export default function Home() {
  return (
    <main style={{ padding: "2rem", fontFamily: "sans-serif" }}>
      <h1>Agentic Merchant Dashboard</h1>
      <p>Skeleton only. Pages to build: /onboarding, /catalog, /policies, /observability.</p>
      <p>
        Sample merchant (typed via <code>@agentic-merchant/shared-types</code>):{" "}
        {placeholderMerchant.name} — {placeholderMerchant.status}
      </p>
    </main>
  );
}
