export type HubInfo = {
  mcp_hub_url: string;
  resource: string;
  auth: string;
  contract_version: string;
};

export type McpClientGrant = {
  group?: string;
  server_id: number;
  access_level: "all_tools" | "selected_tools";
  tool_names: string[];
};

export type McpHubClient = {
  slug: string;
  display_name: string;
  declared_name: string;
  declared_version: string;
  declared_family: string;
  status: "discovered" | "enabled" | "disabled";
  agents_enabled?: boolean;
  allowed_groups?: string[];
  granted_profiles?: string[];
  grant_count?: number;
  first_seen_at?: string;
  last_seen_at?: string;
};

export type McpServer = {
  id: number;
  name: string;
  status: string;
  template_id?: string | null;
};

export type McpTool = {
  id?: number;
  tool_name: string;
};

export type ServerAccessRule = {
  server_id: number;
  enabled: boolean;
  access_level: "all_tools" | "selected_tools";
  allowed_tool_names: string[];
};

export type HubAnalyticsClientRow = {
  slug: string;
  lists: number;
  calls: number;
  denials: number;
  errors: number;
  agent_calls: number;
  avg_duration_ms: number;
  finops?: HubAnalyticsFinopsRow;
};

export type HubAnalyticsFinopsRow = {
  slug: string;
  invocations: number;
  input_tokens: number;
  output_tokens: number;
  estimated_cost: number;
  avg_duration_ms: number;
};

export type HubAnalyticsSummary = {
  hours: number;
  active_clients: number;
  clients: HubAnalyticsClientRow[];
  totals: {
    lists: number;
    calls: number;
    denials: number;
    errors: number;
    agent_calls: number;
  };
  finops?: {
    invocations: number;
    input_tokens: number;
    output_tokens: number;
    estimated_cost: number;
    by_client: HubAnalyticsFinopsRow[];
  };
};

export type HubAnalyticsToolRow = {
  tool_name: string;
  slug: string;
  calls: number;
  denials: number;
  errors: number;
  avg_duration_ms: number;
};

export type HubAnalyticsTools = {
  hours: number;
  tools: HubAnalyticsToolRow[];
};

export type HubAnalyticsErrorEvent = {
  occurred_at: string;
  event_type?: string | null;
  slug: string;
  tool_name?: string | null;
  original_tool?: string | null;
  server_id?: number | null;
  phase: string;
  error_code?: string | null;
  reason?: string | null;
  duration_ms?: number | null;
  request_id?: string | null;
};

export type HubAnalyticsErrorCodeRow = {
  error_code: string;
  phase: string;
  count: number;
};

export type HubAnalyticsErrors = {
  hours: number;
  limit: number;
  by_code: HubAnalyticsErrorCodeRow[];
  events: HubAnalyticsErrorEvent[];
};

/** Full IdP profiles (GROUP_SCOPES); not short loom:group tags. */
export const LOOM_PROFILES = [
  "g-users-demo",
  "g-users-test",
  "g-users-strategics",
  "g-admins-demo",
  "g-admins-mcp",
  "g-admins-security",
  "g-admins-memory",
  "g-admins-a2a",
  "g-admins-registry",
] as const;

export const PROFILE_PLACEHOLDER = "";
