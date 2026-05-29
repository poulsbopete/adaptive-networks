export type FaultSeverity = "low" | "high";

export interface FaultChannel {
  channel: number;
  name: string;
  severity: FaultSeverity;
  errorType: string;
  remediationAction: string;
  description: string;
}

export const FAULT_CHANNELS: FaultChannel[] = [
  {
    channel: 1,
    name: "MAC Address Flapping",
    severity: "low",
    errorType: "SW_MATM-4-MACFLAP_NOTIF",
    remediationAction: "clear_mac_table",
    description: "MAC table instability on the switching fabric",
  },
  {
    channel: 2,
    name: "Spanning Tree Topology Change",
    severity: "high",
    errorType: "SPANTREE-2-TOPO_CHANGE",
    remediationAction: "reset_spanning_tree",
    description: "Rapid STP topology changes destabilizing L2 forwarding",
  },
  {
    channel: 3,
    name: "BGP Peer Flapping",
    severity: "high",
    errorType: "BGP-3-NOTIFICATION",
    remediationAction: "reset_bgp_session",
    description: "BGP session repeatedly flapping between Established and Idle",
  },
  {
    channel: 4,
    name: "Interface Error Spike",
    severity: "low",
    errorType: "INTF-4-INPUTERR-SPIKE",
    remediationAction: "bounce_interface",
    description: "Elevated input/CRC errors on a core interface",
  },
];

export const INCIDENT_STEPS = [
  "enrich_context",
  "count_errors",
  "hybrid_correlation",
  "run_rca",
  "create_case",
  "attach_alert_to_case",
  "high_severity_hitl / auto_remediate_low",
  "audit_log",
];
