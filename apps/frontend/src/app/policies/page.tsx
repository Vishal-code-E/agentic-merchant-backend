"use client";

import { useEffect, useState, type FormEvent } from "react";
import type { Policy, PolicyUpdate } from "@agentic-merchant/shared-types";
import { apiGet, apiPatch, ApiError } from "../../lib/api";
import { useMerchant } from "../../lib/merchant-context";

interface FormState {
  maxAmount: string;
  allowedCategories: string;
  perUserLimit: string;
  maxDiscountPct: string;
}

function toForm(policy: Policy): FormState {
  return {
    maxAmount: policy.maxAmount != null ? String(policy.maxAmount) : "",
    allowedCategories: policy.allowedCategories.join(", "),
    perUserLimit: policy.perUserLimit != null ? String(policy.perUserLimit) : "",
    maxDiscountPct: policy.maxDiscountPct != null ? String(policy.maxDiscountPct) : "30",
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
    setError(null);
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!merchantId || !form) return;
    setError(null);

    // --- Client-side UX safety guardrails ---
    const maxAmt = form.maxAmount ? Number(form.maxAmount) : NaN;
    if (isNaN(maxAmt) || maxAmt <= 0) {
      setError("Max amount per checkout is required and must be greater than 0.");
      return;
    }

    const discount = form.maxDiscountPct ? Number(form.maxDiscountPct) : NaN;
    if (isNaN(discount) || discount < 0 || discount > 50) {
      setError("Max campaign discount must be between 0% and 50% to prevent runaway discount creation.");
      return;
    }

    const userLimit = form.perUserLimit ? Number(form.perUserLimit) : null;
    if (userLimit != null && userLimit > maxAmt) {
      setError(`Per-user limit (${userLimit}) cannot exceed max checkout ceiling (${maxAmt}).`);
      return;
    }

    setSaving(true);
    setSaved(false);

    const payload: PolicyUpdate = {
      maxAmount: maxAmt,
      allowedCategories: form.allowedCategories
        .split(",")
        .map((c) => c.trim())
        .filter(Boolean),
      perUserLimit: userLimit ?? undefined,
      maxDiscountPct: discount,
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
          Deterministic guardrails for merchant <code>{merchantId}</code>. Every checkout and growth recommendation
          is evaluated against these before any external payment or customer action.
        </p>
      </header>

      {error && <div className="banner banner-error">{error}</div>}
      {saved && <div className="banner banner-success">Policy successfully updated and active.</div>}

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
              <label htmlFor="maxAmount">
                Max amount per checkout <span style={{ color: "var(--color-danger)" }}>*</span>
              </label>
              <input
                id="maxAmount"
                type="number"
                min="0.01"
                step="0.01"
                required
                value={form.maxAmount}
                onChange={(e) => update("maxAmount", e.target.value)}
              />
              <span className="hint">Hard spending ceiling per checkout attempt. Required.</span>
            </div>
            <div className="field">
              <label htmlFor="perUserLimit">Per-user limit</label>
              <input
                id="perUserLimit"
                type="number"
                min="0.01"
                step="0.01"
                value={form.perUserLimit}
                onChange={(e) => update("perUserLimit", e.target.value)}
              />
              <span className="hint">Must be ≤ Max amount per checkout. Leave blank for no limit.</span>
            </div>
          </div>

          <div className="form-row">
            <div className="field">
              <label htmlFor="maxDiscountPct">
                Max campaign discount % <span style={{ color: "var(--color-danger)" }}>*</span>
              </label>
              <input
                id="maxDiscountPct"
                type="number"
                min="0"
                max="50"
                step="1"
                required
                value={form.maxDiscountPct}
                onChange={(e) => update("maxDiscountPct", e.target.value)}
              />
              <span className="hint">
                Hard ceiling (0–50%) for automated AI growth campaigns. Prevents runaway/infinite discounts.
              </span>
            </div>
            <div className="field">
              <label htmlFor="categories">Allowed categories</label>
              <input
                id="categories"
                placeholder="electronics, books, apparel"
                value={form.allowedCategories}
                onChange={(e) => update("allowedCategories", e.target.value)}
              />
              <span className="hint">Comma-separated. Leave blank to permit all categories.</span>
            </div>
          </div>

          <button className="btn" type="submit" disabled={saving}>
            {saving ? "Saving…" : "Save policy guardrails"}
          </button>
        </form>
      )}
    </main>
  );
}
