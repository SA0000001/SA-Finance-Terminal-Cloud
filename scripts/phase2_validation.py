# ruff: noqa: E402

from __future__ import annotations

import argparse
import sys
from copy import deepcopy
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from domain.analytics import (
    _breadth,
    _build_fragility,
    _build_liquidity_factor,
    _build_macro_breadth_factor,
    _build_macro_stress_block,
    _build_mqs,
    _build_positioning_factor,
    _build_verdict,
    _build_volatility_factor,
    _confidence_label,
    _confidence_score,
    _delta_from_trend,
    _factor_state,
    _linear_score,
    _pct,
    _region_color,
    _region_signal,
    _top_drivers,
    _weighted_change_score,
    _weighted_metric_score,
    build_analytics_payload,
    clamp_score,
    parse_number,
)
from services.market_data import load_terminal_data


def _fixture_snapshot() -> dict:
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
        "_health": {
            "fixture": {
                "ok": True,
                "last_success_at": datetime.now().isoformat(timespec="seconds"),
            }
        },
    }


def _legacy_crypto_breadth_factor(data: dict) -> dict:
    total = parse_number(data.get("TOTAL_CAP"))
    total2 = parse_number(data.get("TOTAL2_CAP"))
    total3 = parse_number(data.get("TOTAL3_CAP"))
    others = parse_number(data.get("OTHERS_CAP"))
    btc_dom = parse_number(data.get("Dom"))
    eth_dom = parse_number(data.get("ETH_Dom"))
    btc_change = parse_number(data.get("BTC_C"))

    total2_ratio = (total2 / total * 100) if total and total2 is not None else None
    total3_ratio = (total3 / total * 100) if total and total3 is not None else None
    others_ratio = (others / total * 100) if total and others is not None else None
    trend_support = 55
    if (btc_change or 0) > 2 and (total3_ratio or 0) > 30:
        trend_support = 78
    elif (btc_change or 0) > 2 and (total3_ratio or 0) < 24:
        trend_support = 32

    metrics = [
        {
            "label": "TOTAL2 katilimi",
            "display": f"{total2_ratio:.1f}%" if total2_ratio is not None else "-",
            "score": _linear_score(total2_ratio, 35, 55),
            "weight": 0.22,
        },
        {
            "label": "TOTAL3 katilimi",
            "display": f"{total3_ratio:.1f}%" if total3_ratio is not None else "-",
            "score": _linear_score(total3_ratio, 20, 42),
            "weight": 0.26,
        },
        {
            "label": "OTHERS payi",
            "display": f"{others_ratio:.1f}%" if others_ratio is not None else "-",
            "score": _linear_score(others_ratio, 4, 16),
            "weight": 0.12,
        },
        {
            "label": "BTC dominance",
            "display": str(data.get("Dom", "-")),
            "score": _linear_score(btc_dom, 46, 60, inverse=True),
            "weight": 0.18,
        },
        {
            "label": "ETH participation",
            "display": str(data.get("ETH_Dom", "-")),
            "score": _linear_score(eth_dom, 8, 20),
            "weight": 0.10,
        },
        {
            "label": "Alt participation teyidi",
            "display": str(data.get("BTC_C", "-")),
            "score": trend_support,
            "weight": 0.12,
        },
    ]
    score = _weighted_metric_score(metrics)
    confidence = _confidence_score(metrics)
    breadth_trend = clamp_score((_linear_score(total3_ratio, 20, 42) * 0.6) + (trend_support * 0.4))
    delta_7d = _delta_from_trend(breadth_trend)
    return {
        "key": "crypto_breadth",
        "label": "Crypto Breadth",
        "score": score,
        "weight": 0.55,
        "delta_7d": delta_7d,
        "trend": "up" if delta_7d > 1 else "down" if delta_7d < -1 else "flat",
        "state": _factor_state(score),
        "drivers": _top_drivers(metrics),
        "metrics": metrics,
        "confidence": confidence,
        "confidence_label": _confidence_label(confidence),
        "primary_support": max(metrics, key=lambda item: item["score"])["label"],
        "primary_risk": min(metrics, key=lambda item: item["score"])["label"],
    }


