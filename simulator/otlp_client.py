"""Shared OTLP client for adaptive-networks simulator."""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

import httpx

logger = logging.getLogger("adaptive_networks.otlp")

SEVERITY_MAP = {
    "TRACE": 1,
    "DEBUG": 5,
    "INFO": 9,
    "WARN": 13,
    "ERROR": 17,
    "FATAL": 21,
}

SCHEMA_URL = "https://opentelemetry.io/schemas/1.35.0"
SCOPE_NAME = "adaptive-networks"


def _format_attributes(attrs: dict[str, Any]) -> list[dict[str, Any]]:
    formatted = []
    for key, value in attrs.items():
        if value is None:
            continue
        if isinstance(value, bool):
            val_dict = {"boolValue": value}
        elif isinstance(value, int):
            val_dict = {"intValue": str(value)}
        elif isinstance(value, float):
            val_dict = {"doubleValue": value}
        else:
            val_dict = {"stringValue": str(value)}
        formatted.append({"key": key, "value": val_dict})
    return formatted


def _now_ns() -> str:
    return str(int(time.time() * 1_000_000_000))


class OTLPClient:
    def __init__(
        self,
        endpoint: str | None = None,
        api_key: str | None = None,
        auth_type: str | None = None,
    ):
        self.endpoint = (endpoint or os.environ.get("OTLP_ENDPOINT", "")).rstrip("/")
        self.api_key = api_key or os.environ.get("ES_API_KEY", "")
        self.auth_type = auth_type or os.environ.get("OTLP_AUTH_TYPE", "ApiKey")

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"{self.auth_type} {self.api_key}"

        self.client = httpx.Client(headers=headers, http2=True, timeout=10)
        self.consecutive_failures = 0

    @staticmethod
    def build_resource(service_name: str = "network-controller") -> dict[str, Any]:
        attrs = {
            "service.name": service_name,
            "service.namespace": "adaptive-networks",
            "service.version": "1.0.0",
            "service.instance.id": f"{service_name}-001",
            "telemetry.sdk.language": "python",
            "telemetry.sdk.name": "opentelemetry",
            "telemetry.sdk.version": "1.24.0",
            "cloud.provider": "aws",
            "cloud.platform": "aws_ec2",
            "cloud.region": "us-east-1",
            "cloud.availability_zone": "us-east-1a",
            "deployment.environment": "adaptive-networks",
            "host.name": f"{service_name}-core-sw01",
            "host.architecture": "amd64",
            "os.type": "linux",
            "data_stream.type": "logs",
            "data_stream.dataset": "generic",
            "data_stream.namespace": "default",
            "elasticsearch.index": "logs.otel",
        }
        return {"attributes": _format_attributes(attrs), "schemaUrl": SCHEMA_URL}

    def build_log_record(
        self,
        severity: str,
        body: str,
        attributes: dict[str, Any] | None = None,
        event_name: str | None = None,
    ) -> dict[str, Any]:
        record: dict[str, Any] = {
            "timeUnixNano": _now_ns(),
            "severityText": severity.upper(),
            "severityNumber": SEVERITY_MAP.get(severity.upper(), 9),
            "body": {"stringValue": body},
        }
        if event_name:
            record["eventName"] = event_name
        if attributes:
            record["attributes"] = _format_attributes(attributes)
        return record

    def send_logs(self, resource: dict[str, Any], log_records: list[dict[str, Any]]) -> None:
        if not log_records or not self.endpoint:
            return
        payload = {
            "resourceLogs": [
                {
                    "resource": resource,
                    "scopeLogs": [
                        {"scope": {"name": SCOPE_NAME}, "logRecords": log_records}
                    ],
                }
            ]
        }
        self._send(f"{self.endpoint}/v1/logs", payload)

    def build_gauge(
        self,
        name: str,
        value: float,
        unit: str = "",
        attributes: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        dp: dict[str, Any] = {"timeUnixNano": _now_ns(), "asDouble": value}
        if attributes:
            dp["attributes"] = _format_attributes(attributes)
        metric: dict[str, Any] = {"name": name, "gauge": {"dataPoints": [dp]}}
        if unit:
            metric["unit"] = unit
        return metric

    def send_metrics(self, resource: dict[str, Any], metrics: list[dict[str, Any]]) -> None:
        if not metrics or not self.endpoint:
            return
        metric_resource = self._patch_resource_data_stream(resource, "metrics")
        payload = {
            "resourceMetrics": [
                {
                    "resource": metric_resource,
                    "scopeMetrics": [
                        {"scope": {"name": SCOPE_NAME}, "metrics": metrics}
                    ],
                }
            ]
        }
        self._send(f"{self.endpoint}/v1/metrics", payload)

    def _patch_resource_data_stream(
        self, resource: dict[str, Any], stream_type: str
    ) -> dict[str, Any]:
        import copy

        res = copy.deepcopy(resource)
        res["attributes"] = [
            attr for attr in res.get("attributes", []) if attr["key"] != "elasticsearch.index"
        ]
        for attr in res["attributes"]:
            if attr["key"] == "data_stream.type":
                attr["value"]["stringValue"] = stream_type
                break
        return res

    def _send(self, url: str, payload: dict) -> None:
        try:
            response = self.client.post(url, data=json.dumps(payload))
            response.raise_for_status()
            self.consecutive_failures = 0
        except Exception as exc:
            self.consecutive_failures += 1
            if self.consecutive_failures <= 3:
                logger.warning("OTLP send failed: %s", exc)

    def close(self) -> None:
        self.client.close()
