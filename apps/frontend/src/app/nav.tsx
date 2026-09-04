"use client";

import Link from "next/link";
import { useState, type FormEvent } from "react";
import { useMerchant } from "../lib/merchant-context";

export function Nav() {
  const { merchantId, setMerchantId } = useMerchant();
  const [switchValue, setSwitchValue] = useState("");

  function handleSwitch(e: FormEvent) {
    e.preventDefault();
    const trimmed = switchValue.trim();
    if (!trimmed) return;
    setMerchantId(trimmed);
    setSwitchValue("");
  }

  return (
    <nav className="nav">
      <span className="nav-brand">Agentic Merchant</span>
      <Link className="nav-link" href="/onboarding">
        Onboarding
      </Link>
      <Link className="nav-link" href="/catalog">
        Catalog
      </Link>
      <Link className="nav-link" href="/policies">
        Policies
      </Link>
      <Link className="nav-link" href="/observability">
        Observability
      </Link>
      <span className="nav-merchant">
        {merchantId ? (
          <>
            active merchant: <code>{merchantId}</code>{" "}
            <button
              type="button"
              className="btn-danger"
              onClick={() => setMerchantId(null)}
            >
              Forget this merchant
            </button>
          </>
        ) : (
          "no merchant selected"
        )}{" "}
        <form
          onSubmit={handleSwitch}
          style={{ display: "inline-flex", gap: 4, alignItems: "center", marginLeft: 8 }}
        >
          <input
            type="text"
            placeholder="switch to merchant_id..."
            value={switchValue}
            onChange={(e) => setSwitchValue(e.target.value)}
            style={{ width: 220 }}
          />
          <button type="submit" className="btn-secondary" disabled={!switchValue.trim()}>
            Switch
          </button>
        </form>
      </span>
    </nav>
  );
}
