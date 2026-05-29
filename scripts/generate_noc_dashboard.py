#!/usr/bin/env python3
"""Generate Adaptive Networks NOC dashboard NDJSON with Lens panels (Kibana 9.4+)."""

from __future__ import annotations

import json
import uuid

DATA_VIEW = "logs*"
NAMESPACE = "adaptive-networks"
FAULT_KQL = (
    'severity_text: "ERROR" AND body.text: (*SW_MATM* OR *SPANTREE* OR *BGP-3* OR *INTF-4*)'
)
NETWORK_KQL = 'service.name: "network-controller"'


def _uid() -> str:
    return str(uuid.uuid4())


def _ref(layer_id: str) -> dict:
    return {
        "id": DATA_VIEW,
        "name": f"indexpattern-datasource-layer-{layer_id}",
        "type": "index-pattern",
    }


def _layer(layer_id: str, column_order: list[str], columns: dict) -> dict:
    return {
        layer_id: {
            "columnOrder": column_order,
            "columns": columns,
            "ignoreGlobalFilters": False,
            "incompleteColumns": {},
            "indexPatternId": DATA_VIEW,
            "sampling": 1,
        }
    }


def _state(layers: dict, visualization: dict, query: str = "") -> dict:
    return {
        "adHocDataViews": {},
        "datasourceStates": {
            "formBased": {"layers": layers},
            "indexpattern": {"layers": {}},
            "textBased": {"layers": {}},
        },
        "filters": [],
        "internalReferences": [],
        "query": {"language": "kuery", "query": query},
        "visualization": visualization,
    }


def _count_col(label: str, kql_filter: str | None = None) -> dict:
    col = {
        "customLabel": True,
        "dataType": "number",
        "isBucketed": False,
        "label": label,
        "operationType": "count",
        "params": {"emptyAsNull": True},
        "scale": "ratio",
        "sourceField": "___records___",
    }
    if kql_filter:
        col["filter"] = {"language": "kuery", "query": kql_filter}
    return col


def _terms_col(field: str, label: str, size: int = 8, order_col: str | None = None) -> dict:
    return {
        "customLabel": True,
        "dataType": "string",
        "isBucketed": True,
        "label": label,
        "operationType": "terms",
        "params": {
            "size": size,
            "orderDirection": "desc",
            "orderBy": {"columnId": order_col, "type": "column"} if order_col else {"type": "alphabetical"},
            "missingBucket": False,
            "otherBucket": False,
        },
        "scale": "ordinal",
        "sourceField": field,
    }


def _date_hist_col(interval: str = "auto") -> dict:
    return {
        "customLabel": True,
        "dataType": "date",
        "isBucketed": True,
        "label": "@timestamp",
        "operationType": "date_histogram",
        "params": {"interval": interval},
        "scale": "interval",
        "sourceField": "@timestamp",
    }


def _metric_panel(panel_id: str, grid: dict, title: str, query: str, count_filter: str | None, subtitle: str = "") -> dict:
    lid, cid = _uid(), _uid()
    layers = _layer(lid, [cid], {cid: _count_col("Count", count_filter)})
    vis = {
        "layerId": lid,
        "layerType": "data",
        "metricAccessor": cid,
        "subtitle": subtitle,
    }
    return {
        "embeddableConfig": {
            "attributes": {
                "references": [_ref(lid)],
                "state": _state(layers, vis, query),
                "title": title,
                "type": "lens",
                "visualizationType": "lnsMetric",
                "version": 2,
            },
            "enhancements": {"dynamicActions": {"events": []}},
            "hidePanelTitles": False,
            "syncColors": False,
            "syncCursor": True,
            "syncTooltips": False,
        },
        "gridData": grid,
        "panelIndex": panel_id,
        "title": title,
        "type": "lens",
    }


