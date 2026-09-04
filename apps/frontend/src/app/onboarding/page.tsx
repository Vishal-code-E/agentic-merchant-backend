"use client";

import { useState, type FormEvent } from "react";
import type { OnboardMerchantRequest, OnboardMerchantResponse } from "@agentic-merchant/shared-types";
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

export default function OnboardingPage() {
  const { setMerchantId } = useMerchant();
  const [form, setForm] = useState<FormState>(initialForm);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<OnboardMerchantResponse | null>(null);
  const [copied, setCopied] = useState(false);

  function update<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  async function handleCopyApiKey() {
    if (!result) return;
    try {
      await navigator.clipboard.writeText(result.api_key);
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
      setMerchantId(response.merchant.id);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Is the backend running?");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="container">
      <h1>Onboarding</h1>
      <p className="muted">
        Connect a merchant's Razorpay test-mode keys and set its initial policy. A merchant cannot
        exist without a policy — both are created together.
      </p>

      {error && <div className="banner banner-error">{error}</div>}

      {result && (
        <>
          <div className="banner banner-success">
            <strong>Merchant onboarded.</strong> merchant_id:{" "}
            <code>{result.merchant.id}</code> is now the active merchant for the rest of this
            dashboard.
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
              <code>/agent/checkout</code> calls. If you lose it, the only way to get a new one is
              to re-onboard this merchant.
            </div>
            <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <code
                style={{
                  flex: 1,
                  padding: "8px 10px",
                  background: "var(--color-surface)",
                  border: "1px solid var(--color-warning-border)",
                  borderRadius: 6,
                  userSelect: "all",
                  wordBreak: "break-all",
                }}
              >
                {result.api_key}
              </code>
              <button type="button" className="btn-secondary" onClick={handleCopyApiKey}>
                {copied ? "Copied!" : "Copy"}
              </button>
            </div>
          </div>
        </>
      )}

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
          {submitting ? "Onboarding..." : "Onboard merchant"}
        </button>
      </form>
    </main>
  );
}
