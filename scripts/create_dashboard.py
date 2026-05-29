#!/usr/bin/env python3
"""Create a minimal Adaptive Networks NOC dashboard in Kibana."""

from __future__ import annotations

import json
import os
import sys
import urllib.request

KIBANA = os.environ.get("KIBANA_URL", "")
API_KEY = os.environ.get("ES_API_KEY", "")

DASHBOARD = {
    "attributes": {
        "title": "Adaptive Networks NOC",
        "description": "Simulated router/switch faults (logs.otel.adaptive-networks)",
        "panelsJSON": json.dumps([]),
        "optionsJSON": json.dumps({"hidePanelTitles": False, "useMargins": True}),
        "version": 1,
        "timeRestore": False,
        "kibanaSavedObjectMeta": {
            "searchSourceJSON": json.dumps(
                {"query": {"language": "kuery", "query": ""}, "filter": []}
            )
        },
    },
    "coreMigrationVersion": "8.8.0",
    "id": "adaptive-networks-noc",
    "type": "dashboard",
    "references": [],
}


def main() -> int:
    if not KIBANA or not API_KEY:
        print("Set KIBANA_URL and ES_API_KEY", file=sys.stderr)
        return 1

    ndjson = json.dumps(DASHBOARD) + "\n"
    boundary = "----AdaptiveNetworks"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="dashboard.ndjson"\r\n'
        f"Content-Type: application/ndjson\r\n\r\n"
        f"{ndjson}\r\n"
        f"--{boundary}--\r\n"
    ).encode()

    req = urllib.request.Request(
        f"{KIBANA}/api/saved_objects/_import?overwrite=true",
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
    return 0 if not result.get("errors") else 1


if __name__ == "__main__":
    raise SystemExit(main())
