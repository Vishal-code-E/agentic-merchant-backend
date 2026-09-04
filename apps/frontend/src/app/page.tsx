import Link from "next/link";

interface FlowStep {
  number: string;
  title: string;
  description: string;
  href: string;
  cta: string;
  primary?: boolean;
}

const FLOW: FlowStep[] = [
  {
    number: "01",
    title: "Onboarding",
    description:
      "Connect a merchant's Razorpay test-mode keys and set its spending guardrails. This mints the merchant_id and agent API key everything below uses.",
    href: "/onboarding",
    cta: "Start onboarding",
    primary: true,
  },
  {
    number: "02",
    title: "Catalog",
    description:
      "Add products to sell. This is the exact list an agent's GET /agent/catalog call will see.",
    href: "/catalog",
    cta: "Open catalog",
  },
  {
    number: "03",
    title: "Policies",
    description:
      "Set the spending ceiling, per-user limit, and allowed categories every checkout is checked against before it can pay.",
    href: "/policies",
    cta: "Adjust policies",
  },
  {
    number: "04",
    title: "Chat Checkout",
    description:
      "Type a plain-English order and watch it turn into a real, policy-checked cart — no structured JSON required. The most demo-worthy part of this whole thing.",
    href: "/chat-checkout",
    cta: "Try chat checkout",
  },
  {
    number: "05",
    title: "Observability",
    description:
      "Watch agent runs land in real time, and open any run's audit trail to see exactly why it was approved or denied.",
    href: "/observability",
    cta: "View activity",
  },
];

export default function Home() {
  return (
    <main className="container">
      <section className="hero">
        <h1>A store an AI shopping agent can actually buy from.</h1>
        <p>
          This backend gives a Razorpay merchant an agent-readable catalog, a policy-gated
          checkout, and a full audit trail — everything an autonomous buyer needs to browse,
          transact, and be trusted.
        </p>
        <div className="hero-actions">
          <Link className="btn" href="/onboarding">
            Start onboarding
          </Link>
          <a className="link-quiet" href="#how-it-works">
            How this works ↓
          </a>
        </div>
      </section>

      <section>
        <p className="section-label">The flow</p>
        <p className="section-intro">
          Each step hands the next one what it needs — walk them in order the first time.
        </p>

        <div className="flow">
          {FLOW.map((step) => (
            <div className="flow-step" key={step.number}>
              <span className="flow-step-number">{step.number}</span>
              <div className="flow-step-body">
                <h3>{step.title}</h3>
                <p>{step.description}</p>
              </div>
              <div className="flow-step-action">
                <Link className={step.primary ? "btn" : "btn-secondary"} href={step.href}>
                  {step.cta}
                </Link>
              </div>
            </div>
          ))}
        </div>
      </section>

      <section id="how-it-works" className="about">
        <h2>How this works</h2>
        <p>
          Every onboarded merchant gets a machine-readable product catalog an agent can query
          directly — no scraping, no guessing at what&apos;s in stock. A checkout only clears
          after it&apos;s checked against that merchant&apos;s own spending ceiling, per-user
          limit, and category rules, so an agent can&apos;t spend past what the merchant allowed.
        </p>
        <p>
          Every request, policy decision, and Razorpay call is written to an audit trail tied to
          a traceable run, so any approved or denied checkout can be explained after the fact.
          It&apos;s the same trust boundary a human checkout enforces, built for a caller you
          can&apos;t ask &ldquo;are you sure?&rdquo;
        </p>
      </section>
    </main>
  );
}
