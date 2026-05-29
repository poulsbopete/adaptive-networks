import { FAULT_CHANNELS } from "./channels";

const OTLP_ENDPOINT = process.env.OTLP_ENDPOINT?.replace(/\/$/, "") ?? "";
const ES_API_KEY = process.env.ES_API_KEY ?? "";

const INTERFACES = [
  "GigabitEthernet0/0/0",
  "GigabitEthernet0/0/1",
  "TenGigabitEthernet1/0/1",
  "Vlan100",
];

function formatAttrs(attrs: Record<string, string | number | boolean>) {
  return Object.entries(attrs).map(([key, value]) => ({
    key,
    value:
      typeof value === "boolean"
        ? { boolValue: value }
        : typeof value === "number"
          ? { doubleValue: value }
          : { stringValue: String(value) },
  }));
}

function randMac() {
  const arr = new Uint8Array(6);
  crypto.getRandomValues(arr);
  return Array.from(arr, (b) => b.toString(16).padStart(2, "0")).join(":");
}

function faultMessage(channel: number): string {
  const iface = INTERFACES[channel % INTERFACES.length];
  switch (channel) {
    case 1:
      return `%SW_MATM-4-MACFLAP_NOTIF: Host ${randMac()} in vlan 133 is flapping between port GigabitEthernet0/0/0 and port TenGigabitEthernet1/0/1, 18 moves in 120s`;
    case 2:
      return `%SPANTREE-2-TOPO_CHANGE: Topology Change received on VLAN 100 instance 0 from bridge aabb.ccdd.eeff via port ${iface}, 12 TCN BPDUs in 45s`;
    case 3:
      return `%BGP-3-NOTIFICATION: Neighbor 10.0.0.42 (AS 64512) sent NOTIFICATION 4/0 (Hold Timer Expired), 7 transitions in 120s, last state Idle`;
    case 4:
      return `%INTF-4-INPUTERR-SPIKE: Interface ${iface} input errors 240 crc_errors 35 threshold exceeded in 60s`;
    default:
      throw new Error(`Unknown channel ${channel}`);
  }
}

function buildResource() {
  return {
    attributes: formatAttrs({
      "service.name": "network-controller",
      "service.namespace": "adaptive-networks",
      "deployment.environment": "adaptive-networks",
      "host.name": "network-controller-core-sw01",
      "cloud.provider": "aws",
      "cloud.region": "us-east-1",
      "data_stream.type": "logs",
      "data_stream.dataset": "generic",
      "data_stream.namespace": "default",
      "elasticsearch.index": "logs.otel",
    }),
  };
}

function buildLogRecord(channel: number, message: string, offsetMs = 0) {
  const ch = FAULT_CHANNELS.find((c) => c.channel === channel)!;
  return {
    timeUnixNano: String((Date.now() + offsetMs) * 1_000_000),
    severityText: "ERROR",
    severityNumber: 17,
    body: { stringValue: message },
    attributes: formatAttrs({
      "ops.mission_id": "adaptive-networks",
      "system.subsystem": "network_core",
      "system.status": "CRITICAL",
      "error.type": ch.errorType,
      "chaos.channel": channel,
      "chaos.fault_type": ch.name,
      "exception.type": ch.errorType,
      "exception.message": message,
    }),
  };
}

export async function injectFaultLogs(channel: number, burst = 6) {
  if (!OTLP_ENDPOINT || !ES_API_KEY) {
    throw new Error("OTLP_ENDPOINT and ES_API_KEY must be configured");
  }
  const ch = FAULT_CHANNELS.find((c) => c.channel === channel);
  if (!ch) throw new Error(`Unknown channel ${channel}`);

  const message = faultMessage(channel);
  const records = Array.from({ length: burst }, (_, i) =>
    buildLogRecord(channel, message, i)
  );
  const payload = {
    resourceLogs: [
      {
        resource: buildResource(),
        scopeLogs: [
          {
            scope: { name: "adaptive-networks-demo" },
            logRecords: records,
          },
        ],
      },
    ],
  };

  const res = await fetch(`${OTLP_ENDPOINT}/v1/logs`, {
    method: "POST",
    headers: {
      Authorization: `ApiKey ${ES_API_KEY}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`OTLP ingest failed (${res.status}): ${text.slice(0, 300)}`);
  }

  return { logsSent: burst, errorType: ch.errorType, channel };
}
