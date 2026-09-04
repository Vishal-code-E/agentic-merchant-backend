import Link from "next/link";

export default function Home() {
  return (
    <main className="container">
      <h1>Agentic Merchant Dashboard</h1>
      <div className="card">
        <p>
          Start at <Link href="/onboarding">Onboarding</Link> to connect a merchant's Razorpay
          test-mode keys and set its policy — that gives you the <code>merchant_id</code> the rest
          of the dashboard uses.
        </p>
        <p className="muted">
          Then use <Link href="/catalog">Catalog</Link> to add products,{" "}
          <Link href="/policies">Policies</Link> to adjust guardrails, and{" "}
          <Link href="/observability">Observability</Link> to inspect agent runs and audit logs.
        </p>
      </div>
    </main>
  );
}
