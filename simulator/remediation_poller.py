#!/usr/bin/env python3
"""Poll remediation queue and clear simulated fault channels."""

from __future__ import annotations

import argparse
import logging
import os
import time
from datetime import datetime, timezone

import httpx

from chaos_state import ChaosState

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("remediation_poller")

QUEUE_INDEX = "adaptive-networks-remediation-queue"
AUDIT_INDEX = "adaptive-networks-remediation-audit"


def _headers(api_key: str) -> dict[str, str]:
    return {
        "Authorization": f"ApiKey {api_key}",
        "Content-Type": "application/json",
    }


def _search_pending(es_url: str, api_key: str) -> list[dict]:
    url = f"{es_url.rstrip('/')}/{QUEUE_INDEX}/_search"
    body = {
        "size": 10,
        "query": {"bool": {"filter": [{"term": {"status": "pending"}}]}},
        "sort": [{"@timestamp": "asc"}],
    }
    resp = httpx.post(url, headers=_headers(api_key), json=body, timeout=15)
    resp.raise_for_status()
    return resp.json().get("hits", {}).get("hits", [])


def _update_doc(es_url: str, api_key: str, index: str, doc_id: str, fields: dict) -> None:
    url = f"{es_url.rstrip('/')}/{index}/_update/{doc_id}"
    resp = httpx.post(
        url,
        headers=_headers(api_key),
        json={"doc": fields},
        timeout=15,
    )
    resp.raise_for_status()


def _index_audit(es_url: str, api_key: str, doc: dict) -> None:
    url = f"{es_url.rstrip('/')}/{AUDIT_INDEX}/_doc"
    doc["@timestamp"] = datetime.now(timezone.utc).isoformat()
    resp = httpx.post(url, headers=_headers(api_key), json=doc, timeout=15)
    resp.raise_for_status()


def process_pending(es_url: str, api_key: str, dry_run_only: bool = False) -> int:
    chaos = ChaosState()
    hits = _search_pending(es_url, api_key)
    processed = 0

    for hit in hits:
        doc_id = hit["_id"]
        source = hit["_source"]
        channel = int(source.get("channel", 0))
        is_dry_run = str(source.get("dry_run", "true")).lower() in ("true", "1")

        if is_dry_run or dry_run_only:
            logger.info("Dry-run remediation for channel %s — marking completed", channel)
        else:
            if channel:
                chaos.deactivate(channel)
                logger.info("Cleared fault channel %s via remediation", channel)

        _update_doc(
            es_url,
            api_key,
            QUEUE_INDEX,
            doc_id,
            {
                "status": "completed",
                "completed_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        _index_audit(
            es_url,
            api_key,
            {
                "channel": channel,
                "action_type": source.get("action_type"),
                "error_type": source.get("error_type"),
                "dry_run": is_dry_run,
                "status": "resolved",
            },
        )
        processed += 1

    return processed


def main() -> None:
    parser = argparse.ArgumentParser(description="Remediation queue poller")
    parser.add_argument("--interval", type=float, default=5.0)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()

    es_url = os.environ.get("ES_URL", "")
    api_key = os.environ.get("ES_API_KEY", "")
    if not es_url or not api_key:
        raise SystemExit("Set ES_URL and ES_API_KEY")

    logger.info("Remediation poller watching %s", QUEUE_INDEX)
    while True:
        try:
            count = process_pending(es_url, api_key)
            if count:
                logger.info("Processed %d remediation(s)", count)
        except Exception as exc:
            logger.warning("Poll error: %s", exc)

        if args.once:
            break
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
