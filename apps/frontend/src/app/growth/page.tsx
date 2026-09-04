"use client";

import { useState } from "react";
import type { CampaignActionResult, CampaignRunResponse } from "@agentic-merchant/shared-types";
import { apiPost, ApiError } from "../../lib/api";
import { useMerchant } from "../../lib/merchant-context";

interface Recommendation {
  action: string;
  segment: string;
  reasoning: string;
  confidence: number;
  suggestedDiscountPct: number | null;
  path: string;
  orderCount: number;
  totalAmount: number;
  currency: string;
}

const ACTION_LABELS: Record<string, string> = {
  retry_nudge: "Retry nudge",
  loyalty_offer: "Loyalty offer",
  upsell_campaign: "Upsell campaign",
  price_alert: "Price alert",
};

const SEGMENT_LABELS: Record<string, string> = {
  failed_payment_recent: "Recent failed payments",
  high_value_cart: "High-value carts",
};

// One growth_agent recommendation fans out to one action per order (see campaign_graph.py) —
// group back by (segment, action) so the page shows one card per recommendation, not per order.
function groupActions(actions: CampaignActionResult[]): Recommendation[] {
  const groups = new Map<string, Recommendation>();
  for (const a of actions) {
    const key = `${a.segment}::${a.action}`;
    const existing = groups.get(key);
    if (existing) {
      existing.orderCount += 1;
      existing.totalAmount += a.amount;
    } else {
      groups.set(key, {
        action: a.action,
        segment: a.segment,
        reasoning: a.reasoning,
        confidence: a.confidence,
        suggestedDiscountPct: a.suggestedDiscountPct,
        path: a.path,
        orderCount: 1,
        totalAmount: a.amount,
        currency: a.currency,
      });
    }
  }
  return Array.from(groups.values());
}

export default function GrowthPage() {
  const { merchantId } = useMerchant();
  const [recommendations, setRecommendations] = useState<Recommendation[] | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleRun() {
    if (!merchantId) return;
    setError(null);
    setRunning(true);
    try {
      const response = await apiPost<CampaignRunResponse>("/internal/campaigns/run", { merchantId });
      setRecommendations(groupActions(response.actions));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to run analysis.");
    } finally {
      setRunning(false);
    }
  }

  if (!merchantId) {
    return (
      <main className="container">
        <header className="page-header">
          <h1>Growth</h1>
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
        <h1>Growth</h1>
        <p className="page-subtitle">
          Segments your recent orders, then has an AI reason over your real catalog and policy
          to recommend what to do next. Every recommendation shown here already cleared the same
          policy check a checkout goes through.
        </p>
      </header>

      {error && <div className="banner banner-error">{error}</div>}

      <div className="card">
        <h2>Run analysis</h2>
        <p className="hint" style={{ marginBottom: 12 }}>
          Looks at orders from the last 24 hours.
        </p>
        <button className="btn" type="button" onClick={handleRun} disabled={running}>
          {running ? "Analysing…" : "Run analysis"}
        </button>

        {running && (
          <div className="empty-state">
            <div className="typing-indicator" style={{ alignSelf: "center" }}>
              <span className="dot" />
              <span className="dot" />
              <span className="dot" />
            </div>
            <p>Reasoning over your recent orders — this can take a few seconds.</p>
          </div>
        )}

        {!running && recommendations !== null && recommendations.length === 0 && (
          <div className="empty-state">
            <div className="empty-state-icon">🌱</div>
            <p>No actionable segments right now — nothing here needs your attention.</p>
          </div>
        )}
      </div>

      {!running &&
        recommendations?.map((rec) => (
          <div className="card" key={`${rec.segment}::${rec.action}`}>
            <div className="growth-card-header">
              <span className="badge badge-success">{ACTION_LABELS[rec.action] ?? rec.action}</span>
              <span className="muted">
                {SEGMENT_LABELS[rec.segment] ?? rec.segment} · {rec.orderCount} order
                {rec.orderCount === 1 ? "" : "s"} · {rec.totalAmount} {rec.currency}
              </span>
            </div>

            <p className="growth-card-reasoning">{rec.reasoning}</p>

            <div className="growth-card-footer">
              <span className="confidence-bar" title={`${Math.round(rec.confidence * 100)}% confidence`}>
                <span className="confidence-bar-fill" style={{ width: `${Math.round(rec.confidence * 100)}%` }} />
              </span>
              <span className="hint">{Math.round(rec.confidence * 100)}% confidence</span>
              {rec.suggestedDiscountPct != null && (
                <span className="badge badge-success">{rec.suggestedDiscountPct}% off suggested</span>
              )}
              <span className="hint">
                {rec.path === "llm_reasoning" ? "via LLM reasoning" : "via rule-based fallback"}
              </span>
            </div>
          </div>
        ))}
    </main>
  );
}
