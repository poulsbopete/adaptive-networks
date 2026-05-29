#!/usr/bin/env python3
"""Import Adaptive Networks NOC dashboard (Vega panels via saved objects API) into Kibana."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KIBANA = os.environ.get("KIBANA_URL", "")
API_KEY = os.environ.get("ES_API_KEY", "")


def main() -> int:
    if not KIBANA or not API_KEY:
        print("Set KIBANA_URL and ES_API_KEY", file=sys.stderr)
        return 1

    ndjson = subprocess.check_output(
        [sys.executable, str(ROOT / "scripts" / "generate_noc_dashboard.py")],
        text=True,
    )

    boundary = "----AdaptiveNetworks"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="noc-dashboard.ndjson"\r\n'
        f"Content-Type: application/ndjson\r\n\r\n"
        f"{ndjson}\r\n"
        f"--{boundary}--\r\n"
    ).encode()

    req = urllib.request.Request(
        f"{KIBANA.rstrip('/')}/api/saved_objects/_import?overwrite=true",
        data=body,
        headers={
            "Authorization": f"ApiKey {API_KEY}",
            "kbn-xsrf": "true",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        result = json.load(resp)

    print(json.dumps(result, indent=2))
    if result.get("success"):
        print(f"\nDashboard: {KIBANA}/app/dashboards#/view/adaptive-networks-noc")
    return 0 if result.get("success") else 1


if __name__ == "__main__":
    raise SystemExit(main())
