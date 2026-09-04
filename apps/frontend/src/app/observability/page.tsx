"use client";

import { Fragment, useEffect, useState } from "react";
import type { AgentRun, AuditLogEntry } from "@agentic-merchant/shared-types";
import { apiGet, ApiError } from "../../lib/api";
import { useMerchant } from "../../lib/merchant-context";

function statusBadgeClass(status: string): string {
  if (status === "success") return "badge badge-success";
  if (status === "failed") return "badge badge-failed";
  return "badge badge-running";
}

function AuditLogRow({ agentRunId }: { agentRunId: string }) {
  const [logs, setLogs] = useState<AuditLogEntry[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiGet<AuditLogEntry[]>(`/observability/agent-runs/${agentRunId}/audit-logs`)
      .then(setLogs)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Failed to load audit logs."));
  }, [agentRunId]);

  return (
    <tr>
      <td colSpan={5}>
        {error && <div className="banner banner-error">{error}</div>}
        {!error && logs === null && <p className="muted">Loading audit logs...</p>}
        {logs && logs.length === 0 && <p className="muted">No audit log entries for this run.</p>}
        {logs && logs.length > 0 && (
          <table>
            <thead>
              <tr>
                <th>Event</th>
                <th>Payload</th>
                <th>Created</th>
              </tr>
            </thead>
            <tbody>
              {logs.map((log) => (
                <tr key={log.id}>
                  <td>{log.eventType}</td>
                  <td>
                    <code>{JSON.stringify(log.payload)}</code>
                  </td>
                  <td>{new Date(log.createdAt).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </td>
    </tr>
  );
}

export default function ObservabilityPage() {
  const { merchantId } = useMerchant();
  const [runs, setRuns] = useState<AgentRun[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);

  useEffect(() => {
    if (!merchantId) {
      setRuns([]);
      return;
    }

    // Guard against out-of-order responses: switching merchants fires a new
    // fetch before the previous one necessarily resolves, and without this a
    // slower, stale response can overwrite fresher state (see the merchant
    // switcher in nav.tsx — this is exactly the shape that triggers it).
    let cancelled = false;
    setLoading(true);
    setError(null);
    apiGet<AgentRun[]>(`/observability/agent-runs?merchant_id=${merchantId}`)
      .then((data) => {
        if (!cancelled) setRuns(data);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof ApiError ? err.message : "Failed to load agent runs.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [merchantId]);

  if (!merchantId) {
    return (
      <main className="container">
        <h1>Observability</h1>
        <div className="banner banner-warning">
          No merchant selected. Go to <a href="/onboarding">Onboarding</a> first.
        </div>
      </main>
    );
  }

  return (
    <main className="container">
      <h1>Observability</h1>
      <p className="muted">
        Agent runs for merchant <code>{merchantId}</code>. Click a row to see its audit trail.
      </p>

      {error && <div className="banner banner-error">{error}</div>}

      <div className="card">
        {loading ? (
          <p className="muted">Loading...</p>
        ) : runs.length === 0 ? (
          <p className="muted">No agent runs yet — try /agent/checkout or /internal/campaigns/run.</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Type</th>
                <th>Status</th>
                <th>Started</th>
                <th>Ended</th>
                <th>Trace</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((run) => (
                <Fragment key={run.id}>
                  <tr
                    className="row-expand"
                    onClick={() => setExpanded(expanded === run.id ? null : run.id)}
                  >
                    <td>{run.type}</td>
                    <td>
                      <span className={statusBadgeClass(run.status)}>{run.status}</span>
                    </td>
                    <td>{run.startedAt ? new Date(run.startedAt).toLocaleString() : "—"}</td>
                    <td>{run.endedAt ? new Date(run.endedAt).toLocaleString() : "—"}</td>
                    <td>
                      {run.langfuseTraceId ? (
                        <a
                          href={`https://cloud.langfuse.com/trace/${run.langfuseTraceId}`}
                          target="_blank"
                          rel="noreferrer"
                          onClick={(e) => e.stopPropagation()}
                        >
                          View trace
                        </a>
                      ) : (
                        <span className="muted">—</span>
                      )}
                    </td>
                  </tr>
                  {expanded === run.id && <AuditLogRow agentRunId={run.id} />}
                </Fragment>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </main>
  );
}
