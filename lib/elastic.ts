const KIBANA_URL = process.env.KIBANA_URL?.replace(/\/$/, "") ?? "";
const ES_API_KEY = process.env.ES_API_KEY ?? "";
const INCIDENT_WORKFLOW_NAME =
  process.env.INCIDENT_WORKFLOW_NAME ?? "Adaptive Networks Network Incident Response";
const INCIDENT_WORKFLOW_ID = process.env.INCIDENT_WORKFLOW_ID ?? "";

export function requireElasticConfig() {
  if (!KIBANA_URL || !ES_API_KEY) {
    throw new Error("KIBANA_URL and ES_API_KEY must be configured");
  }
  return { kibanaUrl: KIBANA_URL, apiKey: ES_API_KEY };
}

function kibanaHeaders(): HeadersInit {
  const { apiKey } = requireElasticConfig();
  return {
    Authorization: `ApiKey ${apiKey}`,
    "Content-Type": "application/json",
    "kbn-xsrf": "true",
    "x-elastic-internal-origin": "kibana",
  };
}

async function kibanaFetch(path: string, init?: RequestInit) {
  const { kibanaUrl } = requireElasticConfig();
  const res = await fetch(`${kibanaUrl}${path}`, {
    ...init,
    headers: { ...kibanaHeaders(), ...(init?.headers ?? {}) },
    cache: "no-store",
  });
  const text = await res.text();
  let body: unknown = null;
  try {
    body = text ? JSON.parse(text) : null;
  } catch {
    body = text;
  }
  if (!res.ok) {
    const msg =
      typeof body === "object" && body && "message" in body
        ? String((body as { message: string }).message)
        : text.slice(0, 300);
    throw new Error(`Kibana ${path} failed (${res.status}): ${msg}`);
  }
  return body;
}

export async function resolveIncidentWorkflowId(): Promise<string> {
  if (INCIDENT_WORKFLOW_ID) return INCIDENT_WORKFLOW_ID;

  const data = (await kibanaFetch("/api/workflows?page=1&size=100")) as {
    results?: Array<{ id: string; name: string }>;
  };
  const matches = (data.results ?? []).filter((w) => w.name === INCIDENT_WORKFLOW_NAME);
  if (!matches.length) {
    throw new Error(`Workflow not found: ${INCIDENT_WORKFLOW_NAME}`);
  }

  const prefixed = matches.filter((w) => w.id.startsWith("adaptive-networks-network-incident-response"));
  const pool = prefixed.length ? prefixed : matches;
  pool.sort((a, b) => {
    const suffix = (id: string) => {
      const part = id.split("-").pop() ?? "0";
      const n = Number(part);
      return Number.isFinite(n) ? n : 0;
    };
    return suffix(a.id) - suffix(b.id);
  });
  return pool[pool.length - 1].id;
}

export async function listWorkflowExecutions(
  workflowId: string,
  page = 1,
  size = 10
) {
  return kibanaFetch(
    `/api/workflows/workflow/${encodeURIComponent(workflowId)}/executions?page=${page}&size=${size}`
  ) as Promise<{
    results: Array<{ id: string; status: string; startedAt?: string; finishedAt?: string }>;
    total: number;
  }>;
}

export async function getWorkflowExecution(executionId: string) {
  return kibanaFetch(
    `/api/workflows/executions/${encodeURIComponent(executionId)}`
  ) as Promise<import("./types").WorkflowExecution>;
}

export function executionDeepLink(executionId: string, workflowId: string) {
  const { kibanaUrl } = requireElasticConfig();
  return `${kibanaUrl}/app/workflows/workflow/${encodeURIComponent(workflowId)}/run/${encodeURIComponent(executionId)}`;
}

export function casesDeepLink() {
  const { kibanaUrl } = requireElasticConfig();
  return `${kibanaUrl}/app/observability/cases?tags=adaptive-networks`;
}

export function getPublicConfig() {
  const { kibanaUrl } = requireElasticConfig();
  return {
    kibanaUrl,
    workflowName: INCIDENT_WORKFLOW_NAME,
    workflowId: INCIDENT_WORKFLOW_ID || null,
    alertIntervalHint: "~60 seconds",
  };
}

export function assertDemoAuth(request: Request) {
  const secret = process.env.DEMO_API_SECRET;
  if (!secret) return;
  const header = request.headers.get("x-demo-secret");
  if (header !== secret) {
    throw new Error("Unauthorized");
  }
}