def _legacy_participation_factor(data: dict) -> dict:
    macro = _build_macro_breadth_factor(data)
    crypto = _legacy_crypto_breadth_factor(data)
    divergence = abs(macro["score"] - crypto["score"])
    divergence_penalty = clamp_score(_linear_score(divergence, 8, 35, inverse=True))
    base_score = (macro["score"] * 0.45) + (crypto["score"] * 0.55)
    score = clamp_score((base_score * 0.88) + (divergence_penalty * 0.12))
    trend_mix = clamp_score((macro["score"] * 0.45) + (crypto["score"] * 0.55))
    delta_7d = _delta_from_trend(trend_mix)
    metrics = [
        {"label": "Macro Breadth", "score": macro["score"], "weight": 0.45},
        {"label": "Crypto Breadth", "score": crypto["score"], "weight": 0.55},
        {"label": "Participation alignment", "score": divergence_penalty, "weight": 0.12},
    ]
    return {
        "key": "participation",
        "label": "Composite Participation",
        "score": score,
        "weight": 0.25,
        "delta_7d": delta_7d,
        "trend": "up" if delta_7d > 1 else "down" if delta_7d < -1 else "flat",
        "state": _factor_state(score),
        "drivers": [],
        "metrics": metrics,
        "subfactors": {"macro": macro, "crypto": crypto},
        "confidence": clamp_score(
            (_confidence_score(macro["metrics"]) * 0.45) + (_confidence_score(crypto["metrics"]) * 0.55)
        ),
    }


def _legacy_regime_scores(data: dict) -> dict:
    factors = {
        "liquidity": _build_liquidity_factor(data),
        "volatility": _build_volatility_factor(data),
        "positioning": _build_positioning_factor(data),
        "participation": _legacy_participation_factor(data),
    }
    for factor in factors.values():
        factor["contribution"] = round(factor["score"] * factor["weight"], 1)
        factor["weight_pct"] = int(round(factor["weight"] * 100))
        factor["confidence"] = factor.get("confidence", _confidence_score(factor["metrics"]))
        factor["confidence_label"] = factor.get("confidence_label", _confidence_label(factor["confidence"]))
        factor["primary_support"] = max(factor["metrics"], key=lambda item: item["score"])["label"]
        factor["primary_risk"] = min(factor["metrics"], key=lambda item: item["score"])["label"]

    base_score = clamp_score(sum(factor["contribution"] for factor in factors.values()))
    fragility = _build_fragility(factors, data)
    penalty = round(fragility["score"] * 0.18, 1)
    overall = clamp_score(base_score - penalty)
    dominant_driver = max(factors.values(), key=lambda factor: factor["contribution"])
    weakest_driver = min(factors.values(), key=lambda factor: factor["score"])
    return {
        "overall": overall,
        "base_score": base_score,
        "penalty": penalty,
        "fragility": fragility,
        "dominant_driver": dominant_driver["label"],
        "weakest_driver": weakest_driver["label"],
        "subscores": {
            "Liquidity": factors["liquidity"]["score"],
            "Volatility": factors["volatility"]["score"],
            "Positioning": factors["positioning"]["score"],
            "Participation": factors["participation"]["score"],
        },
        "factors": list(factors.values()),
        "participation": factors["participation"],
    }


def _legacy_ews(data: dict, scores: dict) -> dict:
    factors = {f["key"]: f for f in scores["factors"]}
    ob_signal = str(data.get("ORDERBOOK_SIGNAL", "") or "").lower()
    ob_score = 55
    if any(w in ob_signal for w in ["strong buy", "buy", "support"]):
        ob_score = 78
    elif any(w in ob_signal for w in ["strong sell", "sell", "resistance"]):
        ob_score = 28
    elif any(w in ob_signal for w in ["neutral", "mixed"]):
        ob_score = 52

    btc_change = parse_number(data.get("BTC_C")) or 0.0
    taker = parse_number(data.get("Taker")) or 1.0
    etf_flow = parse_number(data.get("ETF_FLOW_TOTAL")) or 0.0
    momentum_score = 50
    if btc_change > 0 and taker > 1.02 and etf_flow > 0:
        momentum_score = 80
    elif btc_change > 0 and taker > 1.02:
        momentum_score = 68
    elif btc_change < 0 and taker < 0.98 and etf_flow < 0:
        momentum_score = 22
    elif btc_change < 0 and taker < 0.98:
        momentum_score = 35
    elif abs(btc_change) < 0.5:
        momentum_score = 55

    vol_score = factors["volatility"]["score"]
    pos_score = factors["positioning"]["score"]
    ews = clamp_score(ob_score * 0.30 + momentum_score * 0.25 + vol_score * 0.25 + pos_score * 0.20)
    return {
        "score": ews,
        "components": [
            {"key": "orderbook", "score": ob_score, "weight": 30},
            {"key": "momentum", "score": momentum_score, "weight": 25},
            {"key": "volatility", "score": vol_score, "weight": 25},
            {"key": "positioning", "score": pos_score, "weight": 20},
        ],
    }


