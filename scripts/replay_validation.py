# ruff: noqa: E402

from __future__ import annotations

import argparse
import json
import sys
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from domain.analytics import build_analytics_payload


def _base_fixture() -> dict:
    return {
        "ETF_FLOW_TOTAL": "+150.0M $",
        "DXY": "100.00",
        "DXY_C": "0.00%",
        "US10Y": "4.20",
        "US10Y_C": "0.00%",
        "STABLE_C_D": "%9.50",
        "USDT_D": "%5.50",
        "VIX": "18.0",
        "VIX_C": "0.00%",
        "BTC_C": "1.20%",
        "BTC_7D": "4.00%",
        "ETH_C": "1.10%",
        "FR": "0.0040%",
        "LS_Ratio": "1.03",
        "Taker": "1.04",
        "OI": "2,900,000 BTC",
        "TOTAL_CAP": "$2.50T",
        "TOTAL2_CAP": "$1.00T",
        "TOTAL3_CAP": "$725.0B",
        "OTHERS_CAP": "$180.0B",
        "TOTAL_CAP_NUM": 2_500_000_000_000,
        "TOTAL2_CAP_NUM": 1_000_000_000_000,
        "TOTAL3_CAP_NUM": 725_000_000_000,
        "OTHERS_CAP_NUM": 180_000_000_000,
        "Dom": "%55.00",
        "ETH_Dom": "%16.0",
        "SPY_C": "0.80%",
        "RSP_C": "0.70%",
        "IWM_C": "0.60%",
        "QQQ_C": "0.90%",
        "XLK_C": "0.80%",
        "XLF_C": "0.60%",
        "XLI_C": "0.50%",
        "XLE_C": "0.30%",
        "XLY_C": "0.70%",
        "SP500_C": "0.80%",
        "NASDAQ_C": "0.90%",
        "DAX_C": "0.50%",
        "FTSE_C": "0.40%",
        "NIKKEI_C": "0.60%",
        "HSI_C": "0.50%",
        "CSI300_C": "0.40%",
        "GOLD_C": "-0.20%",
        "OIL_C": "0.10%",
        "ORDERBOOK_SIGNAL": "Ortak destek guclu",
        "ORDERBOOK_SIGNAL_BADGE": "SUPPORT",
        "ORDERBOOK_SIGNAL_CLASS": "signal-long",
    }


def builtin_fixtures() -> list[dict]:
    risk_off = _base_fixture()
    risk_off.update(
        {
            "id": "macro_risk_off",
            "VIX_C": "+9.00%",
            "DXY_C": "+1.80%",
            "US10Y_C": "+2.20%",
            "SP500_C": "-2.40%",
            "NASDAQ_C": "-3.20%",
            "DAX_C": "-1.80%",
            "FTSE_C": "-1.20%",
            "NIKKEI_C": "-2.10%",
            "HSI_C": "-2.50%",
            "CSI300_C": "-1.90%",
            "BTC_C": "-3.50%",
            "ETH_C": "-4.20%",
            "GOLD_C": "+1.30%",
            "OIL_C": "+1.40%",
        }
    )
    broad_on = _base_fixture()
    broad_on.update(
        {
            "id": "broad_risk_on",
            "VIX_C": "-8.00%",
            "DXY_C": "-1.30%",
            "US10Y_C": "-2.00%",
            "ETF_FLOW_TOTAL": "+620.0M $",
            "SP500_C": "+2.10%",
            "NASDAQ_C": "+2.80%",
            "DAX_C": "+1.50%",
            "FTSE_C": "+1.00%",
            "NIKKEI_C": "+1.40%",
            "HSI_C": "+1.30%",
            "CSI300_C": "+1.10%",
            "BTC_C": "+3.20%",
            "ETH_C": "+4.40%",
            "GOLD_C": "-0.80%",
            "OIL_C": "-0.30%",
        }
    )
    missing_regions = {"id": "missing_region_data", "BTC_C": "+0.20%", "ETH_C": "+0.10%"}
    return [
        {"id": "base_constructive", "input": _base_fixture()},
        {"id": risk_off.pop("id"), "input": risk_off},
        {"id": broad_on.pop("id"), "input": broad_on},
        {"id": missing_regions.pop("id"), "input": missing_regions},
    ]


