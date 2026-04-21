from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

DEFAULT_TELEMETRY_PATH = Path("reports") / "telemetry" / "terminal_telemetry.jsonl"
DEFAULT_SNAPSHOT_DIR = Path("reports") / "snapshots"
SENSITIVE_KEY_PARTS = ("api", "auth", "key", "password", "secret", "token")


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def compact_previous_payload(payload: dict | None) -> dict:
    if not isinstance(payload, dict):
        return {}
    decision = payload.get("decision", {})
    risk = payload.get("risk_on_off", {})
    return {
        "decision": {"verdict": decision.get("verdict", {})},
        "risk_on_off": {"global_signal": risk.get("global_signal")},
    }


def _safe_json_value(value: Any, depth: int = 0):
    if depth > 6:
        return str(value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, dict):
        clean = {}
        for key, item in value.items():
            key_text = str(key)
            if _is_sensitive_key(key_text):
                continue
            if key_text == "_score_warnings":
                continue
            clean[key_text] = _safe_json_value(item, depth + 1)
        return clean
    if isinstance(value, (list, tuple)):
        return [_safe_json_value(item, depth + 1) for item in value[:250]]
    return str(value)


def _is_sensitive_key(key: str) -> bool:
    lower = key.lower()
    return any(part in lower for part in SENSITIVE_KEY_PARTS)


def sanitize_snapshot_input(data: dict) -> dict:
    return _safe_json_value(data)


def analytics_summary(analytics: dict) -> dict:
    scores = analytics.get("scores", {})
    decision = analytics.get("decision", {})
    verdict = decision.get("verdict", {})
    risk = analytics.get("risk_on_off", {})
    telemetry = analytics.get("telemetry", {})
    metrics = telemetry.get("metrics", {})
    explainability = decision.get("explainability", decision)
    return {
        "overall": scores.get("overall"),
        "mqs": decision.get("mqs", {}).get("score"),
        "ews": decision.get("ews", {}).get("score"),
        "decision": verdict.get("verdict_en") or verdict.get("verdict"),
        "global_signal": risk.get("global_signal"),
        "confidence": scores.get("confidence"),
        "validation_warning_count": metrics.get("validation_warning_count", 0),
        "threshold_hits": explainability.get("threshold_hits", []),
        "decision_reason_codes": explainability.get("decision_reason_codes", []),
        "observability_alert_codes": [alert.get("code") for alert in analytics.get("observability_alerts", [])],
    }


def build_telemetry_record(analytics: dict, *, timestamp: str | None = None) -> dict:
    timestamp = timestamp or utc_now_iso()
    decision = analytics.get("decision", {})
    verdict = decision.get("verdict", {})
    risk = analytics.get("risk_on_off", {})
    metrics = analytics.get("telemetry", {}).get("metrics", {})
    guardrails = decision.get("guardrail_warnings") or analytics.get("validation_warnings", [])
    return {
        "timestamp": timestamp,
        "validation_warning_count": metrics.get("validation_warning_count", 0),
        "data_health_failed_source_count": metrics.get("data_health_failed_source_count", 0),
        "unknown_region_count": metrics.get("unknown_region_count", 0),
        "source_timestamp_span_seconds": metrics.get("source_timestamp_span_seconds", 0),
        "crypto_cap_ratio_clamp_count": metrics.get("crypto_cap_ratio_clamp_count", 0),
        "global_signal_flip_count": metrics.get("global_signal_flip_count", 0),
        "decision_verdict_flip_count": metrics.get("decision_verdict_flip_count", 0),
        "mqs_minus_ews_gap": metrics.get("mqs_minus_ews_gap"),
        "btc_nq_spread_pp": metrics.get("btc_nq_spread_pp"),
        "macro_stress_score": metrics.get("macro_stress_score"),
        "yfinance_failed_symbol_count": metrics.get("yfinance_failed_symbol_count", 0),
        "decision": verdict.get("verdict_en") or verdict.get("verdict"),
        "global_signal": risk.get("global_signal"),
        "confidence": analytics_summary(analytics).get("confidence"),
        "guardrail_warnings_summary": guardrails[:8],
        "observability_alerts": [
            {"severity": alert.get("severity"), "code": alert.get("code")}
            for alert in analytics.get("observability_alerts", [])
        ],
    }


def write_telemetry_jsonl(analytics: dict, path: str | Path | None = None, *, timestamp: str | None = None) -> Path:
    target = Path(path or os.getenv("SA_TELEMETRY_JSONL") or DEFAULT_TELEMETRY_PATH)
    target.parent.mkdir(parents=True, exist_ok=True)
    record = build_telemetry_record(analytics, timestamp=timestamp)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    return target


def archive_raw_snapshot(
    data: dict,
    analytics: dict,
    directory: str | Path | None = None,
    *,
    timestamp: str | None = None,
) -> Path:
    timestamp = timestamp or utc_now_iso()
    safe_stamp = timestamp.replace(":", "").replace("-", "").replace(".", "").replace("Z", "Z")
    snapshot_id = f"terminal_snapshot_{safe_stamp}"
    target_dir = Path(directory or os.getenv("SA_SNAPSHOT_DIR") or DEFAULT_SNAPSHOT_DIR)
    target_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "id": snapshot_id,
        "created_at": timestamp,
        "input": sanitize_snapshot_input(data),
        "analytics_summary": analytics_summary(analytics),
    }
    target = target_dir / f"{snapshot_id}.json"
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return target


def export_production_artifacts(
    data: dict,
    analytics: dict,
    *,
    telemetry_path: str | Path | None = None,
    snapshot_dir: str | Path | None = None,
    timestamp: str | None = None,
) -> dict:
    timestamp = timestamp or utc_now_iso()
    result = {"telemetry_path": None, "snapshot_path": None, "warnings": []}
    try:
        result["telemetry_path"] = str(write_telemetry_jsonl(analytics, telemetry_path, timestamp=timestamp))
    except OSError as exc:
        result["warnings"].append(f"Telemetry export failed: {exc}")

    try:
        result["snapshot_path"] = str(archive_raw_snapshot(data, analytics, snapshot_dir, timestamp=timestamp))
    except OSError as exc:
        result["warnings"].append(f"Snapshot archive failed: {exc}")

    return result
