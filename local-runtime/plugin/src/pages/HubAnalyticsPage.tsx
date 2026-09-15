import { useEffect, useMemo, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Bar,
  BarChart,
  CartesianGrid,
  LabelList,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { fetchAnalyticsErrors, fetchAnalyticsSummary, fetchAnalyticsTools, fetchMcpClients } from "../local-runtime/api";
import type {
  HubAnalyticsErrorEvent,
  HubAnalyticsErrors,
  HubAnalyticsSummary,
  HubAnalyticsToolRow,
  McpHubClient,
} from "../local-runtime/types";

type Props = {
  canRead: boolean;
};

type HourRange = 24 | 168 | 720;

const HOUR_OPTIONS: { value: HourRange; label: string }[] = [
  { value: 24, label: "24h" },
  { value: 168, label: "7d" },
  { value: 720, label: "30d" },
];

export function HubAnalyticsPage({ canRead }: Props) {
  const [hours, setHours] = useState<HourRange>(24);
  const [summary, setSummary] = useState<HubAnalyticsSummary | null>(null);
  const [tools, setTools] = useState<HubAnalyticsToolRow[]>([]);
  const [errorsPayload, setErrorsPayload] = useState<HubAnalyticsErrors | null>(null);
  const [clients, setClients] = useState<McpHubClient[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!canRead) return;
    setLoading(true);
    setError(null);
    void Promise.all([
      fetchAnalyticsSummary(hours),
      fetchAnalyticsTools(hours),
      fetchAnalyticsErrors(hours, 100),
      fetchMcpClients(),
    ])
      .then(([s, t, e, c]) => {
        setSummary(s);
        setTools(t.tools || []);
        setErrorsPayload(e);
        setClients(c);
      })
      .catch((err: Error) => setError(err.message || "Failed to load Hub analytics"))
      .finally(() => setLoading(false));
  }, [canRead, hours]);

  const adoptionRows = useMemo(() => buildAdoptionRows(clients, summary), [clients, summary]);

  const trafficByClient = useMemo(
    () =>
      (summary?.clients || []).slice(0, 10).map((c) => ({
        name: shortLabel(c.slug, 16),
        lists: c.lists,
        calls: c.calls,
        agents: c.agent_calls,
        denials: c.denials,
      })),
    [summary],
  );

  const topTools = useMemo(() => {
    const byTool = new Map<string, number>();
    for (const t of tools) {
      const name = t.tool_name || "(unnamed)";
      byTool.set(name, (byTool.get(name) || 0) + t.calls);
    }
    return [...byTool.entries()]
      .sort((a, b) => b[1] - a[1])
      .slice(0, 10)
      .map(([name, value]) => ({ name: shortLabel(name, 22), value }));
  }, [tools]);

  const denialTools = useMemo(() => {
    const byTool = new Map<string, number>();
    for (const t of tools) {
      if (!t.denials) continue;
      const name = t.tool_name || "(unnamed)";
      byTool.set(name, (byTool.get(name) || 0) + t.denials);
    }
    return [...byTool.entries()]
      .sort((a, b) => b[1] - a[1])
      .slice(0, 10)
      .map(([name, value]) => ({ name: shortLabel(name, 22), value }));
  }, [tools]);

  const funnel = useMemo(() => {
    return [
      { name: "Registered", value: clients.length },
      { name: "Active", value: summary?.active_clients ?? 0 },
      { name: "List", value: adoptionRows.filter((r) => r.reached_list).length },
      { name: "Call", value: adoptionRows.filter((r) => r.reached_call).length },
      { name: "Agent", value: adoptionRows.filter((r) => r.reached_agent).length },
    ];
  }, [clients.length, summary, adoptionRows]);

  const errorCodeChart = useMemo(
    () =>
      (errorsPayload?.by_code || []).slice(0, 12).map((r) => ({
        name: shortLabel(`${r.phase}:${r.error_code}`, 28),
        value: r.count,
        phase: r.phase,
      })),
    [errorsPayload],
  );

  const errorEvents: HubAnalyticsErrorEvent[] = errorsPayload?.events || [];

  const costByClient = useMemo(
    () =>
      (summary?.finops?.by_client || [])
        .slice()
        .sort((a, b) => b.estimated_cost - a.estimated_cost)
        .slice(0, 10)
        .map((f) => ({
          name: shortLabel(f.slug, 16),
          cost: Number(f.estimated_cost || 0),
          input: f.input_tokens,
          output: f.output_tokens,
        })),
    [summary],
  );

  if (!canRead) {
    return (
      <div className="space-y-6">
        <div>
          <h2 className="text-lg font-semibold">Hub analytics</h2>
          <p className="text-sm text-muted-foreground">Requires mcp:read.</p>
        </div>
      </div>
    );
  }

  const totals = summary?.totals;
  const finops = summary?.finops;
  const topClient = summary?.clients?.[0]?.slug ?? "—";

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div>
          <h2 className="text-lg font-semibold">Hub analytics</h2>
          <p className="text-sm text-muted-foreground">
            MCP Client usage, adoption, and FinOps (Spec 028)
          </p>
        </div>
        <div className="flex items-center gap-2">
          {HOUR_OPTIONS.map((r) => (
            <button
              key={r.value}
              type="button"
              onClick={() => setHours(r.value)}
              className={`px-3 py-1 text-xs rounded-md border transition-colors ${
                hours === r.value
                  ? "bg-primary text-primary-foreground"
                  : "hover:bg-accent"
              }`}
            >
              {r.label}
            </button>
          ))}
        </div>
      </div>

      {loading && !summary && (
        <div className="text-sm text-muted-foreground">Loading Hub analytics...</div>
      )}
      {error ? <p className="text-xs text-destructive">{error}</p> : null}

      {summary && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
            <MetricCard label="Active Clients" value={String(summary.active_clients ?? 0)} />
            <MetricCard label="tools/list" value={String(totals?.lists ?? 0)} />
            <MetricCard label="tools/call" value={String(totals?.calls ?? 0)} />
            <MetricCard label="agent__* Calls" value={String(totals?.agent_calls ?? 0)} />
            <MetricCard
              label="Est. Cost"
              value={
                finops?.estimated_cost != null
                  ? `$${Number(finops.estimated_cost).toFixed(4)}`
                  : "$0"
              }
            />
          </div>

          <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
            <MetricCard label="Denials" value={String(totals?.denials ?? 0)} />
            <MetricCard label="Errors" value={String(totals?.errors ?? 0)} />
            <MetricCard label="Hub Invocations" value={String(finops?.invocations ?? 0)} />
            <MetricCard
              label="Tokens (in+out)"
              value={String((finops?.input_tokens ?? 0) + (finops?.output_tokens ?? 0))}
            />
            <MetricCard label="Top Client" value={topClient} />
          </div>

          <Tabs defaultValue="overview">
            <TabsList>
              <TabsTrigger value="overview">Overview</TabsTrigger>
              <TabsTrigger value="tools">Tools</TabsTrigger>
              <TabsTrigger value="adoption">Adoption</TabsTrigger>
              <TabsTrigger value="finops">FinOps</TabsTrigger>
              <TabsTrigger value="errors">Errors</TabsTrigger>
            </TabsList>

            <TabsContent value="overview" className="mt-4 space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm font-medium">Traffic by Client</CardTitle>
                  </CardHeader>
                  <CardContent className="pb-3">
                    {trafficByClient.length > 0 ? (
                      <div className="bg-white dark:bg-background rounded-md pt-2 px-2 pb-0">
                        <ResponsiveContainer width="100%" height={220}>
                          <BarChart data={trafficByClient} margin={{ top: 16, right: 10, bottom: 8, left: -10 }}>
                            <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
                            <XAxis dataKey="name" tick={{ fontSize: 10 }} interval={0} angle={-25} textAnchor="end" height={48} />
                            <YAxis tick={{ fontSize: 10 }} allowDecimals={false} width={28} />
                            <Tooltip
                              cursor={{ fill: "var(--muted, #f1f5f9)", opacity: 0.5 }}
                              content={({ active, payload }) => {
                                if (!active || !payload?.length || !payload[0]) return null;
                                const d = payload[0].payload as {
                                  name: string;
                                  lists: number;
                                  calls: number;
                                  agents: number;
                                  denials: number;
                                };
                                return (
                                  <div className="rounded-md border bg-background px-3 py-1.5 text-xs shadow-sm">
                                    <p className="font-medium font-mono">{d.name}</p>
                                    <p className="text-muted-foreground">lists {d.lists} · calls {d.calls}</p>
                                    <p className="text-muted-foreground">agents {d.agents} · denials {d.denials}</p>
                                  </div>
                                );
                              }}
                            />
                            <Legend wrapperStyle={{ fontSize: 11 }} />
                            <Bar dataKey="lists" name="lists" fill="var(--chart-1, #2563eb)" radius={[2, 2, 0, 0]} />
                            <Bar dataKey="calls" name="calls" fill="var(--chart-2, #16a34a)" radius={[2, 2, 0, 0]} />
                            <Bar dataKey="agents" name="agent__*" fill="var(--chart-3, #ea580c)" radius={[2, 2, 0, 0]} />
                            <Bar dataKey="denials" name="denials" fill="var(--chart-4, #dc2626)" radius={[2, 2, 0, 0]} />
                          </BarChart>
                        </ResponsiveContainer>
                      </div>
                    ) : (
                      <p className="text-xs text-muted-foreground">No traffic data</p>
                    )}
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm font-medium">Adoption Funnel</CardTitle>
                  </CardHeader>
                  <CardContent className="pb-3">
                    {funnel.some((f) => f.value > 0) ? (
                      <div className="bg-white dark:bg-background rounded-md pt-2 px-2 pb-0">
                        <ResponsiveContainer width="100%" height={220}>
                          <BarChart data={funnel} margin={{ top: 16, right: 10, bottom: 0, left: -20 }}>
                            <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
                            <XAxis dataKey="name" tick={{ fontSize: 10 }} />
                            <YAxis tick={{ fontSize: 10 }} allowDecimals={false} width={28} />
                            <Tooltip
                              cursor={{ fill: "var(--muted, #f1f5f9)", opacity: 0.5 }}
                              content={({ active, payload }) => {
                                if (!active || !payload?.length || !payload[0]) return null;
                                const d = payload[0].payload as { name: string; value: number };
                                return (
                                  <div className="rounded-md border bg-background px-3 py-1.5 text-xs shadow-sm">
                                    <p className="font-medium">{d.name}</p>
                                    <p className="text-muted-foreground">{d.value} clients</p>
                                  </div>
                                );
                              }}
                            />
                            <Bar dataKey="value" fill="var(--chart-1, #2563eb)" radius={[2, 2, 0, 0]}>
                              <LabelList dataKey="value" position="top" style={{ fontSize: 9, fill: "currentColor" }} />
                            </Bar>
                          </BarChart>
                        </ResponsiveContainer>
                      </div>
                    ) : (
                      <p className="text-xs text-muted-foreground">No adoption data</p>
                    )}
                  </CardContent>
                </Card>
              </div>

              <Card className="bg-muted/30">
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-medium">Clients</CardTitle>
                  <p className="text-xs text-muted-foreground">
                    Aggregated Hub traffic for the selected window.
                  </p>
                </CardHeader>
                <CardContent>
                  {(summary.clients || []).length === 0 ? (
                    <p className="text-sm text-muted-foreground">No Hub traffic in this window</p>
                  ) : (
                    <div className="border rounded-md overflow-hidden">
                      <Table>
                        <TableHeader>
                          <TableRow>
                            <TableHead className="text-xs">Client</TableHead>
                            <TableHead className="text-xs text-right">Lists</TableHead>
                            <TableHead className="text-xs text-right">Calls</TableHead>
                            <TableHead className="text-xs text-right">Agents</TableHead>
                            <TableHead className="text-xs text-right">Denials</TableHead>
                            <TableHead className="text-xs text-right">Avg ms</TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {summary.clients.map((c) => (
                            <TableRow key={c.slug} className="bg-white dark:bg-transparent hover:bg-muted/50 dark:hover:bg-muted/20">
                              <TableCell className="text-xs font-mono">{c.slug}</TableCell>
                              <TableCell className="text-xs text-right font-mono">{c.lists}</TableCell>
                              <TableCell className="text-xs text-right font-mono">{c.calls}</TableCell>
                              <TableCell className="text-xs text-right font-mono">{c.agent_calls}</TableCell>
                              <TableCell className="text-xs text-right font-mono">{c.denials}</TableCell>
                              <TableCell className="text-xs text-right font-mono">{c.avg_duration_ms}</TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    </div>
                  )}
                </CardContent>
              </Card>
            </TabsContent>

            <TabsContent value="tools" className="mt-4 space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm font-medium">Top Tools</CardTitle>
                  </CardHeader>
                  <CardContent className="pb-3">
                    {topTools.length > 0 ? (
                      <div className="bg-white dark:bg-background rounded-md pt-2 px-2 pb-0">
                        <ResponsiveContainer width="100%" height={Math.max(160, topTools.length * 22)}>
                          <BarChart data={topTools} layout="vertical" margin={{ top: 4, right: 30, bottom: 0, left: 0 }}>
                            <CartesianGrid strokeDasharray="3 3" className="stroke-border" horizontal={false} />
                            <XAxis type="number" tick={{ fontSize: 10 }} allowDecimals={false} />
                            <YAxis type="category" dataKey="name" tick={{ fontSize: 10 }} width={90} interval={0} />
                            <Tooltip
                              cursor={{ fill: "var(--muted, #f1f5f9)", opacity: 0.5 }}
                              content={({ active, payload }) => {
                                if (!active || !payload?.length || !payload[0]) return null;
                                const d = payload[0].payload as { name: string; value: number };
                                return (
                                  <div className="rounded-md border bg-background px-3 py-1.5 text-xs shadow-sm">
                                    <p className="font-medium font-mono">{d.name}</p>
                                    <p className="text-muted-foreground">{d.value} calls</p>
                                  </div>
                                );
                              }}
                            />
                            <Bar dataKey="value" fill="var(--chart-2, #16a34a)" radius={[0, 2, 2, 0]}>
                              <LabelList dataKey="value" position="right" style={{ fontSize: 9, fill: "currentColor" }} />
                            </Bar>
                          </BarChart>
                        </ResponsiveContainer>
                      </div>
                    ) : (
                      <p className="text-xs text-muted-foreground">No tool data</p>
                    )}
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm font-medium">Denials by Tool</CardTitle>
                  </CardHeader>
                  <CardContent className="pb-3">
                    {denialTools.length > 0 ? (
                      <div className="bg-white dark:bg-background rounded-md pt-2 px-2 pb-0">
                        <ResponsiveContainer width="100%" height={Math.max(160, denialTools.length * 22)}>
                          <BarChart data={denialTools} layout="vertical" margin={{ top: 4, right: 30, bottom: 0, left: 0 }}>
                            <CartesianGrid strokeDasharray="3 3" className="stroke-border" horizontal={false} />
                            <XAxis type="number" tick={{ fontSize: 10 }} allowDecimals={false} />
                            <YAxis type="category" dataKey="name" tick={{ fontSize: 10 }} width={90} interval={0} />
                            <Tooltip
                              cursor={{ fill: "var(--muted, #f1f5f9)", opacity: 0.5 }}
                              content={({ active, payload }) => {
                                if (!active || !payload?.length || !payload[0]) return null;
                                const d = payload[0].payload as { name: string; value: number };
                                return (
                                  <div className="rounded-md border bg-background px-3 py-1.5 text-xs shadow-sm">
                                    <p className="font-medium font-mono">{d.name}</p>
                                    <p className="text-muted-foreground">{d.value} denials</p>
                                  </div>
                                );
                              }}
                            />
                            <Bar dataKey="value" fill="var(--chart-4, #dc2626)" radius={[0, 2, 2, 0]}>
                              <LabelList dataKey="value" position="right" style={{ fontSize: 9, fill: "currentColor" }} />
                            </Bar>
                          </BarChart>
                        </ResponsiveContainer>
                      </div>
                    ) : (
                      <p className="text-xs text-muted-foreground">No denial data</p>
                    )}
                  </CardContent>
                </Card>
              </div>

              <Card className="bg-muted/30">
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-medium">Tool Calls</CardTitle>
                  <p className="text-xs text-muted-foreground">
                    tools/call aggregated by tool name and client.
                  </p>
                </CardHeader>
                <CardContent>
                  {tools.length === 0 ? (
                    <p className="text-sm text-muted-foreground">No tool calls recorded yet</p>
                  ) : (
                    <div className="border rounded-md overflow-hidden">
                      <Table>
                        <TableHeader>
                          <TableRow>
                            <TableHead className="text-xs">Tool</TableHead>
                            <TableHead className="text-xs">Client</TableHead>
                            <TableHead className="text-xs text-right">Calls</TableHead>
                            <TableHead className="text-xs text-right">Denials</TableHead>
                            <TableHead className="text-xs text-right">Errors</TableHead>
                            <TableHead className="text-xs text-right">Avg ms</TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {tools.map((t, i) => (
                            <TableRow key={`${t.tool_name}-${t.slug}-${i}`} className="bg-white dark:bg-transparent hover:bg-muted/50 dark:hover:bg-muted/20">
                              <TableCell className="text-xs font-mono">{t.tool_name || "(unnamed)"}</TableCell>
                              <TableCell className="text-xs font-mono">{t.slug}</TableCell>
                              <TableCell className="text-xs text-right font-mono">{t.calls}</TableCell>
                              <TableCell className="text-xs text-right font-mono">{t.denials}</TableCell>
                              <TableCell className="text-xs text-right font-mono">{t.errors}</TableCell>
                              <TableCell className="text-xs text-right font-mono">{t.avg_duration_ms}</TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    </div>
                  )}
                </CardContent>
              </Card>
            </TabsContent>

            <TabsContent value="adoption" className="mt-4 space-y-4">
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <MetricCard label="Registered" value={String(clients.length)} />
                <MetricCard label="Active (window)" value={String(summary.active_clients ?? 0)} />
                <MetricCard
                  label="Reached Call"
                  value={String(adoptionRows.filter((r) => r.reached_call).length)}
                />
                <MetricCard
                  label="Reached Agent"
                  value={String(adoptionRows.filter((r) => r.reached_agent).length)}
                />
              </div>

              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-medium">Funnel</CardTitle>
                </CardHeader>
                <CardContent className="pb-3">
                  <div className="bg-white dark:bg-background rounded-md pt-2 px-2 pb-0">
                    <ResponsiveContainer width="100%" height={200}>
                      <BarChart data={funnel} margin={{ top: 16, right: 10, bottom: 0, left: -20 }}>
                        <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
                        <XAxis dataKey="name" tick={{ fontSize: 10 }} />
                        <YAxis tick={{ fontSize: 10 }} allowDecimals={false} width={28} />
                        <Tooltip
                          cursor={{ fill: "var(--muted, #f1f5f9)", opacity: 0.5 }}
                          content={({ active, payload }) => {
                            if (!active || !payload?.length || !payload[0]) return null;
                            const d = payload[0].payload as { name: string; value: number };
                            return (
                              <div className="rounded-md border bg-background px-3 py-1.5 text-xs shadow-sm">
                                <p className="font-medium">{d.name}</p>
                                <p className="text-muted-foreground">{d.value} clients</p>
                              </div>
                            );
                          }}
                        />
                        <Bar dataKey="value" fill="var(--chart-3, #ea580c)" radius={[2, 2, 0, 0]}>
                          <LabelList dataKey="value" position="top" style={{ fontSize: 9, fill: "currentColor" }} />
                        </Bar>
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                </CardContent>
              </Card>

              <Card className="bg-muted/30">
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-medium">Client Adoption</CardTitle>
                  <p className="text-xs text-muted-foreground">
                    List → call → agent__* progress per MCP client channel.
                  </p>
                </CardHeader>
                <CardContent>
                  {adoptionRows.length === 0 ? (
                    <p className="text-sm text-muted-foreground">No MCP clients registered yet</p>
                  ) : (
                    <div className="border rounded-md overflow-hidden">
                      <Table>
                        <TableHeader>
                          <TableRow>
                            <TableHead className="text-xs">Client</TableHead>
                            <TableHead className="text-xs">Status</TableHead>
                            <TableHead className="text-xs">Agents on</TableHead>
                            <TableHead className="text-xs">List</TableHead>
                            <TableHead className="text-xs">Call</TableHead>
                            <TableHead className="text-xs">Agent__</TableHead>
                            <TableHead className="text-xs">Last seen</TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {adoptionRows.map((r) => (
                            <TableRow key={r.slug} className="bg-white dark:bg-transparent hover:bg-muted/50 dark:hover:bg-muted/20">
                              <TableCell className="text-xs font-mono">{r.slug}</TableCell>
                              <TableCell className="text-xs">{r.status}</TableCell>
                              <TableCell className="text-xs">{r.agents_enabled ? "yes" : "no"}</TableCell>
                              <TableCell className="text-xs">{r.reached_list ? "yes" : "—"}</TableCell>
                              <TableCell className="text-xs">{r.reached_call ? "yes" : "—"}</TableCell>
                              <TableCell className="text-xs">
                                {r.reached_agent ? "yes" : r.agents_enabled ? "idle" : "—"}
                              </TableCell>
                              <TableCell className="text-xs font-mono">{r.last_seen || "—"}</TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    </div>
                  )}
                </CardContent>
              </Card>
            </TabsContent>

            <TabsContent value="finops" className="mt-4 space-y-4">
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <MetricCard label="Invocations" value={String(finops?.invocations ?? 0)} />
                <MetricCard label="Input Tokens" value={String(finops?.input_tokens ?? 0)} />
                <MetricCard label="Output Tokens" value={String(finops?.output_tokens ?? 0)} />
                <MetricCard
                  label="Est. Cost"
                  value={
                    finops?.estimated_cost != null
                      ? `$${Number(finops.estimated_cost).toFixed(4)}`
                      : "$0"
                  }
                />
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm font-medium">Estimated Cost by Client</CardTitle>
                  </CardHeader>
                  <CardContent className="pb-3">
                    {costByClient.length > 0 ? (
                      <div className="bg-white dark:bg-background rounded-md pt-2 px-2 pb-0">
                        <ResponsiveContainer width="100%" height={220}>
                          <BarChart data={costByClient} margin={{ top: 16, right: 10, bottom: 8, left: -10 }}>
                            <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
                            <XAxis dataKey="name" tick={{ fontSize: 10 }} interval={0} angle={-25} textAnchor="end" height={48} />
                            <YAxis tick={{ fontSize: 10 }} width={40} />
                            <Tooltip
                              cursor={{ fill: "var(--muted, #f1f5f9)", opacity: 0.5 }}
                              content={({ active, payload }) => {
                                if (!active || !payload?.length || !payload[0]) return null;
                                const d = payload[0].payload as { name: string; cost: number };
                                return (
                                  <div className="rounded-md border bg-background px-3 py-1.5 text-xs shadow-sm">
                                    <p className="font-medium font-mono">{d.name}</p>
                                    <p className="text-muted-foreground">${d.cost.toFixed(4)}</p>
                                  </div>
                                );
                              }}
                            />
                            <Bar dataKey="cost" fill="var(--chart-5, #7c3aed)" radius={[2, 2, 0, 0]} />
                          </BarChart>
                        </ResponsiveContainer>
                      </div>
                    ) : (
                      <p className="text-xs text-muted-foreground">No cost data</p>
                    )}
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm font-medium">Tokens by Client</CardTitle>
                  </CardHeader>
                  <CardContent className="pb-3">
                    {costByClient.length > 0 ? (
                      <div className="bg-white dark:bg-background rounded-md pt-2 px-2 pb-0">
                        <ResponsiveContainer width="100%" height={220}>
                          <BarChart data={costByClient} margin={{ top: 16, right: 10, bottom: 8, left: -10 }}>
                            <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
                            <XAxis dataKey="name" tick={{ fontSize: 10 }} interval={0} angle={-25} textAnchor="end" height={48} />
                            <YAxis tick={{ fontSize: 10 }} allowDecimals={false} width={36} />
                            <Tooltip
                              cursor={{ fill: "var(--muted, #f1f5f9)", opacity: 0.5 }}
                              content={({ active, payload }) => {
                                if (!active || !payload?.length || !payload[0]) return null;
                                const d = payload[0].payload as { name: string; input: number; output: number };
                                return (
                                  <div className="rounded-md border bg-background px-3 py-1.5 text-xs shadow-sm">
                                    <p className="font-medium font-mono">{d.name}</p>
                                    <p className="text-muted-foreground">in {d.input} · out {d.output}</p>
                                  </div>
                                );
                              }}
                            />
                            <Legend wrapperStyle={{ fontSize: 11 }} />
                            <Bar dataKey="input" name="input" stackId="tok" fill="var(--chart-1, #2563eb)" />
                            <Bar dataKey="output" name="output" stackId="tok" fill="var(--chart-2, #16a34a)" radius={[2, 2, 0, 0]} />
                          </BarChart>
                        </ResponsiveContainer>
                      </div>
                    ) : (
                      <p className="text-xs text-muted-foreground">No token data</p>
                    )}
                  </CardContent>
                </Card>
              </div>

              <Card className="bg-muted/30">
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-medium">FinOps by Client</CardTitle>
                  <p className="text-xs text-muted-foreground">
                    Hub-sourced invocations with estimated LiteLLM cost when available.
                  </p>
                </CardHeader>
                <CardContent>
                  {(finops?.by_client || []).length === 0 ? (
                    <p className="text-sm text-muted-foreground">No Hub FinOps data in this window</p>
                  ) : (
                    <div className="border rounded-md overflow-hidden">
                      <Table>
                        <TableHeader>
                          <TableRow>
                            <TableHead className="text-xs">Client</TableHead>
                            <TableHead className="text-xs text-right">Invocations</TableHead>
                            <TableHead className="text-xs text-right">In tok</TableHead>
                            <TableHead className="text-xs text-right">Out tok</TableHead>
                            <TableHead className="text-xs text-right">Avg ms</TableHead>
                            <TableHead className="text-xs text-right">Cost</TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {(finops?.by_client || []).map((f) => (
                            <TableRow key={f.slug} className="bg-white dark:bg-transparent hover:bg-muted/50 dark:hover:bg-muted/20">
                              <TableCell className="text-xs font-mono">{f.slug}</TableCell>
                              <TableCell className="text-xs text-right font-mono">{f.invocations}</TableCell>
                              <TableCell className="text-xs text-right font-mono">{f.input_tokens}</TableCell>
                              <TableCell className="text-xs text-right font-mono">{f.output_tokens}</TableCell>
                              <TableCell className="text-xs text-right font-mono">{f.avg_duration_ms}</TableCell>
                              <TableCell className="text-xs text-right font-mono">
                                ${Number(f.estimated_cost).toFixed(4)}
                              </TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    </div>
                  )}
                </CardContent>
              </Card>
            </TabsContent>

            <TabsContent value="errors" className="mt-4 space-y-4">
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <MetricCard label="Error events" value={String(totals?.errors ?? 0)} />
                <MetricCard label="Denials" value={String(totals?.denials ?? 0)} />
                <MetricCard
                  label="Distinct codes"
                  value={String(errorsPayload?.by_code?.length ?? 0)}
                />
                <MetricCard
                  label="Recent rows"
                  value={String(errorEvents.length)}
                />
              </div>

              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-medium">By error_code</CardTitle>
                </CardHeader>
                <CardContent className="pb-3">
                  {errorCodeChart.length > 0 ? (
                    <div className="bg-white dark:bg-background rounded-md pt-2 px-2 pb-0">
                      <ResponsiveContainer width="100%" height={Math.max(160, errorCodeChart.length * 22)}>
                        <BarChart data={errorCodeChart} layout="vertical" margin={{ top: 4, right: 30, bottom: 0, left: 0 }}>
                          <CartesianGrid strokeDasharray="3 3" className="stroke-border" horizontal={false} />
                          <XAxis type="number" tick={{ fontSize: 10 }} allowDecimals={false} />
                          <YAxis type="category" dataKey="name" tick={{ fontSize: 10 }} width={120} interval={0} />
                          <Tooltip
                            cursor={{ fill: "var(--muted, #f1f5f9)", opacity: 0.5 }}
                            content={({ active, payload }) => {
                              if (!active || !payload?.length || !payload[0]) return null;
                              const d = payload[0].payload as { name: string; value: number; phase: string };
                              return (
                                <div className="rounded-md border bg-background px-3 py-1.5 text-xs shadow-sm">
                                  <p className="font-medium font-mono">{d.name}</p>
                                  <p className="text-muted-foreground">{d.value} · {d.phase}</p>
                                </div>
                              );
                            }}
                          />
                          <Bar dataKey="value" fill="var(--chart-4, #dc2626)" radius={[0, 2, 2, 0]}>
                            <LabelList dataKey="value" position="right" style={{ fontSize: 9, fill: "currentColor" }} />
                          </Bar>
                        </BarChart>
                      </ResponsiveContainer>
                    </div>
                  ) : (
                    <p className="text-xs text-muted-foreground">No error or denial codes in this window</p>
                  )}
                </CardContent>
              </Card>

              <Card className="bg-muted/30">
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-medium">Recent failures</CardTitle>
                  <p className="text-xs text-muted-foreground">
                    Last {errorsPayload?.limit ?? 100} events with phase error or denied.
                    Includes truncated operational reason (`meta.reason`); no args/prompt/response.
                  </p>
                </CardHeader>
                <CardContent>
                  {errorEvents.length === 0 ? (
                    <p className="text-sm text-muted-foreground">No failures in this window</p>
                  ) : (
                    <div className="border rounded-md overflow-hidden">
                      <Table>
                        <TableHeader>
                          <TableRow>
                            <TableHead className="text-xs">When</TableHead>
                            <TableHead className="text-xs">Phase</TableHead>
                            <TableHead className="text-xs">Code</TableHead>
                            <TableHead className="text-xs">Reason</TableHead>
                            <TableHead className="text-xs">Tool</TableHead>
                            <TableHead className="text-xs">Client</TableHead>
                            <TableHead className="text-xs text-right">ms</TableHead>
                            <TableHead className="text-xs">Request</TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {errorEvents.map((ev, i) => (
                            <TableRow
                              key={`${ev.request_id || ev.occurred_at}-${i}`}
                              className="bg-white dark:bg-transparent hover:bg-muted/50 dark:hover:bg-muted/20"
                            >
                              <TableCell className="text-xs font-mono whitespace-nowrap">
                                {formatSeen(ev.occurred_at) || ev.occurred_at || "—"}
                              </TableCell>
                              <TableCell className="text-xs">
                                <span
                                  className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-medium ${
                                    ev.phase === "denied"
                                      ? "bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200"
                                      : "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200"
                                  }`}
                                >
                                  {ev.phase}
                                </span>
                              </TableCell>
                              <TableCell className="text-xs font-mono">{ev.error_code || "—"}</TableCell>
                              <TableCell className="text-xs max-w-[280px]" title={ev.reason || undefined}>
                                <span className="line-clamp-2 break-words text-muted-foreground">
                                  {ev.reason || "—"}
                                </span>
                              </TableCell>
                              <TableCell className="text-xs font-mono">
                                {ev.tool_name || "—"}
                                {ev.original_tool ? (
                                  <span className="text-muted-foreground"> → {ev.original_tool}</span>
                                ) : null}
                              </TableCell>
                              <TableCell className="text-xs font-mono">{ev.slug}</TableCell>
                              <TableCell className="text-xs text-right font-mono">
                                {ev.duration_ms ?? "—"}
                              </TableCell>
                              <TableCell className="text-xs font-mono text-muted-foreground truncate max-w-[120px]">
                                {ev.request_id || "—"}
                              </TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    </div>
                  )}
                </CardContent>
              </Card>
            </TabsContent>
          </Tabs>
        </>
      )}
    </div>
  );
}

type AdoptionRow = {
  slug: string;
  status: string;
  agents_enabled: boolean;
  reached_list: boolean;
  reached_call: boolean;
  reached_agent: boolean;
  last_seen: string;
};

function buildAdoptionRows(
  clients: McpHubClient[],
  summary: HubAnalyticsSummary | null,
): AdoptionRow[] {
  const bySlug = new Map((summary?.clients || []).map((c) => [c.slug, c]));
  const rows: AdoptionRow[] = clients.map((c) => {
    const stats = bySlug.get(c.slug);
    return {
      slug: c.slug,
      status: c.status,
      agents_enabled: Boolean(c.agents_enabled),
      reached_list: (stats?.lists ?? 0) > 0,
      reached_call: (stats?.calls ?? 0) > 0,
      reached_agent: (stats?.agent_calls ?? 0) > 0,
      last_seen: formatSeen(c.last_seen_at),
    };
  });
  for (const c of summary?.clients || []) {
    if (rows.some((r) => r.slug === c.slug)) continue;
    rows.push({
      slug: c.slug,
      status: "unknown",
      agents_enabled: false,
      reached_list: c.lists > 0,
      reached_call: c.calls > 0,
      reached_agent: c.agent_calls > 0,
      last_seen: "—",
    });
  }
  return rows.sort((a, b) => a.slug.localeCompare(b.slug));
}

function formatSeen(iso?: string): string {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

function shortLabel(value: string, max: number): string {
  if (value.length <= max) return value;
  return `${value.slice(0, max - 1)}…`;
}

function MetricCard({ label, value }: { label: string; value: string }) {
  return (
    <Card>
      <CardContent className="pt-2 pb-2">
        <div className="text-xs text-muted-foreground">{label}</div>
        <div className="bg-white dark:bg-background rounded-md px-2 py-1 mt-1">
          <div className="text-xl font-mono font-semibold truncate">{value}</div>
        </div>
      </CardContent>
    </Card>
  );
}
