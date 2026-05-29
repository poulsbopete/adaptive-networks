#!/usr/bin/env python3
"""Mark stale active Kibana alerts as recovered and disable obvious test rules."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

ES_URL = os.environ.get("ES_URL", "").rstrip("/")
KIBANA_URL = os.environ.get("KIBANA_URL", "").rstrip("/")
ES_API_KEY = os.environ.get("ES_API_KEY", "")

# Recover active alerts older than this many hours.
STALE_HOURS = int(os.environ.get("ALERT_STALE_HOURS", "6"))

# Always recover alerts from these rules (demo noise on shared otel-demo).
FORCE_RECOVER_RULES = {
    "test rule",
    "Threshold Alert",
    "Error Rate Exceeding Threshold",
    "High Latency Transactions",
    "Synthetics status internal rule",
}


def headers(*, kibana: bool = False) -> dict[str, str]:
    h = {
        "Authorization": f"ApiKey {ES_API_KEY}",
        "Content-Type": "application/json",
    }
    if kibana:
        h["kbn-xsrf"] = "true"
        h["x-elastic-internal-origin"] = "kibana"
    return h


def es_request(path: str, body: dict | None = None, method: str = "GET") -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"{ES_URL}{path}", data=data, headers=headers(), method=method)
    with urllib.request.urlopen(req) as resp:
        return json.load(resp)


def kibana_request(path: str, method: str = "GET", body: dict | None = None) -> dict | None:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        f"{KIBANA_URL}{path}", data=data, headers=headers(kibana=True), method=method
    )
    try:
        with urllib.request.urlopen(req) as resp:
            text = resp.read().decode()
            return json.loads(text) if text else None
    except urllib.error.HTTPError as exc:
        print(f"  Kibana {method} {path}: HTTP {exc.code}", file=sys.stderr)
        return None


def count_active() -> int:
    body = {
        "size": 0,
        "query": {"term": {"kibana.alert.status": "active"}},
    }
    result = es_request("/.alerts-*/_search", body, "POST")
    total = result["hits"]["total"]
    return total["value"] if isinstance(total, dict) else int(total)


def recover_stale_alerts() -> dict:
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=STALE_HOURS)).isoformat()
    now = datetime.now(timezone.utc).isoformat()

    body = {
        "script": {
            "source": """
              ctx._source['kibana.alert.status'] = 'recovered';
              ctx._source['kibana.alert.end'] = params.now;
              if (ctx._source.containsKey('kibana.alert.start')) {
                long start = ZonedDateTime.parse(ctx._source['kibana.alert.start']).toInstant().toEpochMilli();
                long end = ZonedDateTime.parse(params.now).toInstant().toEpochMilli();
                ctx._source['kibana.alert.duration.us'] = (end - start) * 1000L;
              }
            """,
            "lang": "painless",
            "params": {"now": now},
        },
        "query": {
            "bool": {
                "must": [{"term": {"kibana.alert.status": "active"}}],
                "should": [
                    {"range": {"kibana.alert.start": {"lt": cutoff}}},
                    {"terms": {"kibana.alert.rule.name": list(FORCE_RECOVER_RULES)}},
                ],
                "minimum_should_match": 1,
            }
        },
    }
    return es_request("/.alerts-*/_update_by_query?conflicts=proceed&refresh=true", body, "POST")


def disable_test_rules() -> None:
    req = urllib.request.Request(
        f"{KIBANA_URL}/api/alerting/rules/_find?search=test%20rule&per_page=10",
        headers=headers(kibana=True),
    )
    with urllib.request.urlopen(req) as resp:
        rules = json.load(resp).get("data", [])

    for rule in rules:
        if rule.get("name") != "test rule":
            continue
        rid = rule["id"]
        if rule.get("enabled"):
            kibana_request(f"/api/alerting/rule/{rid}/_disable", "POST")
            print(f"  disabled rule: {rule['name']} ({rid})")


def main() -> int:
    if not ES_URL or not KIBANA_URL or not ES_API_KEY:
        print("Set ES_URL, KIBANA_URL, and ES_API_KEY", file=sys.stderr)
        return 1

    before = count_active()
    print(f"Active alerts before cleanup: {before}")

    result = recover_stale_alerts()
    updated = result.get("updated", 0)
    failures = result.get("failures", [])
    print(f"Recovered {updated} stale alert(s)")
    if failures:
        print(f"  {len(failures)} update failure(s) — check cluster permissions")

    disable_test_rules()

    after = count_active()
    print(f"Active alerts after cleanup: {after}")

    # Summary by rule for anything still active
    summary = es_request(
        "/.alerts-*/_search",
        {
            "size": 0,
            "query": {"term": {"kibana.alert.status": "active"}},
            "aggs": {"by_rule": {"terms": {"field": "kibana.alert.rule.name", "size": 20}}},
        },
        "POST",
    )
    buckets = summary.get("aggregations", {}).get("by_rule", {}).get("buckets", [])
    if buckets:
        print("Remaining active alerts:")
        for bucket in buckets:
            print(f"  {bucket['doc_count']:3} {bucket['key']}")
    else:
        print("No active alerts remaining.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
