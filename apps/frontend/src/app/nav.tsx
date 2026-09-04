"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState, type FormEvent } from "react";
import { useMerchant } from "../lib/merchant-context";

function shortId(id: string): string {
  return id.length > 8 ? `${id.slice(0, 8)}…` : id;
}

export function Nav() {
  const { merchantId, setMerchantId, merchantName, setAgentApiKey } = useMerchant();
  const [switchValue, setSwitchValue] = useState("");
  const pathname = usePathname();

  function isActive(href: string): boolean {
    return pathname === href || (href !== "/" && pathname.startsWith(href));
  }

  function handleSwitch(e: FormEvent) {
    e.preventDefault();
    const trimmed = switchValue.trim();
    if (!trimmed) return;
    setMerchantId(trimmed);
    setAgentApiKey(null); // held key belonged to the old merchant
    setSwitchValue("");
  }

  function handleForget() {
    setMerchantId(null);
    setAgentApiKey(null);
  }

  return (
    <nav className="nav">
      <Link className="nav-brand" href="/">
        <span className="nav-brand-icon">◆</span>
        Agentic Merchant
      </Link>

      <div className="nav-links">
        <Link className={`nav-link ${isActive("/onboarding") ? "active" : ""}`} href="/onboarding">
          Onboarding
        </Link>
        <Link className={`nav-link ${isActive("/catalog") ? "active" : ""}`} href="/catalog">
          Catalog
        </Link>
        <Link className={`nav-link ${isActive("/policies") ? "active" : ""}`} href="/policies">
          Policies
        </Link>
        <Link className={`nav-link ${isActive("/chat-checkout") ? "active" : ""}`} href="/chat-checkout">
          Chat Checkout
        </Link>
        <Link className={`nav-link ${isActive("/observability") ? "active" : ""}`} href="/observability">
          Observability
        </Link>
      </div>

      <div className="nav-merchant">
        {merchantId ? (
          <>
            <span className="merchant-pill" title={merchantId}>
              <span className="dot" />
              {merchantName === undefined ? "Loading…" : merchantName ?? shortId(merchantId)}
            </span>
            <button type="button" className="btn-danger" onClick={handleForget}>
              Forget
            </button>
          </>
        ) : (
          <span className="merchant-pill-empty">No merchant selected</span>
        )}

        <form className="switch-form" onSubmit={handleSwitch}>
          <input
            type="text"
            className="switch-input"
            placeholder="switch to merchant_id..."
            value={switchValue}
            onChange={(e) => setSwitchValue(e.target.value)}
          />
          <button type="submit" className="btn-secondary" disabled={!switchValue.trim()}>
            Switch
          </button>
        </form>
      </div>
    </nav>
  );
}
