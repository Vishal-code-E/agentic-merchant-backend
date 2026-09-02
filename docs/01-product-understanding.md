\# Product Understanding – Razorpay Agentic Merchant Backend

\#\# 1\. Context and Motivation

Commerce is shifting from clicks and forms to agent-led, conversational experiences,  
where AI agents help users discover, decide, and complete transactions inside chats,  
apps, and voice surfaces.\[cite:18\]

Razorpay and NPCI have already piloted Agentic Payments on platforms like Claude and  
voice AI, showing that AI can securely complete UPI payments on behalf of users within  
pre-set spending limits.\[cite:30\]

Merchants, however, lack a standardized, safe backend that makes them "AI-sellable" and  
lets agent workflows drive revenue without rebuilding their stack from scratch.

\#\# 2\. Problem Statement

For a typical Razorpay merchant today:

\- Their product catalog is human-facing (web/app), not agent-readable.  
\- External AI agents (ChatGPT tools, Claude agents, AP2 clients) cannot reliably  
  discover, search, and transact without brittle scraping or custom integrations.  
\- Merchant-side growth levers (upsell, cross-sell, recovery campaigns) are not  
  integrated with agent flows or Razorpay payment rails.  
\- There is no unified, explainable audit trail of agent decisions and money actions  
  that satisfies emerging agentic payment standards (UAP/AP2-style mandates).\[cite:11\]

We are solving:

\> How to turn a Razorpay merchant into an AI-ready, revenue-optimized endpoint where  
\> agents can safely discover catalog, orchestrate checkout, and run growth workflows,  
\> with all money actions explainable, bounded, gated, and auditable.

\#\# 3\. Solution Overview

We are building a backend-first product:

\- A \*\*FastAPI \+ LangGraph agentic backend\*\* that exposes:  
  \- Agent-readable catalog APIs (REST/GraphQL).  
  \- Agent-friendly checkout orchestration over Razorpay test-mode Orders/Payments.  
  \- Policy/mandate checks before any money action.  
\- A \*\*merchant revenue agent\*\* that:  
  \- Suggests upsell/cross-sell at the right point in the flow.  
  \- Runs basic recovery and campaign jobs in the background.  
\- A \*\*deep observability layer\*\*:  
  \- Langfuse traces for agent runs.  
  \- Structured audit logs tying together intent, policies, Razorpay calls, and outcomes.

This backend sits behind a Next.js dashboard for merchant onboarding, configuration,  
and observability.

\#\# 4\. Core User Personas

\- \*\*Merchant Owner / Growth Lead\*\*  
  \- Wants more revenue from agent-led channels without risking compliance or UX.  
  \- Uses the dashboard to configure catalog, offers, limits, and monitor performance.

\- \*\*AI Agent Integrator / Platform\*\*  
  \- Needs a clean, documented API surface to browse catalog and initiate checkout.  
  \- Relies on our backend to enforce policies and handle Razorpay orchestration.

\- \*\*Developer / Operator\*\*  
  \- Maintains the FastAPI/LangGraph stack.  
  \- Needs clear logs, traces, and configurations to debug agent behaviour.\[cite:44\]

\#\# 5\. Success Criteria (Initial)

\- A test-mode merchant can:  
  \- Connect Razorpay keys.  
  \- Expose an agent-readable catalog endpoint.  
  \- Complete an end-to-end agent-led checkout flow in test mode.  
  \- See an audit trail for at least one successful and one failed payment.  
\- The system can be reasonably extended later to AP2/UCP/UAP-style integrations  
  and live mode.  