def load_snapshots(paths: list[Path], limit: int | None = None) -> list[dict]:
    snapshots = []
    for path in paths:
        if path.is_dir():
            files = sorted(path.glob("*.json"))
        else:
            files = [path]
        for file_path in files:
            try:
                raw = json.loads(file_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            data = raw.get("input") or raw.get("data")
            if not isinstance(data, dict):
                snapshots.append({"id": file_path.stem, "skip_reason": "no input/data field"})
                continue
            snapshots.append({"id": raw.get("id") or file_path.stem, "input": data})
    return snapshots[-limit:] if limit else snapshots


def score_summary(payload: dict) -> dict:
    risk = payload["risk_on_off"]
    decision = payload["decision"]
    scores = payload["scores"]
    return {
        "overall": scores["overall"],
        "mqs": decision["mqs"]["score"],
        "ews": decision["ews"]["score"],
        "liquidity": scores["subscores"]["Liquidity"],
        "volatility": scores["subscores"]["Volatility"],
        "positioning": scores["subscores"]["Positioning"],
        "participation": scores["subscores"]["Participation"],
        "global_score": risk["global_score"],
        "strict_score": risk["strict_score"],
        "macro_stress_score": risk["macro_stress"]["score"],
        "cross_asset_score": risk["cross_asset_transmission"]["score"],
        "regime_label": scores["regime_band"],
        "global_signal": risk["global_signal"],
        "decision": decision["verdict"]["verdict_en"],
        "explanation_codes": decision["decision_reason_codes"],
    }


def compare_summary(snapshot_id: str, previous: dict | None, current: dict) -> list[dict]:
    previous = previous or {}
    rows = []
    score_keys = [
        "overall",
        "mqs",
        "ews",
        "liquidity",
        "volatility",
        "positioning",
        "participation",
        "global_score",
        "strict_score",
        "macro_stress_score",
        "cross_asset_score",
    ]
    for key in score_keys:
        previous_score = previous.get(key)
        current_score = current.get(key)
        diff = None if previous_score is None else round(float(current_score) - float(previous_score), 2)
        rows.append(
            {
                "snapshot_id": snapshot_id,
                "metric": key,
                "previous_score": previous_score,
                "current_score": current_score,
                "diff": diff,
                "label_changed": previous.get("regime_label") != current.get("regime_label") if previous else False,
                "decision_changed": previous.get("decision") != current.get("decision") if previous else False,
                "explanation_changed": (
                    previous.get("explanation_codes") != current.get("explanation_codes") if previous else False
                ),
            }
        )
    return rows


def run_replay(snapshots: list[dict], baseline: dict | None = None) -> dict:
    baseline = baseline or {}
    summaries = {}
    diffs = []
    skipped = []
    previous_payload = None
    flip_counts = {"decision_verdict_flip_count": 0, "global_signal_flip_count": 0}

    for snapshot in snapshots:
        snapshot_id = snapshot["id"]
        if "input" not in snapshot:
            skipped.append(snapshot)
            continue
        payload = build_analytics_payload(deepcopy(snapshot["input"]), previous_payload=previous_payload)
        summary = score_summary(payload)
        summaries[snapshot_id] = summary
        diffs.extend(compare_summary(snapshot_id, baseline.get(snapshot_id), summary))
        metrics = payload.get("telemetry", {}).get("metrics", {})
        flip_counts["decision_verdict_flip_count"] += int(metrics.get("decision_verdict_flip_count", 0))
        flip_counts["global_signal_flip_count"] += int(metrics.get("global_signal_flip_count", 0))
        previous_payload = payload

    return {
        "summary": summaries,
        "diffs": diffs,
        "skipped": skipped,
        "window_flip_counts": flip_counts,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay snapshots and report score/label/decision drift.")
    parser.add_argument("--snapshot", action="append", default=[], help="Snapshot JSON file or directory.")
    parser.add_argument("--limit", type=int, default=None, help="Only replay the last N snapshots from provided dirs.")
    parser.add_argument("--baseline", default="", help="Previous replay summary JSON.")
    parser.add_argument("--write-baseline", default="", help="Write current summaries to this JSON path.")
    args = parser.parse_args()

    snapshots = builtin_fixtures()
    if args.snapshot:
        snapshots = load_snapshots([Path(item) for item in args.snapshot], limit=args.limit)

    baseline = {}
    if args.baseline:
        baseline = json.loads(Path(args.baseline).read_text(encoding="utf-8")).get("summary", {})

    result = run_replay(snapshots, baseline=baseline)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.write_baseline:
        Path(args.write_baseline).write_text(
            json.dumps({"summary": result["summary"]}, ensure_ascii=False, indent=2), encoding="utf-8"
        )


if __name__ == "__main__":
    main()
