#!/usr/bin/env bash
# Smoke tests for Adaptive Networks deployment on otel-demo.
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

AUTH_HEADER="Authorization: ApiKey ${ES_API_KEY}"
PASS=0
FAIL=0

check() {
  local name="$1"
  shift
  if "$@"; then
    echo "PASS: $name"
    PASS=$((PASS + 1))
  else
    echo "FAIL: $name"
    FAIL=$((FAIL + 1))
  fi
}

check_indices() {
  for idx in adaptive-networks-remediation-queue adaptive-networks-incident-audit; do
    curl -sfS -H "$AUTH_HEADER" -H "Content-Type: application/json" \
      -X POST "${ES_URL}/${idx}/_search" -d '{"size":0}' >/dev/null 2>&1 || \
    curl -sfS -H "$AUTH_HEADER" -H "Content-Type: application/json" \
      -X POST "${ES_URL}/_search" -d "{\"size\":0,\"index\":\"${idx}\"}" >/dev/null
  done
}

check_agent() {
  curl -sfS -H "$AUTH_HEADER" -H "kbn-xsrf: true" \
    "${KIBANA_URL}/api/agent_builder/agents/adaptive-networks-analyst" >/dev/null
}

check_workflows() {
  local resp
  resp=$(curl -sfS -H "$AUTH_HEADER" -H "kbn-xsrf: true" \
    "${KIBANA_URL}/api/workflows" 2>/dev/null || \
    curl -sfS -H "$AUTH_HEADER" -H "kbn-xsrf: true" \
    -X POST "${KIBANA_URL}/api/workflows/search" -d '{"page":1,"size":50}')
  echo "$resp" | grep -q "Adaptive Networks"
}

check_alerts() {
  local resp
  resp=$(curl -sfS -H "$AUTH_HEADER" -H "kbn-xsrf: true" \
    "${KIBANA_URL}/api/alerting/rules/_find?per_page=10&filter=alert.attributes.tags:adaptive-networks")
  echo "$resp" | python3 -c 'import json,sys; d=json.load(sys.stdin); sys.exit(0 if d.get("total",0)>=4 else 1)'
}

check_esql_stream() {
  local body='{"query":"FROM logs.otel.adaptive-networks* | LIMIT 1"}'
  curl -sfS -H "$AUTH_HEADER" -H "Content-Type: application/json" \
    -X POST "${ES_URL}/_query?format=json" -d "$body" >/dev/null 2>&1 || \
  curl -sfS -H "$AUTH_HEADER" -H "Content-Type: application/json" \
    -X POST "${ES_URL}/_query?format=json" -d '{"query":"FROM logs* | WHERE service.name == \"network-controller\" | LIMIT 1"}' >/dev/null
}

check "Elasticsearch indices" check_indices
check "Agent Builder agent" check_agent
check "Kibana workflows" check_workflows
check "Alert rules (>=4)" check_alerts
check "Network log stream query" check_esql_stream

echo ""
echo "Results: ${PASS} passed, ${FAIL} failed"
[[ "$FAIL" -eq 0 ]]
