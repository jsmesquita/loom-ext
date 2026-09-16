import { ApiError, apiFetch, getAuthToken, tryRefreshToken } from "@/api/client";
import type {
  HubAnalyticsErrors,
  HubAnalyticsSummary,
  HubAnalyticsTools,
  HubInfo,
  McpClientGrant,
  McpHubClient,
  McpServer,
  McpTool,
} from "./types";

/** Hub ops base (browser → mcp-hub directly; no Loom BFF proxy). */
const HUB_BASE =
  (import.meta.env.VITE_MCP_HUB_URL as string | undefined)?.replace(/\/$/, "") ||
  "http://127.0.0.1:8790";

async function hubFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    Accept: "application/json",
    ...(options?.headers as Record<string, string>),
  };
  const token = getAuthToken();
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }

  const url = `${HUB_BASE}${path.startsWith("/") ? path : `/${path}`}`;
  let response = await fetch(url, { ...options, headers });

  if (response.status === 401) {
    const refreshed = await tryRefreshToken();
    if (refreshed) {
      headers.Authorization = `Bearer ${refreshed}`;
      response = await fetch(url, { ...options, headers });
    }
  }

  if (!response.ok) {
    let detail = `HTTP ${response.status}`;
    try {
      const body = (await response.json()) as {
        detail?: string;
        error?: { message?: string };
      };
      if (typeof body.detail === "string") {
        detail = body.detail;
      } else if (body.error?.message) {
        detail = body.error.message;
      }
    } catch {
      /* ignore */
    }
    throw new ApiError(response.status, detail);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return response.json() as Promise<T>;
}

export async function fetchHubInfo(): Promise<HubInfo> {
  return hubFetch<HubInfo>("/v1/info");
}

export async function fetchMcpClients(): Promise<McpHubClient[]> {
  const data = await hubFetch<{ clients: McpHubClient[] }>("/v1/clients");
  return data.clients || [];
}

export async function fetchActiveMcpServers(): Promise<McpServer[]> {
  const list = await apiFetch<McpServer[]>("/api/mcp/servers");
  return (list || []).filter((s) => s.status === "active");
}

export async function fetchServerTools(serverId: number): Promise<McpTool[]> {
  const tools = await apiFetch<McpTool[]>(`/api/mcp/servers/${serverId}/tools`);
  return tools || [];
}

export async function fetchProfileGrants(
  slug: string,
  group: string,
): Promise<{ group: string; grants: McpClientGrant[] }> {
  return hubFetch<{ group: string; grants: McpClientGrant[] }>(
    `/v1/clients/${encodeURIComponent(slug)}/profile-grants?group=${encodeURIComponent(group)}`,
  );
}

export async function putProfileGrants(
  slug: string,
  group: string,
  grants: McpClientGrant[],
): Promise<void> {
  await hubFetch(`/v1/clients/${encodeURIComponent(slug)}/profile-grants`, {
    method: "PUT",
    body: JSON.stringify({ group, grants }),
  });
}

export async function patchMcpClient(
  slug: string,
  body: {
    status?: "enabled" | "disabled";
    agents_enabled?: boolean;
  },
): Promise<void> {
  await hubFetch(`/v1/clients/${encodeURIComponent(slug)}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export async function deleteMcpClient(slug: string): Promise<void> {
  await hubFetch(`/v1/clients/${encodeURIComponent(slug)}`, {
    method: "DELETE",
  });
}

export async function fetchAnalyticsSummary(hours = 24): Promise<HubAnalyticsSummary> {
  return hubFetch<HubAnalyticsSummary>(`/v1/analytics/summary?hours=${hours}`);
}

export async function fetchAnalyticsTools(hours = 24): Promise<HubAnalyticsTools> {
  return hubFetch<HubAnalyticsTools>(`/v1/analytics/tools?hours=${hours}`);
}

export async function fetchAnalyticsErrors(
  hours = 24,
  limit = 100,
): Promise<HubAnalyticsErrors> {
  return hubFetch<HubAnalyticsErrors>(
    `/v1/analytics/errors?hours=${hours}&limit=${limit}`,
  );
}
