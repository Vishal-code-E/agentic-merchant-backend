"use client";

/**
 * Holds the "currently active merchant_id" so the catalog/policies/observability
 * pages don't each need it re-entered.
 *
 * Persisted to localStorage (not just React state): a full page refresh —
 * common during local testing — would otherwise silently drop the active
 * merchant and make it look like re-onboarding is required. Read lazily via
 * useEffect rather than a useState initializer so the server-rendered and
 * first client-rendered pass still match (localStorage isn't available
 * during SSR) — this costs one render with merchantId=null right after
 * mount, before the stored value (if any) is applied.
 */

import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

interface MerchantContextValue {
  merchantId: string | null;
  setMerchantId: (id: string | null) => void;
}

const MerchantContext = createContext<MerchantContextValue | undefined>(undefined);

const STORAGE_KEY = "agentic-merchant:active-merchant-id";

export function MerchantProvider({ children }: { children: ReactNode }) {
  const [merchantId, setMerchantIdState] = useState<string | null>(null);

  useEffect(() => {
    try {
      const stored = window.localStorage.getItem(STORAGE_KEY);
      if (stored) {
        setMerchantIdState(stored);
      }
    } catch {
      // localStorage unavailable (private browsing, disabled, etc.) — fall back to unset.
    }
  }, []);

  function setMerchantId(id: string | null) {
    setMerchantIdState(id);
    try {
      if (id) {
        window.localStorage.setItem(STORAGE_KEY, id);
      } else {
        window.localStorage.removeItem(STORAGE_KEY);
      }
    } catch {
      // localStorage unavailable — the active merchant just won't survive a refresh.
    }
  }

  return (
    <MerchantContext.Provider value={{ merchantId, setMerchantId }}>
      {children}
    </MerchantContext.Provider>
  );
}

export function useMerchant(): MerchantContextValue {
  const ctx = useContext(MerchantContext);
  if (!ctx) {
    throw new Error("useMerchant() must be used within a <MerchantProvider>");
  }
  return ctx;
}
