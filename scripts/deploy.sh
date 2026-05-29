#!/usr/bin/env bash
# Deploy Adaptive Networks assets to otel-demo (Elasticsearch + Kibana).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

: "${ES_URL:?Set ES_URL}"
: "${KIBANA_URL:?Set KIBANA_URL}"
: "${ES_API_KEY:?Set ES_API_KEY}"

NS="adaptive-networks"
AGENT_ID="adaptive-networks-analyst"
AUTH_HEADER="Authorization: ApiKey ${ES_API_KEY}"
KB_HEADERS=(-H "$AUTH_HEADER" -H "Content-Type: application/json" -H "kbn-xsrf: true")

log() { echo "[deploy] $*"; }

es_curl() {
  curl -sfS -H "$AUTH_HEADER" -H "Content-Type: application/json" "$@"
}

kb_curl() {
  curl -sfS "${KB_HEADERS[@]}" "$@"
}

# ── 1. Indices (bootstrap via index API — creates on first write) ─────────────
log "Creating audit/queue indices..."
for index in "${NS}-remediation-queue" "${NS}-remediation-audit" "${NS}-incident-audit"; do
  es_curl -X POST "${ES_URL}/${index}/_doc" -d "{\"@timestamp\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\",\"bootstrap\":true,\"status\":\"init\"}" >/dev/null 2>&1 || \
    log "Index bootstrap for ${index} may require first workflow write"
done

# ── 2. Stream fork ────────────────────────────────────────────────────────────
log "Forking logs.otel -> logs.otel.adaptive-networks..."
kb_curl -X POST "${KIBANA_URL}/api/streams/logs.otel/_fork" -d '{
  "stream": {"name": "logs.otel.adaptive-networks"},
  "where": {
    "field": "resource.attributes.service.name",
    "eq": "network-controller"
  }
}' >/dev/null 2>&1 || log "Stream fork may already exist (continuing)"

# ── 3. Workflows ──────────────────────────────────────────────────────────────
deploy_workflow() {
  local yaml_file="$1"
  local yaml_content
  yaml_content=$(python3 -c 'import json,sys; print(json.dumps({"yaml": sys.stdin.read()}))' < "$yaml_file")

  local resp http_code body
  resp=$(curl -sS -w "\n%{http_code}" "${KB_HEADERS[@]}" \
    -X POST "${KIBANA_URL}/api/workflows/workflow" \
    -d "$yaml_content" 2>/dev/null || true)
  http_code=$(echo "$resp" | tail -n1)
  body=$(echo "$resp" | sed '$d')

  if [[ "$http_code" == "404" || "$http_code" == "405" ]]; then
    resp=$(curl -sS -w "\n%{http_code}" "${KB_HEADERS[@]}" \
      -X POST "${KIBANA_URL}/api/workflows" \
      -d "$yaml_content")
    http_code=$(echo "$resp" | tail -n1)
    body=$(echo "$resp" | sed '$d')
  fi

  if [[ "$http_code" -ge 300 ]]; then
    echo "Workflow deploy failed ($yaml_file): HTTP $http_code" >&2
    echo "$body" >&2
    return 1
  fi

  echo "$body" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("id",""))'
}

log "Deploying workflows..."
REMEDIATION_WF_ID=$(deploy_workflow "${ROOT}/elastic_config/workflows/remediation_action.yaml")
INCIDENT_WF_ID=$(deploy_workflow "${ROOT}/elastic_config/workflows/network_incident_response.yaml")
log "  remediation_action: ${REMEDIATION_WF_ID}"
log "  network_incident_response: ${INCIDENT_WF_ID}"

# ── 4. Agent Builder tools ────────────────────────────────────────────────────
log "Deploying Agent Builder tools..."
python3 <<PY
import json, os, urllib.request

kibana = os.environ["KIBANA_URL"]
api_key = os.environ["ES_API_KEY"]
headers = {
    "Authorization": f"ApiKey {api_key}",
    "Content-Type": "application/json",
    "kbn-xsrf": "true",
}

with open("${ROOT}/elastic_config/tools/agent_tools.json") as f:
    tools = json.load(f)

# Add remediation workflow tool after workflows are deployed
tools.append({
    "id": "adaptive_networks_remediation_action",
    "type": "workflow",
    "description": "Execute remediation for simulated network faults. Queues action to remediation poller.",
    "configuration": {"workflow_id": "${REMEDIATION_WF_ID}"},
})

