"use client";

import { useState } from "react";
import Link from "next/link";

export function ComplianceBanner() {
  const [dismissed, setDismissed] = useState(false);

  if (dismissed) return null;

  return (
    <div
      className="banner banner-warning"
      style={{
        display: "flex",
        alignItems: "flex-start",
        justifyContent: "space-between",
        gap: "1rem",
        margin: "1rem 2rem 0 2rem",
        padding: "0.85rem 1.25rem",
        borderLeft: "4px solid #b7791f",
      }}
      role="region"
      aria-label="Compliance and autonomous agent disclaimer"
    >
      <div style={{ fontSize: "0.875rem", lineHeight: "1.5" }}>
        <strong>⚖️ Razorpay Test-Mode &amp; Autonomous Agent Notice: </strong>
        <span>
          This platform operates strictly against Razorpay test-mode APIs with simulated funds.
          External AI agents autonomously interpret customer intent and propose checkout transactions.
          Merchants remain solely responsible for configuring deterministic financial guardrails (spending ceilings,
          discount caps, and permitted categories) under{" "}
          <Link href="/policies" style={{ textDecoration: "underline", fontWeight: 600 }}>
            Policies
          </Link>{" "}
          and ensuring compliance prior to live-mode deployment.
        </span>
      </div>
      <button
        type="button"
        onClick={() => setDismissed(true)}
        style={{
          background: "none",
          border: "none",
          cursor: "pointer",
          fontSize: "1.1rem",
          color: "#744210",
          padding: "0 0.25rem",
          lineHeight: 1,
        }}
        title="Dismiss notice"
        aria-label="Dismiss compliance notice"
      >
        ×
      </button>
    </div>
  );
}