def _xy_panel(panel_id: str, grid: dict, title: str, query: str, split_field: str | None = None) -> dict:
    lid = _uid()
    date_id, count_id = _uid(), _uid()
    columns = {date_id: _date_hist_col(), count_id: _count_col("Count")}
    column_order = [date_id, count_id]

    if split_field:
        split_id = _uid()
        columns[split_id] = _terms_col(split_field, split_field, size=6, order_col=count_id)
        column_order = [date_id, split_id, count_id]

    layers = _layer(lid, column_order, columns)
    accessors = [count_id] if not split_field else [split_id, count_id]
    vis = {
        "axisTitlesVisibilitySettings": {"x": True, "yLeft": True, "yRight": True},
        "fittingFunction": "None",
        "gridlinesVisibilitySettings": {"x": True, "yLeft": True, "yRight": True},
        "labelsOrientation": {"x": 0, "yLeft": 0, "yRight": 0},
        "layers": [
            {
                "accessors": accessors,
                "layerId": lid,
                "layerType": "data",
                "position": "top",
                "seriesType": "line" if split_field else "area_stacked",
                "showGridlines": False,
                "xAccessor": date_id,
            }
        ],
        "legend": {"isVisible": True, "position": "right"},
        "preferredSeriesType": "line" if split_field else "area_stacked",
        "tickLabelsVisibilitySettings": {"x": True, "yLeft": True, "yRight": True},
        "valueLabels": "hide",
    }
    return {
        "embeddableConfig": {
            "attributes": {
                "references": [_ref(lid)],
                "state": _state(layers, vis, query),
                "title": title,
                "type": "lens",
                "visualizationType": "lnsXY",
                "version": 2,
            },
            "enhancements": {"dynamicActions": {"events": []}},
            "hidePanelTitles": False,
            "syncColors": False,
            "syncCursor": True,
            "syncTooltips": False,
        },
        "gridData": grid,
        "panelIndex": panel_id,
        "title": title,
        "type": "lens",
    }


def _fault_logs_table_panel(panel_id: str, grid: dict) -> dict:
    lid = _uid()
    adhoc_id = _uid()
    esql_query = (
        f"FROM logs.otel.{NAMESPACE}, logs.otel.{NAMESPACE}.* "
        f'| WHERE severity_text == "ERROR" AND body.text LIKE "*-*" '
        f"| KEEP @timestamp, body.text, service.name, severity_text "
        f"| SORT @timestamp DESC "
        f"| LIMIT 50"
    )

    def esql_col(field: str, es_type: str, col_type: str) -> dict:
        return {
            "columnId": _uid(),
            "fieldName": field,
            "label": field,
            "customLabel": False,
            "meta": {"esType": es_type, "type": col_type},
        }

    columns = [
        esql_col("@timestamp", "date", "date"),
        esql_col("body.text", "text", "string"),
        esql_col("service.name", "keyword", "string"),
        esql_col("severity_text", "keyword", "string"),
    ]

    state = {
        "adHocDataViews": {
            adhoc_id: {
                "allowHidden": False,
                "allowNoIndex": False,
                "fieldFormats": {},
                "id": adhoc_id,
                "name": DATA_VIEW,
                "runtimeFieldMap": {},
                "sourceFilters": [],
                "timeFieldName": "@timestamp",
                "title": DATA_VIEW,
                "type": "esql",
            }
        },
        "datasourceStates": {
            "textBased": {
                "layers": {
                    lid: {
                        "index": adhoc_id,
                        "query": {"esql": esql_query},
                        "columns": columns,
                        "timeField": "@timestamp",
                    }
                }
            }
        },
        "filters": [],
        "internalReferences": [
            {
                "id": adhoc_id,
                "name": f"textBasedLanguages-datasource-layer-{lid}",
                "type": "index-pattern",
            }
        ],
        "query": {"esql": esql_query},
        "visualization": {
            "layerId": lid,
            "layerType": "data",
            "columns": [{"columnId": c["columnId"]} for c in columns],
            "paging": {"enabled": True, "size": 10},
            "sorting": {"columnId": columns[0]["columnId"], "direction": "desc"},
        },
    }

    return {
        "embeddableConfig": {
            "attributes": {
                "references": [],
                "state": state,
                "title": "Recent network fault logs",
                "type": "lens",
                "visualizationType": "lnsDatatable",
                "version": 2,
            },
            "enhancements": {"dynamicActions": {"events": []}},
            "hidePanelTitles": False,
            "syncColors": False,
            "syncCursor": True,
            "syncTooltips": False,
        },
        "gridData": grid,
        "panelIndex": panel_id,
        "title": "Recent network fault logs",
        "type": "lens",
    }


