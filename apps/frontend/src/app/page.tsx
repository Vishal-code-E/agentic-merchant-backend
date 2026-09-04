"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import type {
  ChatCheckoutRequest,
  ChatCheckoutResponse,
  RegenerateApiKeyResponse,
} from "@agentic-merchant/shared-types";
import { apiPost, ApiError } from "../lib/api";
import { useMerchant } from "../lib/merchant-context";

type ChatEntry =
  | { role: "user"; text: string }
  | {
      role: "system";
      interpretation: string;
      matched: boolean;
      checkoutResult: ChatCheckoutResponse["checkoutResult"];
    };

const EXAMPLE_MESSAGES = ["I want 2 face washes under ₹400", "buy me a spaceship"];

export default function Home() {
  const { merchantId, hydrated, agentApiKey, setAgentApiKey } = useMerchant();
  const router = useRouter();
  const [messages, setMessages] = useState<ChatEntry[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmingRegenerate, setConfirmingRegenerate] = useState(false);
  const [regenerating, setRegenerating] = useState(false);
  const [regenerateError, setRegenerateError] = useState<string | null>(null);
  const chatEndRef = useRef<HTMLDivElement>(null);

  // Sign-in gate: no active merchant on a direct/refresh visit sends the visitor to onboard first.
  useEffect(() => {
    if (hydrated && !merchantId) {
      router.replace("/onboarding");
    }
  }, [hydrated, merchantId, router]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, sending]);

  async function sendMessage(text: string) {
    const trimmed = text.trim();
    if (!merchantId || !agentApiKey || !trimmed || sending) return;

    setError(null);
    setSending(true);
    setMessages((prev) => [...prev, { role: "user", text: trimmed }]);
    setInput("");

    const payload: ChatCheckoutRequest = { merchantId, message: trimmed };
    try {
      const response = await apiPost<ChatCheckoutResponse>("/agent/chat-checkout", payload, {
        "X-Agent-Api-Key": agentApiKey,
      });
      setMessages((prev) => [
        ...prev,
        {
          role: "system",
          interpretation: response.interpretation,
          matched: response.matched,
          checkoutResult: response.checkoutResult,
        },
      ]);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to reach the backend.");
    } finally {
      setSending(false);
    }
  }

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    sendMessage(input);
  }

  async function handleGenerateKey() {
    if (!merchantId) return;
    setRegenerateError(null);
    setRegenerating(true);
    try {
      const response = await apiPost<RegenerateApiKeyResponse>(
        `/merchant/${merchantId}/api-key/regenerate`,
        {}
      );
      setAgentApiKey(response.api_key);
      setConfirmingRegenerate(false);
    } catch (err) {
      setRegenerateError(err instanceof ApiError ? err.message : "Failed to generate an API key.");
    } finally {
      setRegenerating(false);
    }
  }

  // Gate pending or redirecting — render nothing rather than a flash of empty chat.
  if (!hydrated || !merchantId) {
    return null;
  }

  if (!agentApiKey) {
    return (
      <div className="chat-page">
        <div className="chat-gate">
          <div className="banner banner-warning">
            <strong>No API key held for this browser session.</strong>
            <div className="hint" style={{ marginTop: 4, marginBottom: 8 }}>
              The agent API key is only ever shown once, at onboarding — a refresh, a new tab, or
              onboarding in an earlier session all lose it. Generate a fresh one to continue.
            </div>
            {!confirmingRegenerate ? (
              <button type="button" className="btn-secondary" onClick={() => setConfirmingRegenerate(true)}>
                Generate a fresh API key
              </button>
            ) : (
              <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                <span className="hint">
                  This immediately invalidates any key issued earlier for this merchant.
                </span>
                <button
                  type="button"
                  className="btn-danger"
                  onClick={handleGenerateKey}
                  disabled={regenerating}
                >
                  {regenerating ? "Generating..." : "Confirm"}
                </button>
                <button
                  type="button"
                  className="btn-secondary"
                  onClick={() => setConfirmingRegenerate(false)}
                  disabled={regenerating}
                >
                  Cancel
                </button>
              </div>
            )}
            {regenerateError && (
              <div className="banner banner-error" style={{ marginTop: 8 }}>
                {regenerateError}
              </div>
            )}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="chat-page">
      <div className="chat-messages">
        <div className="chip-row">
          {EXAMPLE_MESSAGES.map((example) => (
            <button
              key={example}
              type="button"
              className="chip"
              onClick={() => sendMessage(example)}
              disabled={sending}
            >
              {example}
            </button>
          ))}
        </div>

        {error && <div className="banner banner-error">{error}</div>}

        {messages.length === 0 && !sending ? (
          <div className="chat-empty">
            <div className="chat-empty-icon">💬</div>
            <p>No messages yet — try an example above or type your own below.</p>
          </div>
        ) : (
          <>
            {messages.map((entry, i) =>
              entry.role === "user" ? (
                <div className="chat-bubble-user" key={i}>
                  {entry.text}
                </div>
              ) : (
                <div key={i} className={`chat-bubble-system ${entry.matched ? "matched" : "unmatched"}`}>
                  <div>{entry.interpretation}</div>
                  {entry.matched && entry.checkoutResult && (
                    <div className="chat-order-detail">
                      <span className="chat-order-badge">
                        ✅ Order {entry.checkoutResult.razorpayOrderId ?? "(pending)"}
                      </span>
                      <span style={{ marginLeft: 8 }}>
                        {entry.checkoutResult.amount} {entry.checkoutResult.currency}
                      </span>
                      {entry.checkoutResult.upsellSuggestions.length > 0 && (
                        <div className="hint" style={{ marginTop: 6 }}>
                          Suggested: {entry.checkoutResult.upsellSuggestions.map((p) => p.name).join(", ")}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )
            )}
            {sending && (
              <div className="typing-indicator">
                <span className="dot" />
                <span className="dot" />
                <span className="dot" />
              </div>
            )}
            <div ref={chatEndRef} />
          </>
        )}
      </div>

      <div className="chat-input-bar">
        <form className="chat-input-row" onSubmit={handleSubmit}>
          <input
            type="text"
            placeholder="e.g. 2x face wash under ₹400"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            disabled={sending}
            autoFocus
          />
          <button className="btn" type="submit" disabled={sending || !input.trim()}>
            {sending ? "Sending…" : "Send"}
          </button>
        </form>
      </div>
    </div>
  );
}
