import { useEffect, useState } from "react";
import { fetchAnalyticsSummary } from "./api";
import type { HubAnalyticsSummary } from "./types";

type Props = {
  canRead: boolean;
};

export function HubAnalyticsSection({ canRead }: Props) {
  const [hours, setHours] = useState(24);
  const [data, setData] = useState<HubAnalyticsSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!canRead) return;
    setLoading(true);
    setError(null);
    void fetchAnalyticsSummary(hours)
      .then(setData)
      .catch((err: Error) => setError(err.message || "Failed to load analytics"))
      .finally(() => setLoading(false));
  }, [canRead, hours]);

  if (!canRead) return null;

  const totals = data?.totals;
  const finops = data?.finops;

  return (
    <section className="rounded-lg border bg-card p-4 space-y-3 text-sm">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <div>
          <h2 className="text-sm font-medium">Hub usage &amp; FinOps</h2>
          <p className="text-[11px] text-muted-foreground">
            Telemetry from MCP Clients (Spec 028). Events + Hub agent costs.
          </p>
        </div>
        <select
          className="h-7 rounded-md border bg-background px-2 text-xs"
          value={hours}
          onChange={(e) => setHours(Number(e.target.value))}
        >
          <option value={24}>Last 24h</option>
          <option value={168}>Last 7d</option>
          <option value={720}>Last 30d</option>
        </select>
      </div>
      {loading ? <p className="text-xs text-muted-foreground">Loading…</p> : null}
      {error ? <p className="text-xs text-destructive">{error}</p> : null}
      {data && !loading ? (
        <>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs">
            <Stat label="Active clients" value={String(data.active_clients ?? 0)} />
            <Stat label="tools/list" value={String(totals?.lists ?? 0)} />
            <Stat label="tools/call" value={String(totals?.calls ?? 0)} />
            <Stat label="agent__* calls" value={String(totals?.agent_calls ?? 0)} />
            <Stat label="Denials" value={String(totals?.denials ?? 0)} />
            <Stat label="Errors" value={String(totals?.errors ?? 0)} />
            <Stat label="Hub invocations" value={String(finops?.invocations ?? 0)} />
            <Stat
              label="Est. cost"
              value={finops?.estimated_cost != null ? `$${Number(finops.estimated_cost).toFixed(4)}` : "$0"}
            />
          </div>
          {(data.clients || []).length ? (
            <div className="overflow-x-auto rounded-md border">
              <table className="w-full text-xs">
                <thead className="bg-muted/40 text-left">
                  <tr>
                    <th className="px-2 py-1.5 font-medium">Client</th>
                    <th className="px-2 py-1.5 font-medium">Lists</th>
                    <th className="px-2 py-1.5 font-medium">Calls</th>
                    <th className="px-2 py-1.5 font-medium">Agents</th>
                    <th className="px-2 py-1.5 font-medium">Denials</th>
                    <th className="px-2 py-1.5 font-medium">Avg ms</th>
                    <th className="px-2 py-1.5 font-medium">Tokens</th>
                    <th className="px-2 py-1.5 font-medium">Cost</th>
                  </tr>
                </thead>
                <tbody>
                  {data.clients.map((c) => (
                    <tr key={c.slug} className="border-t">
                      <td className="px-2 py-1.5 font-mono">{c.slug}</td>
                      <td className="px-2 py-1.5">{c.lists}</td>
                      <td className="px-2 py-1.5">{c.calls}</td>
                      <td className="px-2 py-1.5">{c.agent_calls}</td>
                      <td className="px-2 py-1.5">{c.denials}</td>
                      <td className="px-2 py-1.5">{c.avg_duration_ms}</td>
                      <td className="px-2 py-1.5">
                        {(c.finops?.input_tokens ?? 0) + (c.finops?.output_tokens ?? 0)}
                      </td>
                      <td className="px-2 py-1.5">
                        {c.finops?.estimated_cost != null
                          ? `$${Number(c.finops.estimated_cost).toFixed(4)}`
                          : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="text-[11px] text-muted-foreground italic">
              No Hub traffic in this window yet. Connect a client and call tools.
            </p>
          )}
        </>
      ) : null}
    </section>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border px-2 py-1.5">
      <div className="text-[10px] text-muted-foreground uppercase tracking-wide">{label}</div>
      <div className="font-medium tabular-nums">{value}</div>
    </div>
  );
}
