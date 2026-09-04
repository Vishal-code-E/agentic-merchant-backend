"use client";

import { useEffect, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import type {
  OnboardMerchantRequest,
  OnboardMerchantResponse,
  RegenerateApiKeyResponse,
} from "@agentic-merchant/shared-types";
import { apiPost, ApiError } from "../../lib/api";
import { useMerchant } from "../../lib/merchant-context";

interface FormState {
  name: string;
  razorpayKeyId: string;
  razorpayKeySecret: string;
  maxAmount: string;
  allowedCategories: string;
  perUserLimit: string;
}

const initialForm: FormState = {
  name: "",
  razorpayKeyId: "",
  razorpayKeySecret: "",
  maxAmount: "",
  allowedCategories: "",
  perUserLimit: "",
};

interface FlowStep {
  number: string;
  title: string;
  description: string;
}

const FLOW: FlowStep[] = [
  {
    number: "01",
    title: "Catalog",
    description: "Add products to sell — the exact list an agent's GET /agent/catalog call will see.",
  },
  {
    number: "02",
    title: "Policies",
    description:
      "Set the spending ceiling, per-user limit, and allowed categories every checkout is checked against.",
  },
  {
    number: "03",
    title: "Chat",
    description:
      "Type a plain-English order and watch it turn into a real, policy-checked cart — no structured JSON required.",
  },
  {
    number: "04",
    title: "Growth",
    description:
      "An AI reasons over your recent orders and real catalog to recommend retry nudges, loyalty offers, and upsells — and explains why, every time.",
  },
  {
    number: "05",
    title: "Observability",
    description: "Watch agent runs land in real time, and open any run's audit trail to see why.",
  },
];

const REDIRECT_DELAY_MS = 5000;

// Local dev convenience only, from .env.local (gitignored) — never a live key.
const TEST_RAZORPAY_KEY_ID = process.env.NEXT_PUBLIC_TEST_RAZORPAY_KEY_ID;
const TEST_RAZORPAY_KEY_SECRET = process.env.NEXT_PUBLIC_TEST_RAZORPAY_KEY_SECRET;

export default function OnboardingPage() {
  const { setMerchantId, setAgentApiKey } = useMerchant();
  const router = useRouter();
  const [form, setForm] = useState<FormState>(initialForm);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<OnboardMerchantResponse | null>(null);
  const [apiKey, setApiKey] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [confirmingRegenerate, setConfirmingRegenerate] = useState(false);
  const [regenerating, setRegenerating] = useState(false);
  const [regenerateError, setRegenerateError] = useState<string | null>(null);

  // Give the user a window to copy the one-time API key before leaving this page.
  useEffect(() => {
    if (!result) return;
    const timer = setTimeout(() => router.push("/"), REDIRECT_DELAY_MS);
    return () => clearTimeout(timer);
  }, [result, router]);

  function update<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  async function handleCopyApiKey() {
    if (!apiKey) return;
    try {
      await navigator.clipboard.writeText(apiKey);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard API unavailable (non-secure context, permission denied, etc.) —
      // the key below is still selectable text, so this is a soft failure.
    }
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setCopied(false);
    setSubmitting(true);

    const payload: OnboardMerchantRequest = {
      name: form.name,
      razorpay_key_id: form.razorpayKeyId,
      razorpay_key_secret: form.razorpayKeySecret,
      max_amount: Number(form.maxAmount),
      allowed_categories: form.allowedCategories
        .split(",")
        .map((c) => c.trim())
        .filter(Boolean),
      per_user_limit: form.perUserLimit ? Number(form.perUserLimit) : null,
    };

    try {
      const response = await apiPost<OnboardMerchantResponse>("/merchant/onboarding/keys", payload);
      setResult(response);
      setApiKey(response.api_key);
      setMerchantId(response.merchant.id);
      setAgentApiKey(response.api_key); // makes chat usable right away, same session
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Is the backend running?");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleRegenerate() {
    if (!result) return;
    setRegenerateError(null);
    setRegenerating(true);
    try {
      const response = await apiPost<RegenerateApiKeyResponse>(
        `/merchant/${result.merchant.id}/api-key/regenerate`,
        {}
      );
      setApiKey(response.api_key);
      setAgentApiKey(response.api_key);
      setCopied(false);
      setConfirmingRegenerate(false);
    } catch (err) {
      setRegenerateError(err instanceof ApiError ? err.message : "Failed to regenerate the API key.");
    } finally {
      setRegenerating(false);
    }
  }

  return (
    <main className="container">
      {!result && (
        <>
          <section className="hero">
            <h1>A store an AI shopping agent can actually buy from.</h1>
            <p>
              This backend gives a Razorpay merchant an agent-readable catalog, a policy-gated
              checkout, and a full audit trail — everything an autonomous buyer needs to browse,
              transact, and be trusted.
            </p>
          </section>

          <section>
            <p className="section-label">The flow</p>
            <p className="section-intro">
              Onboarding below mints the merchant_id and agent API key everything after it uses.
            </p>

            <div className="flow">
              {FLOW.map((step) => (
                <div className="flow-step" key={step.number}>
                  <span className="flow-step-number">{step.number}</span>
                  <div className="flow-step-body">
                    <h3>{step.title}</h3>
                    <p>{step.description}</p>
                  </div>
                </div>
              ))}
            </div>
          </section>

          <section className="about">
            <h2>How this works</h2>
            <p>
              Every onboarded merchant gets a machine-readable product catalog an agent can query
              directly — no scraping, no guessing at what&apos;s in stock. A checkout only clears
              after it&apos;s checked against that merchant&apos;s own spending ceiling, per-user
              limit, and category rules, so an agent can&apos;t spend past what the merchant
              allowed.
            </p>
            <p>
              Every request, policy decision, and Razorpay call is written to an audit trail tied
              to a traceable run, so any approved or denied checkout can be explained after the
              fact. It&apos;s the same trust boundary a human checkout enforces, built for a caller
              you can&apos;t ask &ldquo;are you sure?&rdquo;
            </p>
          </section>
        </>
      )}

      <header className="page-header">
        <h1>Onboarding</h1>
        <p className="page-subtitle">
          Connect a merchant&apos;s Razorpay test-mode keys and set its initial policy. A
          merchant cannot exist without a policy — both are created together.
        </p>
      </header>

      {error && <div className="banner banner-error">{error}</div>}

      {result && (
        <>
          <div className="banner banner-success">
            <strong>Merchant onboarded.</strong> merchant_id:{" "}
            <code>{result.merchant.id}</code> is now the active merchant.
            {!result.keys_valid && (
              <div style={{ marginTop: 4 }}>
                Note: Razorpay key validation failed — the merchant was created with status{" "}
                <code>{result.merchant.status}</code>.
              </div>
            )}
          </div>

          <div className="banner banner-warning">
            <strong>Copy this API key now — it will not be shown again.</strong>
            <div className="hint" style={{ marginTop: 4, marginBottom: 8 }}>
              Send it as the <code>X-Agent-Api-Key</code> header on <code>/agent/catalog</code> and{" "}
              <code>/agent/checkout</code> calls. If you lose it, regenerate a new one below —
              that immediately invalidates this one.
            </div>
            <div className="api-key-box">
              <code className="api-key-value">{apiKey}</code>
              <button type="button" className="btn-secondary" onClick={handleCopyApiKey}>
                {copied ? "Copied!" : "Copy"}
              </button>
            </div>

            <div style={{ marginTop: 12, paddingTop: 12, borderTop: "1px solid var(--color-warning-border)" }}>
              {!confirmingRegenerate ? (
                <button
                  type="button"
                  className="btn-secondary"
                  onClick={() => setConfirmingRegenerate(true)}
                >
                  Regenerate API key
                </button>
              ) : (
                <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                  <span className="hint">
                    This immediately invalidates the key above. Anything still using it gets 401.
                  </span>
                  <button
                    type="button"
                    className="btn-danger"
                    onClick={handleRegenerate}
                    disabled={regenerating}
                  >
                    {regenerating ? "Regenerating…" : "Confirm regenerate"}
                  </button>
                  <button
                    type="button"
                    className="btn-secondary"
                    onClick={() => setConfirmingRegenerate(false)}
                    disabled={regenerating}
                  >
                    Cancel
                  </button>
                </div>
              )}
              {regenerateError && (
                <div className="banner banner-error" style={{ marginTop: 8 }}>
                  {regenerateError}
                </div>
              )}
            </div>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <button type="button" className="btn" onClick={() => router.push("/")}>
              Continue to chat →
            </button>
            <span className="hint">Redirecting automatically in a few seconds…</span>
          </div>
        </>
      )}

      {!result && (
        <form className="card" onSubmit={handleSubmit}>
          <div className="field">
            <label htmlFor="name">Merchant name</label>
            <input
              id="name"
              required
              value={form.name}
              onChange={(e) => update("name", e.target.value)}
            />
          </div>

          <div className="form-row">
            <div className="field">
              <label htmlFor="keyId">Razorpay key ID</label>
              <input
                id="keyId"
                required
                value={form.razorpayKeyId}
                onChange={(e) => update("razorpayKeyId", e.target.value)}
              />
              {TEST_RAZORPAY_KEY_ID && (
                <span className="hint">Test mode key: {TEST_RAZORPAY_KEY_ID}</span>
              )}
            </div>
            <div className="field">
              <label htmlFor="keySecret">Razorpay key secret</label>
              <input
                id="keySecret"
                type="password"
                required
                value={form.razorpayKeySecret}
                onChange={(e) => update("razorpayKeySecret", e.target.value)}
              />
              {TEST_RAZORPAY_KEY_SECRET && (
                <span className="hint">Test mode secret: {TEST_RAZORPAY_KEY_SECRET}</span>
              )}
            </div>
          </div>

          <div className="form-row">
            <div className="field">
              <label htmlFor="maxAmount">Max amount per checkout</label>
              <input
                id="maxAmount"
                type="number"
                min="0"
                step="0.01"
                required
                value={form.maxAmount}
                onChange={(e) => update("maxAmount", e.target.value)}
              />
            </div>
            <div className="field">
              <label htmlFor="perUserLimit">Per-user limit (optional)</label>
              <input
                id="perUserLimit"
                type="number"
                min="0"
                step="0.01"
                value={form.perUserLimit}
                onChange={(e) => update("perUserLimit", e.target.value)}
              />
            </div>
          </div>

          <div className="field">
            <label htmlFor="categories">Allowed categories</label>
            <input
              id="categories"
              placeholder="electronics, books, apparel"
              value={form.allowedCategories}
              onChange={(e) => update("allowedCategories", e.target.value)}
            />
            <span className="hint">Comma-separated. Leave blank for no category restriction.</span>
          </div>

          <button className="btn" type="submit" disabled={submitting}>
            {submitting ? "Onboarding…" : "Onboard merchant"}
          </button>
        </form>
      )}
    </main>
  );
}
