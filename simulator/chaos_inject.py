#!/usr/bin/env python3
"""CLI to inject or clear simulated network fault channels."""

from __future__ import annotations

import argparse
import sys

from chaos_state import ChaosState, load_registry


def main() -> int:
    parser = argparse.ArgumentParser(description="Inject simulated network faults (CH01-CH04)")
    parser.add_argument("action", choices=["on", "off", "clear", "list"], help="Fault action")
    parser.add_argument("channel", nargs="?", type=int, help="Channel number 1-4")
    args = parser.parse_args()

    chaos = ChaosState()
    registry = load_registry()

    if args.action == "list":
        active = chaos.list_active()
        print("Active channels:", active or "(none)")
        for ch_id, ch in sorted(registry.items()):
            marker = "*" if ch_id in active else " "
            print(f"  {marker} CH{ch_id:02d}: {ch['name']} [{ch['severity']}] — {ch['error_type']}")
        return 0

    if args.action == "clear":
        chaos.clear_all()
        print("Cleared all active fault channels")
        return 0

    if args.channel is None:
        print("Channel required for on/off", file=sys.stderr)
        return 1

    if args.channel not in registry:
        print(f"Unknown channel {args.channel}. Valid: {sorted(registry.keys())}", file=sys.stderr)
        return 1

    if args.action == "on":
        chaos.activate(args.channel)
        ch = registry[args.channel]
        print(f"Activated CH{args.channel:02d}: {ch['name']} ({ch['error_type']})")
    elif args.action == "off":
        chaos.deactivate(args.channel)
        print(f"Deactivated CH{args.channel:02d}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