def _legacy_region(name: str, assets: list[tuple[str, str, float]], data: dict, region_weight: float) -> dict:
    changes = [_pct(data.get(change_key)) for _, change_key, _ in assets]
    weights = [weight for _, _, weight in assets]
    pos, total = _breadth(changes)
    breadth_pct = (pos / total * 100) if total else 0.0
    score = _weighted_change_score(changes, weights)
    signal = _region_signal(score, breadth_pct)
    return {
        "name": name,
        "score": round(score, 1),
        "weight": region_weight,
        "signal": signal,
        "color": _region_color(signal),
        "breadth_pos": pos,
        "breadth_total": total,
        "breadth_pct": round(breadth_pct, 0),
        "assets": [
            {
                "label": label,
                "value": change,
                "pos": change is not None and change > 0,
                "risk_sign": 1,
            }
            for (label, _, _), change in zip(assets, changes)
        ],
    }


def _legacy_risk_on_off(data: dict) -> dict:
    regions = [
        _legacy_region(
            "ASIA",
            [("N225", "NIKKEI_C", 0.40), ("HSI", "HSI_C", 0.35), ("SHCOMP", "CSI300_C", 0.25)],
            data,
            0.18,
        ),
        _legacy_region("EUROPE", [("DAX", "DAX_C", 0.50), ("FTSE", "FTSE_C", 0.50)], data, 0.16),
        _legacy_region("US FUTURES", [("SP500", "SP500_C", 0.50), ("NASDAQ", "NASDAQ_C", 0.50)], data, 0.18),
        _legacy_region("CRYPTO", [("BTC", "BTC_C", 0.55), ("ETH", "ETH_C", 0.45)], data, 0.18),
    ]
    macro_stress = _build_macro_stress_block(data)
    total_weight = sum(region["weight"] for region in regions) + macro_stress["weight"]
    global_score = clamp_score(
        (sum(region["score"] * region["weight"] for region in regions) + macro_stress["score"] * macro_stress["weight"])
        / (total_weight or 1.0)
    )
    signals = [region["signal"] for region in regions]
    risk_on_count = signals.count("RISK ON")
    risk_off_count = signals.count("RISK OFF")
    neutral_count = signals.count("NEUTRAL")
    dominant = max(risk_on_count, risk_off_count, neutral_count)
    sync_q = clamp_score(dominant / len(signals) * 100)
    if global_score >= 60 and sync_q >= 55:
        global_signal = "RISK ON"
    elif global_score <= 40 or (risk_off_count >= 2 and global_score < 50):
        global_signal = "RISK OFF"
    else:
        global_signal = "NEUTRAL"
    strict_regions = [region for region in regions if region["breadth_total"] >= 2]
    if strict_regions:
        strict_raw = sum(region["score"] * region["weight"] for region in strict_regions)
        strict_w = sum(region["weight"] for region in strict_regions)
        strict_score = clamp_score((strict_raw / strict_w) * 0.7 + macro_stress["score"] * 0.3)
    else:
        strict_score = global_score
    return {
        "global_score": global_score,
        "global_signal": global_signal,
        "strict_score": strict_score,
        "sync_q": sync_q,
        "live_score": global_score,
        "regions": regions,
        "macro_stress": macro_stress,
    }


def _row(widget: str, old_value, new_value, reason: str) -> tuple[str, str, str, str, str]:
    old_text = str(old_value)
    new_text = str(new_value)
    try:
        diff = round(abs(float(old_value) - float(new_value)), 2)
    except (TypeError, ValueError):
        diff = "changed" if old_text != new_text else "0"
    return widget, old_text, new_text, str(diff), reason


