# Adaptive Networks — Vercel Demo UI

Interactive demo: pick a simulated network fault, inject OTLP logs to otel-demo, and watch the **Network Incident Response** Kibana workflow execute in real time.

## Deploy to Vercel

1. Import the repo in [Vercel](https://vercel.com/new)
2. Set **Root Directory** to `web`
3. Add environment variables (Project → Settings → Environment Variables):

| Variable | Required | Description |
|----------|----------|-------------|
| `KIBANA_URL` | Yes | e.g. `https://otel-demo-a5630c.kb.us-east-1.aws.elastic.cloud` |
| `ES_API_KEY` | Yes | Elasticsearch API key (Kibana + ingest) |
| `OTLP_ENDPOINT` | Yes | e.g. `https://otel-demo-a5630c.ingest.us-east-1.aws.elastic.cloud` |
| `INCIDENT_WORKFLOW_NAME` | No | Default: `Adaptive Networks Network Incident Response` |
| `INCIDENT_WORKFLOW_ID` | No | Pin workflow ID if auto-discovery is insufficient |
| `DEMO_API_SECRET` | No | If set, require `x-demo-secret` header on `/api/inject` |

4. Deploy — Vercel runs `npm run build` in `web/`

## Local development

```bash
cd web
cp .env.example .env.local   # fill in credentials
npm install
npm run dev
```

Open http://localhost:3000

## How it works

1. **Inject** — `POST /api/inject` sends 6 ERROR logs via OTLP with the Cisco mnemonic for the selected channel
2. **Alert** — Kibana alert rules (1 min interval) match `body.text` + `severity_text: ERROR`
3. **Workflow** — Alert triggers `Adaptive Networks Network Incident Response`
4. **Poll** — UI polls `/api/executions?since=…` every 3s and renders `stepExecutions`
5. **HITL** — High-severity faults pause at `hitl_approval`; link opens Kibana to approve

## Prerequisites

Run `./scripts/deploy.sh` from the repo root first so workflows, alerts, and Agent Builder assets exist on otel-demo.