for tool in tools:
    tid = tool["id"]
    req = urllib.request.Request(
        f"{kibana}/api/agent_builder/tools/{tid}",
        headers=headers,
        method="DELETE",
    )
    try:
        urllib.request.urlopen(req)
    except Exception:
        pass

    req = urllib.request.Request(
        f"{kibana}/api/agent_builder/tools",
        data=json.dumps(tool).encode(),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        print(f"  tool {tid}: HTTP {resp.status}")
PY

# ── 5. Agent ──────────────────────────────────────────────────────────────────
log "Deploying Agent Builder agent ${AGENT_ID}..."
python3 <<PY
import json, os, urllib.request

kibana = os.environ["KIBANA_URL"]
api_key = os.environ["ES_API_KEY"]
headers = {
    "Authorization": f"ApiKey {api_key}",
    "Content-Type": "application/json",
    "kbn-xsrf": "true",
}

with open("${ROOT}/elastic_config/agents/network-analyst-prompt.txt") as f:
    instructions = f.read()

tool_ids = [
    "adaptive_networks_log_search",
    "adaptive_networks_fault_esql",
    "adaptive_networks_hybrid_correlation",
    "adaptive_networks_remediation_action",
    "platform.core.cases",
    "platform.core.resume_workflow_execution",
    "platform.core.get_workflow_execution_status",
]

agent_body = {
    "id": "${AGENT_ID}",
    "name": "Adaptive Networks: Infrastructure & Network Analyst",
    "description": "NOC analyst for simulated router/switch faults with hybrid otel-demo correlation.",
    "configuration": {
        "instructions": instructions,
        "tools": [{"tool_ids": tool_ids}],
    },
}

req = urllib.request.Request(
    f"{kibana}/api/agent_builder/agents/${AGENT_ID}",
    headers=headers,
    method="DELETE",
)
try:
    urllib.request.urlopen(req)
except Exception:
    pass

req = urllib.request.Request(
    f"{kibana}/api/agent_builder/agents",
    data=json.dumps(agent_body).encode(),
    headers=headers,
    method="POST",
)
with urllib.request.urlopen(req) as resp:
    print(f"  agent ${AGENT_ID}: HTTP {resp.status}")
PY

# ── 6. Alert rules ────────────────────────────────────────────────────────────
log "Deploying alert rules..."
python3 <<PY
import json, os, urllib.request

kibana = os.environ["KIBANA_URL"]
api_key = os.environ["ES_API_KEY"]
headers = {
    "Authorization": f"ApiKey {api_key}",
    "Content-Type": "application/json",
    "kbn-xsrf": "true",
}
ns = "${NS}"
incident_wf = "${INCIDENT_WF_ID}"

with open("${ROOT}/elastic_config/alerts/network_fault_rules.json") as f:
    rules = json.load(f)["rules"]

# Cleanup old rules by tag
for page in range(1, 5):
    req = urllib.request.Request(
        f"{kibana}/api/alerting/rules/_find?per_page=100&page={page}&filter=alert.attributes.tags:{ns}",
        headers=headers,
    )
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.load(resp)
    except Exception:
        break
    for rule in data.get("data", []):
        rid = rule.get("id")
        if rid:
            del_req = urllib.request.Request(
                f"{kibana}/api/alerting/rule/{rid}",
                headers=headers,
                method="DELETE",
            )
            try:
                urllib.request.urlopen(del_req)
            except Exception:
                pass
    if not data.get("data"):
        break

for r in rules:
    es_query = json.dumps({
        "query": {
            "bool": {
                "filter": [
                    {"range": {"@timestamp": {"gte": "now-1m"}}},
                    {"match_phrase": {"body.text": r["error_type"]}},
                    {"term": {"severity_text": "ERROR"}},
                ]
            }
        }
    })
    rule = {
        "name": r["name"],
        "rule_type_id": ".es-query",
        "consumer": "alerts",
        "tags": [ns, r["error_type"], r["remediation_action"], str(r["channel"]), r["severity"]],
        "schedule": {"interval": "1m"},
        "params": {
            "searchType": "esQuery",
            "esQuery": es_query,
            "index": ["logs*"],
            "timeField": "@timestamp",
            "threshold": [0],
            "thresholdComparator": ">",
            "size": 100,
            "timeWindowSize": 1,
            "timeWindowUnit": "m",
        },
        "actions": [{
            "group": "query matched",
            "id": "system-connector-.workflows",
            "frequency": {"summary": False, "notify_when": "onActiveAlert", "throttle": None},
            "params": {
                "subAction": "run",
                "subActionParams": {
                    "workflowId": incident_wf,
                    "inputs": {},
                },
            },
        }],
    }
    req = urllib.request.Request(
        f"{kibana}/api/alerting/rule",
        data=json.dumps(rule).encode(),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        print(f"  alert {r['name']}: HTTP {resp.status}")
PY

# ── 7. Dashboard ──────────────────────────────────────────────────────────────
log "Importing NOC dashboard..."
python3 "${ROOT}/scripts/create_dashboard.py" 2>/dev/null || \
  log "Dashboard import skipped (run: python3 scripts/create_dashboard.py)"

log "Deployment complete."
log "  Kibana: ${KIBANA_URL}"
log "  Agent:  ${AGENT_ID}"
log "  Workflow: ${INCIDENT_WF_ID}"
