"use client";

/**
 * Holds the "currently active merchant_id" so the catalog/policies/observability
 * pages don't each need it re-entered. Also resolves that id to the merchant's
 * name (for the sidebar pill — a raw UUID isn't a legible "who am I working on"
 * indicator) and caches it per id so switching back doesn't re-fetch.
 *
 * agentApiKey is deliberately plain React state, NOT persisted to localStorage:
 * it's a live bearer credential (X-Agent-Api-Key), unlike merchantId which is
 * not a secret. It's set once, right after onboarding or a regenerate call,
 * and is lost on refresh/new tab by design — see page.tsx's (the chat home)
 * "generate a fresh key" fallback for that case. Callers that switch/forget
 * the active merchant are responsible for clearing it themselves (see
 * sidebar.tsx) — this file doesn't auto-clear it on merchantId change, to
 * avoid wiping a key onboarding just set in the same update.
 *
 * merchantId is persisted to localStorage (not just React state): a full page
 * refresh — common during local testing — would otherwise silently drop the
 * active merchant and make it look like re-onboarding is required. Read
 * lazily via useEffect rather than a useState initializer so the
 * server-rendered and first client-rendered pass still match (localStorage
 * isn't available during SSR) — this costs one render with merchantId=null
 * right after mount, before the stored value (if any) is applied.
 */

import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { apiGet } from "./api";

interface MerchantContextValue {
  merchantId: string | null;
  setMerchantId: (id: string | null) => void;
  /** null = not fetched/no merchant; undefined = fetch in flight. */
  merchantName: string | null | undefined;
  /** In-memory only — see module docstring. null = none held this session. */
  agentApiKey: string | null;
  setAgentApiKey: (key: string | null) => void;
  /** True once the localStorage read has run — gates redirect guards so they don't fire on the pre-hydration null. */
  hydrated: boolean;
}

const MerchantContext = createContext<MerchantContextValue | undefined>(undefined);

const STORAGE_KEY = "agentic-merchant:active-merchant-id";

export function MerchantProvider({ children }: { children: ReactNode }) {
  const [merchantId, setMerchantIdState] = useState<string | null>(null);
  const [merchantName, setMerchantName] = useState<string | null | undefined>(null);
  const [agentApiKey, setAgentApiKey] = useState<string | null>(null);
  const [hydrated, setHydrated] = useState(false);
  const nameCache = useRef(new Map<string, string>());

  useEffect(() => {
    try {
      const stored = window.localStorage.getItem(STORAGE_KEY);
      if (stored) {
        setMerchantIdState(stored);
      }
    } catch {
      // localStorage unavailable (private browsing, disabled, etc.) — fall back to unset.
    }
    setHydrated(true);
  }, []);

  useEffect(() => {
    if (!merchantId) {
      setMerchantName(null);
      return;
    }

    const cached = nameCache.current.get(merchantId);
    if (cached) {
      setMerchantName(cached);
      return;
    }

    let cancelled = false;
    setMerchantName(undefined);
    apiGet<{ name: string }>(`/merchant/${merchantId}`)
      .then((merchant) => {
        if (cancelled) return;
        nameCache.current.set(merchantId, merchant.name);
        setMerchantName(merchant.name);
      })
      .catch(() => {
        // Name is a display nicety, not load-bearing — the pill falls back
        // to a shortened id (see sidebar.tsx) rather than blocking on this.
        if (!cancelled) setMerchantName(null);
      });

    return () => {
      cancelled = true;
    };
  }, [merchantId]);

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
    <MerchantContext.Provider
      value={{ merchantId, setMerchantId, merchantName, agentApiKey, setAgentApiKey, hydrated }}
    >
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
