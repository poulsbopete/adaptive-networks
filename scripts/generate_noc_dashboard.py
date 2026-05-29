#!/usr/bin/env python3
"""Generate Adaptive Networks NOC dashboard NDJSON with Vega panels (Kibana 9.4+)."""

from __future__ import annotations

import json

NAMESPACE = "adaptive-networks"
DASHBOARD_ID = "adaptive-networks-noc"
LOGS_INDEX = "logs*"
FAULT_STREAM = f"logs.otel.{NAMESPACE}, logs.otel.{NAMESPACE}.*"

FAULT_FILTER = (
    'severity_text == "ERROR" AND ('
    'body.text LIKE "*SW_MATM*" OR body.text LIKE "*SPANTREE*" OR '
    'body.text LIKE "*BGP-3*" OR body.text LIKE "*INTF-4*")'
)
SERVICE_FILTER = 'service.name == "network-controller"'

VEGA_CONFIG = {
    "axis": {"domainColor": "#444", "tickColor": "#444"},
    "view": {"stroke": None},
}


def _vega_lite(title: str, query: str, *, subtitle: str = "", context: bool = True) -> dict:
    spec: dict = {
        "$schema": "https://vega.github.io/schema/vega-lite/v6.json",
        "title": {"text": title, "subtitle": subtitle, "anchor": "start"},
        "autosize": {"type": "fit", "contains": "padding"},
        "config": VEGA_CONFIG,
        "data": {
            "url": {
                "%type%": "esql",
                "%timefield%": "@timestamp",
                "query": query,
            }
        },
    }
    if context:
        spec["data"]["url"]["%context%"] = True
    return spec


def _metric_spec(title: str, query: str, subtitle: str = "") -> dict:
    spec = _vega_lite(title, query, subtitle=subtitle)
    spec["mark"] = {
        "type": "text",
        "fontSize": 36,
        "fontWeight": "bold",
        "color": "#6092C0",
        "baseline": "middle",
    }
    spec["encoding"] = {
        "text": {"field": "count", "type": "quantitative", "format": ",.0f"}
    }
    return spec


def _time_series_spec(title: str, query: str, *, area: bool = False, color_field: str | None = None) -> dict:
    spec = _vega_lite(title, query)
    mark_type = "area" if area and not color_field else "line"
    spec["mark"] = {
        "type": mark_type,
        "point": False,
        "tooltip": True,
        "strokeWidth": 2,
        "opacity": 0.85 if area else 1,
    }
    encoding: dict = {
        "x": {
            "field": "bucket",
            "type": "temporal",
            "title": None,
            "axis": {"labelAngle": 0, "tickCount": 8},
        },
        "y": {"field": "count", "type": "quantitative", "title": "Count"},
    }
    if color_field:
        spec["mark"]["type"] = "line"
        encoding["color"] = {"field": color_field, "type": "nominal", "title": None}
    spec["encoding"] = encoding
    return spec


def _fault_logs_table_spec() -> dict:
    query = (
        f"FROM {FAULT_STREAM} "
        f"| WHERE @timestamp >= ?_tstart AND @timestamp <= ?_tend "
        f'AND severity_text == "ERROR" AND body.text LIKE "*-*" '
        f"| EVAL log_msg = TO_STRING(body.text), "
        f"service_name = TO_STRING(service.name), "
        f'severity = TO_STRING(severity_text), event_time = @timestamp '
        f"| SORT event_time DESC "
        f"| LIMIT 25"
    )
    return {
        "$schema": "https://vega.github.io/schema/vega/v6.json",
        "title": "Recent network fault logs",
        "autosize": {"type": "fit", "contains": "padding"},
        "padding": 8,
        "config": VEGA_CONFIG,
        "data": [
            {
                "name": "logs",
                "url": {"%type%": "esql", "%timefield%": "@timestamp", "query": query},
                "format": {"type": "json", "property": "values"},
                "transform": [
                    {"type": "window", "ops": ["row_number"], "as": ["row"]},
                    {
                        "type": "formula",
                        "as": "line",
                        "expr": (
                            "timeFormat(toDate(datum.event_time), '%Y-%m-%d %H:%M:%S')"
                            " + '  [' + datum.severity + ']  '"
                            " + slice(datum.log_msg, 0, 140)"
                        ),
                    },
                ],
            }
        ],
        "scales": [
            {
                "name": "y",
                "type": "band",
                "domain": {"data": "logs", "field": "row"},
                "range": "height",
                "padding": 0.05,
            }
        ],
        "marks": [
            {
                "type": "text",
                "from": {"data": "logs"},
                "encode": {
                    "update": {
                        "x": {"value": 4},
                        "y": {"scale": "y", "field": "row", "band": 0.5},
                        "text": {"field": "line"},
                        "fontSize": {"value": 11},
                        "fill": {"value": "#cccccc"},
                    }
                },
            }
        ],
    }


