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

  function update<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
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
