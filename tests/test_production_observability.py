import importlib
import json
import shutil
import uuid
import warnings
from pathlib import Path

from domain.analytics import TELEMETRY_METRIC_NAMES, build_analytics_payload
from scripts.replay_validation import builtin_fixtures, load_snapshots, run_replay
from services.observability import compact_previous_payload, export_production_artifacts


def _workspace_tmp_dir() -> Path:
    root = Path("reports") / "test_tmp" / uuid.uuid4().hex
    shutil.rmtree(root, ignore_errors=True)
    root.mkdir(parents=True, exist_ok=True)
    return root


def _base() -> dict:
    return {
        "ETF_FLOW_TOTAL": "+180.0M $",
        "DXY": "99.20",
        "DXY_C": "-0.60%",
        "US10Y": "4.1100",
        "US10Y_C": "-1.20%",
        "STABLE_C_D": "%9.80",
        "USDT_D": "%5.90",
        "VIX": "18.0",
        "VIX_C": "-3.5%",
        "BTC_C": "3.60%",
        "BTC_7D": "8.20%",
        "ETH_C": "4.10%",
        "FR": "0.0060%",
        "LS_Ratio": "1.04",
        "Taker": "1.06",
        "OI": "3,000,000 BTC",
        "TOTAL_CAP": "$2.40T",
        "TOTAL2_CAP": "$1.18T",
        "TOTAL3_CAP": "$0.92T",
        "OTHERS_CAP": "$210.0B",
        "TOTAL_CAP_NUM": 2_400_000_000_000,
        "TOTAL2_CAP_NUM": 1_180_000_000_000,
        "TOTAL3_CAP_NUM": 920_000_000_000,
        "OTHERS_CAP_NUM": 210_000_000_000,
        "Dom": "%54.20",
        "ETH_Dom": "%16.10",
        "SPY_C": "1.40%",
        "RSP_C": "1.20%",
        "IWM_C": "1.10%",
        "QQQ_C": "1.70%",
        "XLK_C": "1.80%",
        "XLF_C": "1.10%",
        "XLI_C": "1.00%",
        "XLE_C": "0.60%",
        "XLY_C": "1.20%",
        "SP500_C": "1.30%",
        "NASDAQ_C": "1.60%",
        "DAX_C": "0.60%",
        "FTSE_C": "0.40%",
        "NIKKEI_C": "1.10%",
        "HSI_C": "0.80%",
        "SHCOMP_C": "0.55%",
        "OIL_C": "0.20%",
        "GOLD_C": "-0.40%",
        "ORDERBOOK_SIGNAL": "Ortak destek guclu",
        "ORDERBOOK_SIGNAL_BADGE": "SUPPORT",
        "ORDERBOOK_SIGNAL_CLASS": "signal-long",
    }


def test_root_analytics_is_deprecated_single_source_shim():
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        legacy = importlib.reload(importlib.import_module("analytics"))

    assert legacy.build_analytics_payload is build_analytics_payload
    assert any("deprecated" in str(item.message) for item in caught)


def test_payload_exposes_explainability_and_telemetry_contract():
    payload = build_analytics_payload(_base())

    decision = payload["decision"]
    telemetry = payload["telemetry"]

    assert TELEMETRY_METRIC_NAMES <= set(telemetry["metrics"])
    assert {
        "decision_reason_codes",
        "top_positive_drivers",
        "top_negative_drivers",
        "threshold_hits",
        "guardrail_warnings",
        "data_quality_summary",
        "dominant_driver_reason",
        "weakest_link_reason",
    } <= set(decision)
    assert decision["dominant_driver_reason"]
    assert decision["weakest_link_reason"]


def test_guardrails_emit_alerts_provider_degradation_and_quality_summary():
    data = {
        "BTC_C": "+0.20%",
        "ETH_C": "+0.10%",
        "TOTAL_CAP": "$2.00T",
        "TOTAL2_CAP": "$3.00T",
        "TOTAL3_CAP": "$2.80T",
        "OTHERS_CAP": "$2.30T",
        "_health": {
            "yFinance Indices": {
                "ok": False,
                "error": "'^GSPC': failed; 'NQ=F': failed",
                "fetched_at": "2026-04-20T10:00:00+00:00",
                "last_success_at": None,
            },
            "FRED M2": {
                "ok": False,
                "error": "FRED_API_KEY missing",
                "fetched_at": "2026-04-20T10:20:30+00:00",
                "last_success_at": None,
            },
        },
    }

    payload = build_analytics_payload(data)
    metrics = payload["telemetry"]["metrics"]
    alert_codes = {alert["code"] for alert in payload["observability_alerts"]}

    assert metrics["unknown_region_count"] == 3
    assert metrics["crypto_cap_ratio_clamp_count"] > 0
    assert metrics["source_timestamp_span_seconds"] > 900
    assert metrics["yfinance_failed_symbol_count"] == 2
    assert {"UNKNOWN_REGION_COVERAGE", "CRYPTO_RATIO_CLAMP", "VALIDATION_WARNINGS_PRESENT"} <= alert_codes
    assert payload["provider_degradation"]["mode"] == "visible_degradation"
    assert payload["decision"]["data_quality_summary"]["unknown_region_count"] == 3