def _visualizations() -> list[tuple[str, str, dict]]:
    time_where = "@timestamp >= ?_tstart AND @timestamp <= ?_tend"
    return [
        (
            "adaptive-networks-noc-fault-errors",
            "Network fault errors",
            _metric_spec(
                "Network fault errors",
                f"FROM {LOGS_INDEX} | WHERE {time_where} AND {SERVICE_FILTER} AND {FAULT_FILTER} "
                f"| STATS count = COUNT(*)",
                "Cisco-style fault signatures",
            ),
        ),
        (
            "adaptive-networks-noc-controller-logs",
            "Network controller logs",
            _metric_spec(
                "Network controller logs",
                f"FROM {LOGS_INDEX} | WHERE {time_where} AND {SERVICE_FILTER} "
                f"| STATS count = COUNT(*)",
                "All severities",
            ),
        ),
        (
            "adaptive-networks-noc-error-severity",
            "ERROR severity",
            _metric_spec(
                "ERROR severity",
                f"FROM {LOGS_INDEX} | WHERE {time_where} AND {SERVICE_FILTER} "
                f'AND severity_text == "ERROR" | STATS count = COUNT(*)',
                "network-controller",
            ),
        ),
        (
            "adaptive-networks-noc-info-logs",
            "Baseline INFO logs",
            _metric_spec(
                "Baseline INFO logs",
                f"FROM {LOGS_INDEX} | WHERE {time_where} AND {SERVICE_FILTER} "
                f'AND severity_text == "INFO" | STATS count = COUNT(*)',
                "Polling telemetry",
            ),
        ),
        (
            "adaptive-networks-noc-fault-timeline",
            "Fault errors over time",
            _time_series_spec(
                "Fault errors over time",
                f"FROM {LOGS_INDEX} | WHERE {time_where} AND {SERVICE_FILTER} AND {FAULT_FILTER} "
                f"| STATS count = COUNT(*) BY bucket = DATE_TRUNC(5 minutes, @timestamp) "
                f"| SORT bucket ASC",
                area=True,
            ),
        ),
        (
            "adaptive-networks-noc-severity-timeline",
            "Logs by severity",
            _time_series_spec(
                "Logs by severity",
                f"FROM {LOGS_INDEX} | WHERE {time_where} AND {SERVICE_FILTER} "
                f"| STATS count = COUNT(*) BY bucket = DATE_TRUNC(5 minutes, @timestamp), severity_text "
                f"| RENAME severity_text AS severity | SORT bucket ASC",
                color_field="severity",
            ),
        ),
        (
            "adaptive-networks-noc-fault-logs",
            "Recent network fault logs",
            _fault_logs_table_spec(),
        ),
    ]


def _build_vis_object(viz_id: str, title: str, spec: dict) -> dict:
    spec_string = json.dumps(spec, indent=2)
    vis_state = {
        "title": title,
        "type": "vega",
        "params": {"spec": spec_string},
        "aggs": [],
    }
    return {
        "attributes": {
            "description": "",
            "kibanaSavedObjectMeta": {"searchSourceJSON": "{}"},
            "title": title,
            "uiStateJSON": "{}",
            "visState": json.dumps(vis_state),
        },
        "coreMigrationVersion": "8.8.0",
        "id": viz_id,
        "managed": False,
        "references": [],
        "type": "visualization",
        "typeMigrationVersion": "8.5.0",
    }


def _dashboard_panels() -> tuple[list[dict], list[dict]]:
    layout = [
        ("adaptive-networks-noc-fault-errors", 0, 2, 12, 6),
        ("adaptive-networks-noc-controller-logs", 12, 2, 12, 6),
        ("adaptive-networks-noc-error-severity", 24, 2, 12, 6),
        ("adaptive-networks-noc-info-logs", 36, 2, 12, 6),
        ("adaptive-networks-noc-fault-timeline", 0, 8, 24, 12),
        ("adaptive-networks-noc-severity-timeline", 24, 8, 24, 12),
        ("adaptive-networks-noc-fault-logs", 0, 20, 48, 14),
    ]

    panels: list[dict] = [
        {
            "type": "DASHBOARD_MARKDOWN",
            "embeddableConfig": {
                "content": (
                    "## Adaptive Networks NOC\n"
                    "Simulated Cisco-style router/switch telemetry from "
                    f"`logs.otel.{NAMESPACE}`. Inject faults via the demo UI or "
                    "`python simulator/chaos_inject.py`."
                )
            },
            "panelIndex": "p_intro",
            "gridData": {"h": 2, "i": "p_intro", "w": 48, "x": 0, "y": 0},
        }
    ]
    references: list[dict] = []

    for index, (viz_id, x, y, w, h) in enumerate(layout):
        panel_index = str(index + 1)
        panel_ref = f"panel_{index}"
        panels.append(
            {
                "embeddableConfig": {"hidePanelTitles": True},
                "gridData": {"x": x, "y": y, "w": w, "h": h, "i": panel_index},
                "panelIndex": panel_index,
                "panelRefName": panel_ref,
                "type": "visualization",
            }
        )
        references.append({"id": viz_id, "name": panel_ref, "type": "visualization"})

    return panels, references


def generate_dashboard_ndjson() -> str:
    lines: list[str] = []

    for viz_id, title, spec in _visualizations():
        lines.append(json.dumps(_build_vis_object(viz_id, title, spec), separators=(",", ":")))

    panels, references = _dashboard_panels()
    dashboard = {
        "attributes": {
            "description": "Network operations view for simulated router/switch faults on otel-demo",
            "kibanaSavedObjectMeta": {
                "searchSourceJSON": json.dumps(
                    {
                        "query": {
                            "language": "kuery",
                            "query": f'service.name: "network-controller"',
                        },
                        "filter": [],
                    }
                )
            },
            "optionsJSON": json.dumps({"hidePanelTitles": False, "useMargins": True}),
            "panelsJSON": json.dumps(panels),
            "refreshInterval": {"pause": False, "value": 30000},
            "timeFrom": "now-7d",
            "timeRestore": True,
            "timeTo": "now",
            "title": "Adaptive Networks NOC",
            "version": 1,
        },
        "coreMigrationVersion": "8.8.0",
        "id": DASHBOARD_ID,
        "managed": False,
        "references": references,
        "type": "dashboard",
        "typeMigrationVersion": "10.3.0",
    }
    lines.append(json.dumps(dashboard, separators=(",", ":")))
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    print(generate_dashboard_ndjson(), end="")
