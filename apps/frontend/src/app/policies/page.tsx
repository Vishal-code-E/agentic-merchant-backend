"use client";

import { useEffect, useState, type FormEvent } from "react";
import type { Policy, PolicyUpdate } from "@agentic-merchant/shared-types";
import { apiGet, apiPatch, ApiError } from "../../lib/api";
import { useMerchant } from "../../lib/merchant-context";

interface FormState {
  maxAmount: string;
  allowedCategories: string;
  perUserLimit: string;
}

function toForm(policy: Policy): FormState {
  return {
    maxAmount: policy.maxAmount != null ? String(policy.maxAmount) : "",
    allowedCategories: policy.allowedCategories.join(", "),
    perUserLimit: policy.perUserLimit != null ? String(policy.perUserLimit) : "",
  };
}

export default function PoliciesPage() {
  const { merchantId } = useMerchant();
  const [policy, setPolicy] = useState<Policy | null>(null);
  const [form, setForm] = useState<FormState | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (!merchantId) {
      setPolicy(null);
      setForm(null);
      return;
    }

    // Guard against out-of-order responses: switching merchants fires a new
    // fetch before the previous one necessarily resolves, and without this a
    // slower, stale response can overwrite fresher state.
    let cancelled = false;
    setLoading(true);
    setError(null);
    apiGet<Policy>(`/merchant/${merchantId}/policy`)
      .then((data) => {
        if (cancelled) return;
        setPolicy(data);
        setForm(toForm(data));
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof ApiError ? err.message : "Failed to load policy.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [merchantId]);

  function update<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((prev) => (prev ? { ...prev, [key]: value } : prev));
    setSaved(false);
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!merchantId || !form) return;
    setError(null);
    setSaving(true);
    setSaved(false);

    const payload: PolicyUpdate = {
      maxAmount: form.maxAmount ? Number(form.maxAmount) : undefined,
      allowedCategories: form.allowedCategories
        .split(",")
        .map((c) => c.trim())
        .filter(Boolean),
      perUserLimit: form.perUserLimit ? Number(form.perUserLimit) : undefined,
    };

    try {
      const updated = await apiPatch<Policy>(`/merchant/${merchantId}/policy`, payload);
      setPolicy(updated);
      setForm(toForm(updated));
      setSaved(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to update policy.");
    } finally {
      setSaving(false);
    }
  }

  if (!merchantId) {
    return (
      <main className="container">
        <header className="page-header">
          <h1>Policies</h1>
        </header>
        <div className="banner banner-warning">
          No merchant selected. Go to <a href="/onboarding">Onboarding</a> first.
        </div>
      </main>
    );
  }

  return (
    <main className="container">
      <header className="page-header">
        <h1>Policies</h1>
        <p className="page-subtitle">
          Guardrails for merchant <code>{merchantId}</code>. Every checkout is evaluated against
          these before any Razorpay call.
        </p>
      </header>

      {error && <div className="banner banner-error">{error}</div>}
      {saved && <div className="banner banner-success">Policy updated.</div>}

      {loading && (
        <div className="card">
          <div className="skeleton-row">
            <div className="skeleton" />
            <div className="skeleton" />
            <div className="skeleton" />
          </div>
        </div>
      )}

      {!loading && form && policy && (
        <form className="card" onSubmit={handleSubmit}>
          <div className="form-row">
            <div className="field">
              <label htmlFor="maxAmount">Max amount per checkout</label>
              <input
                id="maxAmount"
                type="number"
                min="0"
                step="0.01"
                value={form.maxAmount}
                onChange={(e) => update("maxAmount", e.target.value)}
              />
            </div>
            <div className="field">
              <label htmlFor="perUserLimit">Per-user limit</label>
              <input
                id="perUserLimit"
                type="number"
                min="0"
                step="0.01"
                value={form.perUserLimit}
                onChange={(e) => update("perUserLimit", e.target.value)}
              />
              <span className="hint">Leave blank for no per-user limit.</span>
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

          <button className="btn" type="submit" disabled={saving}>
            {saving ? "Saving…" : "Save policy"}
          </button>
        </form>
      )}
    </main>
  );
}
