#!/usr/bin/env python3
"""Simulated Cisco IOS-XE/NX-OS network controller — OTLP telemetry to otel-demo."""

from __future__ import annotations

import argparse
import logging
import random
import string
import time

from chaos_state import ChaosState, load_registry
from otlp_client import OTLPClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("network_controller")

INTERFACES = [
    "GigabitEthernet0/0/0",
    "GigabitEthernet0/0/1",
    "TenGigabitEthernet1/0/1",
    "TenGigabitEthernet1/0/2",
    "Vlan100",
    "Vlan200",
    "Loopback0",
]


def _safe_format(template: str, params: dict) -> str:
    class SafeDict(dict):
        def __missing__(self, key):
            return f"{{{key}}}"

    return string.Formatter().vformat(template, (), SafeDict(params))


def _fault_params(channel: int) -> dict[str, str | int]:
    iface = random.choice(INTERFACES)
    base = {
        "interface": iface,
        "interface_src": random.choice(INTERFACES),
        "interface_dst": random.choice(INTERFACES),
        "vlan_id": random.randint(100, 200),
        "mac_address": ":".join(f"{random.randint(0, 255):02x}" for _ in range(6)),
        "flap_count": random.randint(5, 40),
        "flap_window": random.randint(30, 120),
        "stp_instance": random.randint(0, 4),
        "bridge_id": "aabb.ccdd.eeff",
        "tc_count": random.randint(5, 25),
        "tc_window": random.randint(10, 60),
        "bgp_peer_ip": f"10.0.{random.randint(1, 5)}.{random.randint(1, 254)}",
        "bgp_peer_as": random.choice([64512, 64513, 65100]),
        "bgp_notification": "4/0 (Hold Timer Expired)",
        "bgp_flap_count": random.randint(3, 15),
        "bgp_flap_window": random.randint(30, 180),
        "bgp_last_state": random.choice(["Idle", "Active", "Connect"]),
        "in_errors": random.randint(50, 500),
        "crc_errors": random.randint(10, 100),
        "error_window": random.randint(30, 120),
    }
    return base


class NetworkSimulator:
    def __init__(self, interval: float = 2.0):
        self.interval = interval
        self.chaos = ChaosState()
        self.registry = load_registry()
        self.otlp = OTLPClient()
        self.resource = OTLPClient.build_resource("network-controller")
        self._poll_idx = 0
        self._last_bgp_check = 0.0

    def _base_attrs(self) -> dict:
        active = self.chaos.list_active()
        status = "CRITICAL" if active else "NORMAL"
        return {
            "ops.mission_id": "adaptive-networks",
            "ops.phase": "ACTIVE",
            "system.subsystem": "network_core",
            "system.status": status,
        }

    def emit_log(self, level: str, message: str, extra: dict | None = None) -> None:
        attrs = self._base_attrs()
        if extra:
            attrs.update(extra)
        record = self.otlp.build_log_record(level, message, attrs)
        self.otlp.send_logs(self.resource, [record])

    def emit_metric(self, name: str, value: float, unit: str = "") -> None:
        metric = self.otlp.build_gauge(name, value, unit)
        self.otlp.send_metrics(self.resource, [metric])

    def emit_fault_logs(self, channel: int) -> None:
        ch = self.registry[channel]
        params = _fault_params(channel)
        msg = _safe_format(ch["error_message"], params)
        stack = _safe_format(ch.get("stack_trace", ""), params)
        for _ in range(random.randint(2, 4)):
            attrs = self._base_attrs()
            attrs.update(
                {
                    "error.type": ch["error_type"],
                    "sensor.type": ch["sensor_type"],
                    "chaos.channel": channel,
                    "chaos.fault_type": ch["name"],
                    "exception.type": ch["error_type"],
                    "exception.message": msg,
                    "exception.stacktrace": stack,
                    "system.status": "CRITICAL",
                }
            )
            self.emit_log("ERROR", msg, attrs)

    def generate_telemetry(self) -> None:
        active = self.chaos.list_active()
        for ch in active:
            ch_def = self.registry.get(ch, {})
            if "network-controller" in ch_def.get("affected_services", []):
                self.emit_fault_logs(ch)

        iface = INTERFACES[self._poll_idx % len(INTERFACES)]
        self._poll_idx += 1
        in_errors = random.randint(0, 2) if not active else random.randint(10, 100)
        crc_errors = random.randint(0, 1) if not active else random.randint(5, 50)

        self.emit_metric("network.interface.in_errors", float(in_errors), "errors")
        self.emit_log(
            "INFO",
            f"%LINEPROTO-5-UPDOWN: Line protocol on Interface {iface}, changed state to up "
            f"in_errors={in_errors} crc_errors={crc_errors}",
            {"operation": "interface_poll", "network.interface": iface},
        )

        now = time.time()
        if now - self._last_bgp_check > 10:
            bgp_peers = random.randint(3, 6)
            established = bgp_peers if not active else random.randint(1, bgp_peers - 1)
            self.emit_metric("network.bgp.peers_established", float(established), "peers")
            self.emit_log(
                "INFO",
                f"%BGP-5-ADJCHANGE: neighbor 10.0.0.1 Up, {established}/{bgp_peers} peers Established",
                {"operation": "bgp_check"},
            )
            self._last_bgp_check = now

        stp_changes = random.randint(0, 1) if not active else random.randint(3, 15)
        self.emit_metric("network.stp.topology_changes", float(stp_changes), "changes")
        self.emit_log(
            "INFO",
            f"%SPANTREE-6-PORT_STATE: VLAN0100 {iface} state -> forwarding, "
            f"{stp_changes} topology changes this interval",
            {"operation": "stp_check"},
        )

    def run(self) -> None:
        logger.info("Network simulator running (interval=%ss)", self.interval)
        try:
            while True:
                self.generate_telemetry()
                time.sleep(self.interval)
        except KeyboardInterrupt:
            logger.info("Stopping simulator")
        finally:
            self.otlp.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Adaptive Networks OTLP simulator")
    parser.add_argument("--interval", type=float, default=2.0, help="Seconds between cycles")
    args = parser.parse_args()
    NetworkSimulator(interval=args.interval).run()


if __name__ == "__main__":
    main()
