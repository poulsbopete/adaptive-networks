# Adaptive Networks

Simulated router/switch network operations on [otel-demo](https://otel-demo-a5630c.kb.us-east-1.aws.elastic.cloud/) with Elastic Agent Builder, Kibana Workflows, and human-in-the-loop remediation for high-severity faults.

**Presentation:** [GitHub Pages slides](https://poulsbopete.github.io/adaptive-networks/) (Reveal.js deck — use arrow keys or swipe to navigate)

**Interactive demo:** Vercel UI — inject faults and watch Elastic workflows run (see [Vercel demo UI](#vercel-demo-ui) below)

## Architecture

- **Simulator** emits Cisco-style syslog and SNMP-style metrics via OTLP to `logs.otel` (forked to `logs.otel.adaptive-networks`)
- **Alert rules** detect fault mnemonics and trigger the **Network Incident Response** workflow
- **Agent Builder** (`adaptive-networks-analyst`) performs RCA and invokes remediation
- **Low severity** (MAC flap, interface errors): auto-remediate after RCA
- **High severity** (STP, BGP): `waitForInput` human approval before remediation
- **Hybrid correlation** enriches cases with otel-demo K8s events and VPC flow data

## Quick start

```bash
cp .env.example .env   # set ES_URL, KIBANA_URL, ES_API_KEY, OTLP_ENDPOINT
pip install -r simulator/requirements.txt
chmod +x scripts/*.sh simulator/*.py

# Deploy to otel-demo
./scripts/deploy.sh

# Terminal 1: baseline telemetry
python simulator/network_controller.py

# Terminal 2: remediation poller
python simulator/remediation_poller.py

# Inject faults
python simulator/chaos_inject.py on 1    # low — MAC flap (auto)
python simulator/chaos_inject.py on 3    # high — BGP (HITL)
python simulator/chaos_inject.py list
python simulator/chaos_inject.py clear
```

Validate deployment:

```bash
./scripts/validate.sh
```

## Demo runbook (~10 minutes)

1. **Deploy** — `./scripts/deploy.sh` and confirm `./scripts/validate.sh` passes
2. **Start simulator + poller** — see Quick start
3. **Low-risk path** — `python simulator/chaos_inject.py on 1`
   - Alert fires within ~1 minute
   - Workflow runs RCA → Case → auto remediation → poller clears CH01 → Case closed
4. **High-risk path** — `python simulator/chaos_inject.py on 3`
   - Workflow pauses at **waitForInput** in Kibana → Observability → Workflows → execution UI
   - Approve remediation; agent queues fix; poller clears CH03
5. **Review** — Case comments show hybrid correlation + Agent Builder conversation link
6. **Dashboard** — open **Adaptive Networks NOC** in Kibana

## Fault channels

| CH | Fault | Severity | Remediation |
|----|-------|----------|-------------|
| 1 | `SW_MATM-4-MACFLAP_NOTIF` | low | `clear_mac_table` |
| 2 | `SPANTREE-2-TOPO_CHANGE` | high | `reset_spanning_tree` |
| 3 | `BGP-3-NOTIFICATION` | high | `reset_bgp_session` |
| 4 | `INTF-4-INPUTERR-SPIKE` | low | `bounce_interface` |

## Kibana links

- [Kibana home](https://otel-demo-a5630c.kb.us-east-1.aws.elastic.cloud/)
- Workflows: Observability → Workflows
- Agent Builder: Agent Builder → `adaptive-networks-analyst`
- Cases: Observability → Cases (filter tag `adaptive-networks`)

## Repository layout

```
app/                      # Next.js demo UI (Vercel)
lib/                      # demo API helpers
channel_registry.yaml     # fault definitions
simulator/                # OTLP emitter, chaos CLI, remediation poller
elastic_config/           # workflows, alerts, agent, dashboard
scripts/deploy.sh         # bootstrap otel-demo
scripts/validate.sh       # smoke tests
```

## Vercel demo UI

Deploy the Next.js app from the **repo root** (default Root Directory `.`).

1. Import the repo in [Vercel](https://vercel.com/new)
2. Framework preset: **Next.js** (auto-detected from root `package.json`)
3. Add environment variables:

| Variable | Required | Description |
|----------|----------|-------------|
| `KIBANA_URL` | Yes | e.g. `https://otel-demo-a5630c.kb.us-east-1.aws.elastic.cloud` |
| `ES_API_KEY` | Yes | Elasticsearch API key (Kibana + ingest) |
| `OTLP_ENDPOINT` | Yes | e.g. `https://otel-demo-a5630c.ingest.us-east-1.aws.elastic.cloud` |
| `INCIDENT_WORKFLOW_NAME` | No | Default: `Adaptive Networks Network Incident Response` |
| `INCIDENT_WORKFLOW_ID` | No | Pin workflow ID if auto-discovery is insufficient |
| `DEMO_API_SECRET` | No | If set, require `x-demo-secret` header on `/api/inject` |

4. Deploy

Local dev: `npm install && npm run dev` (open http://localhost:3000). Copy demo vars from [`.env.example`](.env.example).

If your Vercel project was previously configured with **Root Directory = `web`**, reset it to `.` (repo root) and redeploy.

## Environment variables

| Variable | Description |
|----------|-------------|
| `ES_URL` | Elasticsearch endpoint |
| `KIBANA_URL` | Kibana endpoint |
| `ES_API_KEY` | API key (Elasticsearch + Kibana) |
| `OTLP_ENDPOINT` | Ingest URL (no path suffix) |

## Notes

- Log search must use **`body.text`**, not `body` (OTLP passthrough mapping)
- Alert workflow metadata is encoded in rule **tags** (inputs from alerts resolve blank)
- Remediation queue index: `adaptive-networks-remediation-queue`