def generate_dashboard_ndjson() -> str:
    panels = []

    panels.append(
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
    )

    panels.append(
        _metric_panel(
            "p_errors",
            {"h": 6, "i": "p_errors", "w": 12, "x": 0, "y": 2},
            "Network fault errors",
            NETWORK_KQL,
            FAULT_KQL,
            "Last 7 days",
        )
    )
    panels.append(
        _metric_panel(
            "p_logs",
            {"h": 6, "i": "p_logs", "w": 12, "x": 12, "y": 2},
            "Network controller logs",
            NETWORK_KQL,
            None,
            "All severities",
        )
    )
    panels.append(
        _metric_panel(
            "p_error_rate",
            {"h": 6, "i": "p_error_rate", "w": 12, "x": 24, "y": 2},
            "ERROR severity",
            NETWORK_KQL,
            'severity_text: "ERROR"',
            "network-controller",
        )
    )
    panels.append(
        _metric_panel(
            "p_info",
            {"h": 6, "i": "p_info", "w": 12, "x": 36, "y": 2},
            "Baseline INFO logs",
            NETWORK_KQL,
            'severity_text: "INFO"',
            "Polling telemetry",
        )
    )

    panels.append(
        _xy_panel(
            "p_fault_timeline",
            {"h": 12, "i": "p_fault_timeline", "w": 24, "x": 0, "y": 8},
            "Fault errors over time",
            f"{NETWORK_KQL} AND {FAULT_KQL}",
        )
    )
    panels.append(
        _xy_panel(
            "p_severity_timeline",
            {"h": 12, "i": "p_severity_timeline", "w": 24, "x": 24, "y": 8},
            "Logs by severity",
            NETWORK_KQL,
            "severity_text",
        )
    )

    panels.append(
        _fault_logs_table_panel(
            "p_fault_table",
            {"h": 14, "i": "p_fault_table", "w": 48, "x": 0, "y": 20},
        )
    )

    refs = []
    seen = set()
    for panel in panels:
        attrs = panel.get("embeddableConfig", {}).get("attributes", {})
        for ref in attrs.get("references", []):
            if ref["name"] not in seen:
                refs.append(ref)
                seen.add(ref["name"])

    dashboard = {
        "attributes": {
            "description": "Network operations view for simulated router/switch faults on otel-demo",
            "kibanaSavedObjectMeta": {
                "searchSourceJSON": json.dumps(
                    {"query": {"language": "kuery", "query": NETWORK_KQL}, "filter": []}
                )
            },
            "panelsJSON": json.dumps(panels),
            "refreshInterval": {"pause": False, "value": 30000},
            "timeFrom": "now-7d",
            "timeRestore": True,
            "timeTo": "now",
            "title": "Adaptive Networks NOC",
            "optionsJSON": json.dumps({"hidePanelTitles": False, "useMargins": True}),
            "version": 1,
        },
        "coreMigrationVersion": "8.8.0",
        "id": "adaptive-networks-noc",
        "managed": False,
        "references": refs,
        "type": "dashboard",
        "typeMigrationVersion": "10.3.0",
    }

    return json.dumps(dashboard, separators=(",", ":")) + "\n"


if __name__ == "__main__":
    print(generate_dashboard_ndjson(), end="")
