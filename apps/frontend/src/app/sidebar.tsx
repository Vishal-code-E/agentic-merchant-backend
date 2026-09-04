"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { useMerchant } from "../lib/merchant-context";

function shortId(id: string): string {
  return id.length > 8 ? `${id.slice(0, 8)}…` : id;
}

const LINKS = [
  { href: "/catalog", label: "Catalog" },
  { href: "/policies", label: "Policies" },
  { href: "/growth", label: "Growth" },
  { href: "/observability", label: "Observability" },
];

export function Sidebar() {
  const { merchantId, setMerchantId, merchantName, setAgentApiKey } = useMerchant();
  const [switchValue, setSwitchValue] = useState("");
  const pathname = usePathname();
  const router = useRouter();

  function isActive(href: string): boolean {
    return pathname === href || pathname.startsWith(`${href}/`);
  }

  function handleSwitch(e: FormEvent) {
    e.preventDefault();
    const trimmed = switchValue.trim();
    if (!trimmed) return;
    setMerchantId(trimmed);
    setAgentApiKey(null); // held key belonged to the old merchant
    setSwitchValue("");
    router.push("/");
  }

  function handleOnboardDifferent() {
    setMerchantId(null);
    setAgentApiKey(null);
    router.push("/onboarding");
  }

  return (
    <aside className="sidebar">
      <Link className="sidebar-brand" href="/">
        <span className="sidebar-brand-icon">◆</span>
        Agentic Merchant
      </Link>

      <div className="sidebar-merchant">
        {merchantId ? (
          <span className="merchant-pill" title={merchantId}>
            <span className="dot" />
            {merchantName === undefined ? "Loading…" : merchantName ?? shortId(merchantId)}
          </span>
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

      <nav className="sidebar-nav">
        {LINKS.map((link) => (
          <Link
            key={link.href}
            className={`sidebar-link ${isActive(link.href) ? "active" : ""}`}
            href={link.href}
          >
            {link.label}
          </Link>
        ))}
      </nav>

      <button type="button" className="sidebar-signout" onClick={handleOnboardDifferent}>
        Onboard a different merchant
      </button>
    </aside>
  );
}