def test_signal_and_decision_flip_telemetry_uses_previous_payload():
    first = _base()
    second = _base()
    second.update(
        {
            "VIX": "34.0",
            "VIX_C": "+9.00%",
            "DXY": "105.00",
            "DXY_C": "+1.80%",
            "US10Y": "4.95",
            "US10Y_C": "+2.20%",
            "SP500_C": "-2.40%",
            "NASDAQ_C": "-3.20%",
            "DAX_C": "-1.80%",
            "FTSE_C": "-1.20%",
            "NIKKEI_C": "-2.10%",
            "HSI_C": "-2.50%",
            "SHCOMP_C": "-1.90%",
            "BTC_C": "-6.50%",
            "ETH_C": "-7.20%",
            "GOLD_C": "+1.30%",
            "OIL_C": "+1.40%",
        }
    )

    first_payload = build_analytics_payload(first)
    second_payload = build_analytics_payload(second, previous_payload=first_payload)
    metrics = second_payload["telemetry"]["metrics"]

    assert metrics["global_signal_flip_count"] == 1
    assert metrics["decision_verdict_flip_count"] == 1


def test_compact_previous_payload_preserves_live_flip_detection_contract():
    first_payload = build_analytics_payload(_base())
    previous = compact_previous_payload(first_payload)
    second = _base()
    second.update(
        {
            "VIX_C": "+9.00%",
            "DXY_C": "+1.80%",
            "US10Y_C": "+2.20%",
            "SP500_C": "-2.40%",
            "NASDAQ_C": "-3.20%",
            "DAX_C": "-1.80%",
            "FTSE_C": "-1.20%",
            "NIKKEI_C": "-2.10%",
            "HSI_C": "-2.50%",
            "SHCOMP_C": "-1.90%",
            "BTC_C": "-6.50%",
            "ETH_C": "-7.20%",
            "GOLD_C": "+1.30%",
            "OIL_C": "+1.40%",
        }
    )

    second_payload = build_analytics_payload(second, previous_payload=previous)
    metrics = second_payload["telemetry"]["metrics"]

    assert set(previous) == {"decision", "risk_on_off"}
    assert metrics["global_signal_flip_count"] == 1
    assert metrics["decision_verdict_flip_count"] == 1


def test_external_telemetry_sink_snapshot_archive_and_replay_compatibility():
    tmp_path = _workspace_tmp_dir()
    data = _base()
    payload = build_analytics_payload(data)
    telemetry_path = tmp_path / "telemetry" / "terminal.jsonl"
    snapshot_dir = tmp_path / "snapshots"

    try:
        result = export_production_artifacts(
            data,
            payload,
            telemetry_path=telemetry_path,
            snapshot_dir=snapshot_dir,
            timestamp="2026-04-20T10:00:00Z",
        )

        assert result["warnings"] == []
        assert telemetry_path.exists()
        record = json.loads(telemetry_path.read_text(encoding="utf-8").splitlines()[0])
        assert {
            "timestamp",
            "validation_warning_count",
            "data_health_failed_source_count",
            "unknown_region_count",
            "source_timestamp_span_seconds",
            "crypto_cap_ratio_clamp_count",
            "global_signal_flip_count",
            "decision_verdict_flip_count",
            "mqs_minus_ews_gap",
            "btc_nq_spread_pp",
            "macro_stress_score",
            "decision",
            "global_signal",
            "confidence",
            "guardrail_warnings_summary",
        } <= set(record)

        snapshot_path = snapshot_dir / "terminal_snapshot_20260420T100000Z.json"
        assert snapshot_path.exists()
        snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
        assert "input" in snapshot
        assert "_score_warnings" not in snapshot["input"]
        assert snapshot["analytics_summary"]["decision"] == payload["decision"]["verdict"]["verdict_en"]

        replay = run_replay(load_snapshots([snapshot_dir]))
        assert snapshot["id"] in replay["summary"]
        assert replay["skipped"] == []
    finally:
        shutil.rmtree(tmp_path, ignore_errors=True)


def test_telemetry_sink_failure_is_returned_as_visible_warning():
    tmp_path = _workspace_tmp_dir()
    data = _base()
    payload = build_analytics_payload(data)

    try:
        result = export_production_artifacts(
            data,
            payload,
            telemetry_path=tmp_path,
            snapshot_dir=tmp_path / "snapshots",
            timestamp="2026-04-20T10:00:00Z",
        )

        assert result["snapshot_path"]
        assert any("Telemetry export failed" in warning for warning in result["warnings"])
    finally:
        shutil.rmtree(tmp_path, ignore_errors=True)


def test_replay_runner_reports_score_label_decision_and_explanation_drift():
    snapshots = builtin_fixtures()[:2]
    baseline = {
        snapshots[0]["id"]: {
            "overall": 0,
            "regime_label": "old",
            "decision": "old",
            "explanation_codes": ["OLD"],
        }
    }

    result = run_replay(snapshots, baseline=baseline)
    first_rows = [row for row in result["diffs"] if row["snapshot_id"] == snapshots[0]["id"]]

    assert result["summary"]
    assert first_rows[0]["previous_score"] == 0
    assert first_rows[0]["current_score"] is not None
    assert any(row["label_changed"] for row in first_rows)
    assert any(row["decision_changed"] for row in first_rows)
    assert any(row["explanation_changed"] for row in first_rows)
