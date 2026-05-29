"""Shared chaos channel state for simulator processes."""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any

import yaml

DEFAULT_STATE_FILE = Path(__file__).resolve().parent / ".chaos_state.json"
REGISTRY_PATH = Path(__file__).resolve().parent.parent / "channel_registry.yaml"


def load_registry() -> dict[int, dict[str, Any]]:
    with open(REGISTRY_PATH) as f:
        data = yaml.safe_load(f)
    return {int(k): v for k, v in data["channels"].items()}


class ChaosState:
    def __init__(self, state_file: Path | None = None):
        self.state_file = state_file or DEFAULT_STATE_FILE
        self._lock = threading.Lock()
        self.registry = load_registry()

    def _read(self) -> dict[str, Any]:
        if not self.state_file.exists():
            return {"active_channels": []}
        with open(self.state_file) as f:
            return json.load(f)

    def _write(self, state: dict[str, Any]) -> None:
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.state_file, "w") as f:
            json.dump(state, f, indent=2)

    def list_active(self) -> list[int]:
        with self._lock:
            return list(self._read().get("active_channels", []))

    def activate(self, channel: int) -> None:
        if channel not in self.registry:
            raise ValueError(f"Unknown channel {channel}")
        with self._lock:
            state = self._read()
            active = set(state.get("active_channels", []))
            active.add(channel)
            state["active_channels"] = sorted(active)
            self._write(state)

    def deactivate(self, channel: int) -> None:
        with self._lock:
            state = self._read()
            active = [c for c in state.get("active_channels", []) if c != channel]
            state["active_channels"] = active
            self._write(state)

    def clear_all(self) -> None:
        with self._lock:
            self._write({"active_channels": []})

    def is_active(self, channel: int) -> bool:
        return channel in self.list_active()
