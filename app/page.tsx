"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { FAULT_CHANNELS, INCIDENT_STEPS } from "@/lib/channels";
import type { DemoConfig, WorkflowExecution } from "@/lib/types";

type Phase =
  | "idle"
  | "injecting"
  | "waiting"
  | "running"
  | "hitl"
  | "done"
  | "error";

interface ExecutionSummary {
  id: string;
  workflowId: string;
  status: string;
  startedAt?: string;
  finishedAt?: string;
  currentNodeId?: string;
  kibanaUrl: string;
  waitingForHuman?: boolean;
  stepExecutions?: Array<{
    stepId: string;
    stepType: string;
    status: string;
    executionTimeMs?: number;
  }>;
}

function statusClass(status: string) {
  if (status === "completed") return "status-ok";
  if (status === "failed") return "status-bad";
  if (status === "running") return "status-run";
  return "status-wait";
}

export default function DemoPage() {
  const [config, setConfig] = useState<DemoConfig | null>(null);
  const [selected, setSelected] = useState<number | null>(null);
  const [phase, setPhase] = useState<Phase>("idle");
  const [message, setMessage] = useState("");
  const [injectedAt, setInjectedAt] = useState<string | null>(null);
  const [execution, setExecution] = useState<ExecutionSummary | null>(null);
  const [pollCount, setPollCount] = useState(0);

  useEffect(() => {
    fetch("/api/config")
      .then((r) => r.json())
      .then(setConfig)
      .catch(() => setConfig(null));
  }, []);

  const pollExecutions = useCallback(async (since: string) => {
    const res = await fetch(`/api/executions?since=${encodeURIComponent(since)}`);
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Poll failed");
    return (data.executions ?? []) as ExecutionSummary[];
  }, []);

  useEffect(() => {
    if (!injectedAt || phase === "idle" || phase === "error" || phase === "done") return;

    const interval = setInterval(async () => {
      try {
        setPollCount((c) => c + 1);
        const executions = await pollExecutions(injectedAt);
        if (!executions.length) {
          setPhase("waiting");
          setMessage(
            `Fault logs ingested. Waiting for Kibana alert rule evaluation (runs every ~60s, 5m lookback window)… (${Math.max(0, pollCount) * 3}s elapsed)`
          );
          return;
        }

        const latest = executions[0];
        setExecution(latest);

        if (latest.waitingForHuman) {
          setPhase("hitl");
          setMessage("Workflow paused for human approval in Kibana (waitForInput).");
        } else if (latest.status === "completed") {
          setPhase("done");
          setMessage("Workflow completed successfully.");
        } else if (latest.status === "failed") {
          setPhase("error");
          setMessage("Workflow failed — open Kibana for details.");
        } else {
          setPhase("running");
          setMessage("Elastic workflow is running…");
        }
      } catch (err) {
        setPhase("error");
        setMessage(err instanceof Error ? err.message : "Polling error");
      }
    }, 3000);

    return () => clearInterval(interval);
  }, [injectedAt, phase, pollExecutions]);

  const inject = async (channel: number) => {
    setSelected(channel);
    setPhase("injecting");
    setMessage("Sending simulated fault logs to otel-demo…");
    setExecution(null);
    setPollCount(0);

    try {
      const res = await fetch("/api/inject", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ channel }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Inject failed");

      setInjectedAt(data.injectedAt);
      setPhase("waiting");
      setMessage(data.message);
    } catch (err) {
      setPhase("error");
      setMessage(err instanceof Error ? err.message : "Inject failed");
    }
  };

  const selectedFault = useMemo(
    () => FAULT_CHANNELS.find((c) => c.channel === selected),
    [selected]
  );

  return (
    <main className="page">
      <header className="hero">
        <p className="eyebrow">Elastic Observability · Agent Builder · Workflows</p>
        <h1>Adaptive Networks Demo</h1>
        <p className="lede">
          Inject a simulated router or switch fault, then watch the real{" "}
          <strong>Network Incident Response</strong> workflow run on otel-demo.
        </p>
        {config && (
          <p className="meta">
            Kibana:{" "}
            <a href={config.kibanaUrl} target="_blank" rel="noopener noreferrer">
              {config.kibanaUrl.replace("https://", "")}
            </a>
            {" · "}Alert interval {config.alertIntervalHint}
          </p>
        )}
      </header>

      <section className="panel">
        <h2>1 · Choose a network fault</h2>
        <div className="grid">
          {FAULT_CHANNELS.map((fault) => (
            <button
              key={fault.channel}
              className={`fault-card ${selected === fault.channel ? "selected" : ""}`}
              onClick={() => inject(fault.channel)}
              disabled={phase === "injecting"}
            >
              <div className="fault-head">
                <span className="ch">CH{String(fault.channel).padStart(2, "0")}</span>
                <span className={`sev sev-${fault.severity}`}>{fault.severity}</span>
              </div>
              <h3>{fault.name}</h3>
              <p>{fault.description}</p>
              <code>{fault.errorType}</code>
            </button>
          ))}
        </div>
      </section>

      <section className="panel">
        <h2>2 · Workflow progress</h2>
        <div className={`timeline ${phase}`}>
          {[
            ["injecting", "Inject logs"],
            ["waiting", "Alert fires (~60s)"],
            ["running", "Workflow runs"],
            ["hitl", "Human approval"],
            ["done", "Complete"],
          ].map(([key, label]) => (
            <div
              key={key}
              className={`tl-step ${
                phase === key ||
                (phase === "running" && key === "waiting") ||
                (phase === "done" && ["running", "waiting", "injecting"].includes(key))
                  ? "active"
                  : ""
              } ${phase === "done" && key === "done" ? "done" : ""}`}
            >
              <span className="dot" />
              <span>{label}</span>
            </div>
          ))}
        </div>

        <div className="status-box">
          <strong>Status:</strong> {message || "Select a fault to begin."}
          {pollCount > 0 && phase === "waiting" && (
            <span className="poll"> · polling ({pollCount})</span>
          )}
        </div>

        {selectedFault && (
          <p className="hint">
            {selectedFault.severity === "high"
              ? "High severity: workflow will pause at waitForInput — approve remediation in Kibana."
              : "Low severity: workflow auto-remediates after Agent Builder RCA."}
          </p>
        )}

        {execution && (
          <div className="execution">
            <div className="exec-head">
              <div>
                <h3>Execution {execution.id.slice(0, 8)}…</h3>
                <p>
                  <span className={statusClass(execution.status)}>{execution.status}</span>
                  {execution.startedAt && (
                    <span className="muted"> · started {new Date(execution.startedAt).toLocaleTimeString()}</span>
                  )}
                </p>
              </div>
              <a className="btn" href={execution.kibanaUrl} target="_blank" rel="noopener noreferrer">
                Open in Kibana
              </a>
            </div>

            <ul className="steps">
              {(execution.stepExecutions ?? []).map((step) => (
                <li key={step.stepId + step.status}>
                  <span className={statusClass(step.status)}>{step.status}</span>
                  <code>{step.stepId}</code>
                  <span className="muted">{step.stepType}</span>
                  {step.executionTimeMs != null && (
                    <span className="muted">{step.executionTimeMs}ms</span>
                  )}
                </li>
              ))}
            </ul>

            {phase === "hitl" && (
              <div className="hitl-banner">
                Paused at <code>hitl_approval</code> — open Kibana to approve or reject remediation.
              </div>
            )}
          </div>
        )}

        {!execution && phase === "waiting" && (
          <ul className="expected-steps">
            {INCIDENT_STEPS.map((step) => (
              <li key={step}>
                <span className="dot pending" /> {step}
              </li>
            ))}
          </ul>
        )}
      </section>

      <footer className="footer">
        <a href="https://github.com/poulsbopete/adaptive-networks" target="_blank" rel="noopener noreferrer">
          Source on GitHub
        </a>
        {" · "}
        <a href="https://poulsbopete.github.io/adaptive-networks/" target="_blank" rel="noopener noreferrer">
          Slides
        </a>
      </footer>

      <style jsx>{`
        .page {
          max-width: 1100px;
          margin: 0 auto;
          padding: 2rem 1.25rem 4rem;
        }
        .hero {
          margin-bottom: 2rem;
        }
        .eyebrow {
          color: var(--accent);
          font-size: 0.8rem;
          font-weight: 600;
          letter-spacing: 0.08em;
          text-transform: uppercase;
        }
        h1 {
          font-size: clamp(2rem, 5vw, 3rem);
          margin: 0.2rem 0;
          letter-spacing: -0.03em;
        }
        .lede {
          color: var(--muted);
          max-width: 720px;
          line-height: 1.6;
        }
        .meta {
          font-size: 0.85rem;
          color: var(--muted);
        }
        .panel {
          background: var(--panel);
          border: 1px solid var(--border);
          border-radius: 16px;
          padding: 1.25rem 1.5rem 1.5rem;
          margin-bottom: 1.25rem;
        }
        .panel h2 {
          margin: 0 0 1rem;
          font-size: 1rem;
          color: var(--accent);
        }
        .grid {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
          gap: 0.85rem;
        }
        .fault-card {
          text-align: left;
          background: rgba(0, 0, 0, 0.2);
          border: 1px solid var(--border);
          border-radius: 12px;
          padding: 1rem;
          color: inherit;
          cursor: pointer;
          transition: border-color 0.15s, transform 0.15s;
        }
        .fault-card:hover:not(:disabled) {
          border-color: var(--accent);
          transform: translateY(-2px);
        }
        .fault-card.selected {
          border-color: var(--accent);
          box-shadow: 0 0 0 1px var(--accent);
        }
        .fault-card:disabled {
          opacity: 0.6;
          cursor: wait;
        }
        .fault-head {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 0.5rem;
        }
        .ch {
          font-weight: 700;
          color: var(--accent);
        }
        .sev {
          font-size: 0.7rem;
          font-weight: 700;
          text-transform: uppercase;
          padding: 0.15rem 0.5rem;
          border-radius: 999px;
        }
        .sev-low {
          background: rgba(110, 231, 183, 0.15);
          color: var(--low);
        }
        .sev-high {
          background: rgba(252, 165, 165, 0.15);
          color: var(--high);
        }
        .fault-card h3 {
          margin: 0 0 0.35rem;
          font-size: 0.95rem;
        }
        .fault-card p {
          margin: 0 0 0.5rem;
          font-size: 0.8rem;
          color: var(--muted);
          line-height: 1.4;
        }
        .timeline {
          display: flex;
          flex-wrap: wrap;
          gap: 0.5rem 1rem;
          margin-bottom: 1rem;
        }
        .tl-step {
          display: flex;
          align-items: center;
          gap: 0.4rem;
          font-size: 0.78rem;
          color: var(--muted);
        }
        .tl-step.active {
          color: var(--text);
          font-weight: 600;
        }
        .tl-step.done .dot {
          background: var(--low);
        }
        .dot {
          width: 8px;
          height: 8px;
          border-radius: 50%;
          background: var(--border);
        }
        .tl-step.active .dot {
          background: var(--accent);
        }
        .status-box {
          background: rgba(0, 0, 0, 0.25);
          border-radius: 10px;
          padding: 0.85rem 1rem;
          font-size: 0.9rem;
          line-height: 1.5;
        }
        .poll {
          color: var(--muted);
        }
        .hint {
          font-size: 0.82rem;
          color: var(--muted);
          margin: 0.75rem 0 0;
        }
        .execution {
          margin-top: 1rem;
          border-top: 1px solid var(--border);
          padding-top: 1rem;
        }
        .exec-head {
          display: flex;
          justify-content: space-between;
          align-items: flex-start;
          gap: 1rem;
          flex-wrap: wrap;
        }
        .exec-head h3 {
          margin: 0;
          font-size: 0.95rem;
        }
        .exec-head p {
          margin: 0.25rem 0 0;
          font-size: 0.82rem;
        }
        .btn {
          display: inline-block;
          background: var(--accent-dim);
          border: 1px solid rgba(0, 191, 179, 0.4);
          color: var(--accent);
          padding: 0.45rem 0.85rem;
          border-radius: 8px;
          font-size: 0.82rem;
          font-weight: 600;
          text-decoration: none;
        }
        .steps {
          list-style: none;
          padding: 0;
          margin: 1rem 0 0;
        }
        .steps li {
          display: grid;
          grid-template-columns: 90px 1fr auto auto;
          gap: 0.75rem;
          align-items: center;
          padding: 0.45rem 0;
          border-bottom: 1px solid var(--border);
          font-size: 0.78rem;
        }
        .expected-steps {
          list-style: none;
          padding: 0;
          margin: 1rem 0 0;
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
          gap: 0.35rem 1rem;
        }
        .expected-steps li {
          font-size: 0.78rem;
          color: var(--muted);
          display: flex;
          align-items: center;
          gap: 0.45rem;
        }
        .dot.pending {
          width: 6px;
          height: 6px;
          border-radius: 50%;
          background: var(--border);
        }
        :global(.status-ok) {
          color: var(--low);
          font-weight: 600;
          text-transform: capitalize;
        }
        :global(.status-bad) {
          color: var(--high);
          font-weight: 600;
          text-transform: capitalize;
        }
        :global(.status-run) {
          color: var(--warn);
          font-weight: 600;
          text-transform: capitalize;
        }
        :global(.status-wait) {
          color: var(--muted);
          text-transform: capitalize;
        }
        :global(.muted) {
          color: var(--muted);
        }
        .hitl-banner {
          margin-top: 1rem;
          padding: 0.75rem 1rem;
          border-radius: 10px;
          background: rgba(251, 191, 36, 0.12);
          border: 1px solid rgba(251, 191, 36, 0.35);
          color: #fde68a;
          font-size: 0.85rem;
        }
        .footer {
          text-align: center;
          color: var(--muted);
          font-size: 0.82rem;
          margin-top: 2rem;
        }
      `}</style>
    </main>
  );
}
