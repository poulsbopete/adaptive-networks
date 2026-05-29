#!/usr/bin/env bash
# Redeploy Adaptive Networks alert rules only (no workflow/agent churn).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck disable=SC1091
[[ -f "${ROOT}/.env" ]] && set -a && source "${ROOT}/.env" && set +a

: "${KIBANA_URL:?Set KIBANA_URL}"
: "${ES_API_KEY:?Set ES_API_KEY}"
NS="${NAMESPACE:-adaptive-networks}"

INCIDENT_WF_ID="${INCIDENT_WORKFLOW_ID:-}"
if [[ -z "${INCIDENT_WF_ID}" ]]; then
  INCIDENT_WF_ID="$(python3 <<'PY'
import json, os, urllib.request
kibana = os.environ["KIBANA_URL"].rstrip("/")
headers = {
    "Authorization": f"ApiKey {os.environ['ES_API_KEY']}",
    "Content-Type": "application/json",
    "kbn-xsrf": "true",
}
req = urllib.request.Request(f"{kibana}/api/workflows?page=1&size=100", headers=headers)
with urllib.request.urlopen(req) as resp:
    data = json.load(resp)
name = "Adaptive Networks Network Incident Response"
matches = [w for w in data.get("results", []) if w.get("name") == name]
pref = [w for w in matches if str(w.get("id", "")).startswith("adaptive-networks-network-incident-response")]
pool = pref or matches
if not pool:
    raise SystemExit(f"Workflow not found: {name}")
pool.sort(key=lambda w: int(str(w["id"]).split("-")[-1]) if str(w["id"]).split("-")[-1].isdigit() else 0)
print(pool[-1]["id"])
PY
)"
fi

echo "Using incident workflow: ${INCIDENT_WF_ID}"

python3 <<PY
import json, os, urllib.request

kibana = os.environ["KIBANA_URL"].rstrip("/")
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
                print(f"  deleted old rule: {rule.get('name')}")
            except Exception:
                pass
    if not data.get("data"):
        break

for r in rules:
    es_query = json.dumps({
        "query": {
            "bool": {
                "filter": [
                    {"term": {"service.name": "network-controller"}},
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
            "timeWindowSize": 5,
            "timeWindowUnit": "m",
            "excludeHitsFromPreviousRun": False,
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
        print(f"  created alert {r['name']}: HTTP {resp.status} -> workflow {incident_wf}")
PY

echo "Alert rules redeployed."
