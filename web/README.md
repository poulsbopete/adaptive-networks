# Adaptive Networks — Vercel Demo UI

Interactive demo: pick a simulated network fault, inject OTLP logs to otel-demo, and watch the **Network Incident Response** Kibana workflow execute in real time.

## Deploy to Vercel

### Option A (recommended): set Root Directory to `web`

1. Import the repo in [Vercel](https://vercel.com/new)
2. **Project Settings → General → Root Directory → `web`**
3. Framework preset: **Next.js** (auto-detected)
4. Add environment variables (see table below)
5. Deploy

### Option B: deploy from repo root

If Root Directory is left as `.`, the root [`vercel.json`](../vercel.json) builds the app in `web/` via `npm run build --prefix web`. Do **not** leave a Python `requirements.txt` at the repo root (simulator deps live in [`simulator/requirements.txt`](../simulator/requirements.txt)).

### Environment variables

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

Or from repo root: `npm install --prefix web && npm run dev --prefix web`

Open http://localhost:3000

## How it works

1. **Inject** — `POST /api/inject` sends 6 ERROR logs via OTLP with the Cisco mnemonic for the selected channel
2. **Alert** — Kibana alert rules (1 min interval) match `body.text` + `severity_text: ERROR`
3. **Workflow** — Alert triggers `Adaptive Networks Network Incident Response`
4. **Poll** — UI polls `/api/executions?since=…` every 3s and renders `stepExecutions`
5. **HITL** — High-severity faults pause at `hitl_approval`; link opens Kibana to approve

## Prerequisites

Run `./scripts/deploy.sh` from the repo root first so workflows, alerts, and Agent Builder assets exist on otel-demo.