def build_comparison(data: dict) -> list[tuple[str, str, str, str, str]]:
    working = deepcopy(data)
    new_payload = build_analytics_payload(working)
    old_scores = _legacy_regime_scores(deepcopy(data))
    old_mqs = _build_mqs(old_scores)
    old_ews = _legacy_ews(data, old_scores)
    old_verdict = _build_verdict(old_mqs, old_ews, old_scores)
    old_risk = _legacy_risk_on_off(data)

    new_scores = new_payload["scores"]
    new_decision = new_payload["decision"]
    new_risk = new_payload["risk_on_off"]

    rows = [
        _row(
            "Decision verdict",
            old_verdict["verdict_en"],
            new_decision["verdict"]["verdict_en"],
            "Hard-no thresholds now include MQS/EWS/fragility/overall.",
        ),
        _row(
            "MQS",
            old_mqs["score"],
            new_decision["mqs"]["score"],
            "Crypto breadth unit fix can alter participation, fragility and gap penalty.",
        ),
        _row(
            "EWS",
            old_ews["score"],
            new_decision["ews"]["score"],
            "Orderbook parser now reads badge/class and Turkish support/resistance hints.",
        ),
        _row(
            "Overall Regime Score",
            old_scores["overall"],
            new_scores["overall"],
            "Participation and fragility recomputed with unit-safe crypto breadth.",
        ),
        _row(
            "Liquidity",
            old_scores["subscores"]["Liquidity"],
            new_scores["subscores"]["Liquidity"],
            "Unchanged formula.",
        ),
        _row(
            "Volatility",
            old_scores["subscores"]["Volatility"],
            new_scores["subscores"]["Volatility"],
            "Unchanged formula.",
        ),
        _row(
            "Positioning",
            old_scores["subscores"]["Positioning"],
            new_scores["subscores"]["Positioning"],
            "Unchanged formula.",
        ),
        _row(
            "Composite Participation",
            old_scores["subscores"]["Participation"],
            new_scores["subscores"]["Participation"],
            "TOTAL/TOTAL2/TOTAL3/OTHERS ratios now use numeric market caps.",
        ),
        _row(
            "Global Risk On/Off",
            old_risk["global_score"],
            new_risk["global_score"],
            "Missing-region handling and explicit payload contract.",
        ),
        _row(
            "Global Risk Signal",
            old_risk["global_signal"],
            new_risk["global_signal"],
            "UNKNOWN coverage can prevent false Risk Off.",
        ),
        _row(
            "Strict Sync",
            old_risk["sync_q"],
            new_risk["sync_q"],
            "UNKNOWN no longer counts as RISK OFF/NEUTRAL consensus.",
        ),
        _row(
            "Live Now",
            old_risk["live_score"],
            new_risk["live_score"],
            "Same as global live score after coverage adjustment.",
        ),
        _row(
            "Cross-Asset Transmission",
            "implicit",
            new_risk["cross_asset_transmission"]["score"],
            "Now emitted as structured dashboard field.",
        ),
        _row(
            "Macro Stress Block",
            old_risk["macro_stress"]["score"],
            new_risk["macro_stress"]["score"],
            "Unchanged sign convention: DXY/VIX/US10Y up are drags.",
        ),
    ]
    for old_region, new_region in zip(old_risk["regions"], new_risk["regions"]):
        rows.append(
            _row(
                f"Region {old_region['name']}",
                f"{old_region['score']} {old_region['signal']}",
                f"{new_region['score']} {new_region['signal']}",
                "Coverage-adjusted score; 0 coverage becomes UNKNOWN instead of false RISK OFF.",
            )
        )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 2 semantic validation snapshot comparison.")
    parser.add_argument("--fixture", action="store_true", help="Use deterministic fixture instead of live market data.")
    args = parser.parse_args()

    source = "fixture"
    data = _fixture_snapshot()
    if not args.fixture:
        try:
            data = load_terminal_data("")
            source = "live"
        except Exception as exc:
            data["_health"] = {"live_fetch": {"ok": False, "error": str(exc)}}

    payload = build_analytics_payload(deepcopy(data))
    print(f"snapshot_source: {source}")
    print(f"snapshot_time: {datetime.now().isoformat(timespec='seconds')}")
    print(f"validation_warnings: {len(payload.get('validation_warnings', []))}")
    for warning in payload.get("validation_warnings", [])[:8]:
        print(f"- {warning}")
    print()
    print("| Widget | old_value | new_value | absolute_diff | reason_for_change |")
    print("|---|---:|---:|---:|---|")
    for row in build_comparison(data):
        print("| " + " | ".join(row) + " |")


if __name__ == "__main__":
    main()
