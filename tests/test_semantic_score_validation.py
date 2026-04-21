from domain.analytics import (
    _confidence_label,
    _confidence_tier,
    _coverage_quality,
    _fragility_label,
    _phase_from_score,
    _regime_band,
    _regime_confidence_label,
    _side_bias_from_state,
    build_analytics_payload,
    build_regime_scores,
    build_risk_on_off,
)


def _base() -> dict:
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
        "SHCOMP_C": "0.40%",
        "GOLD_C": "-0.20%",
        "OIL_C": "0.10%",
        "ORDERBOOK_SIGNAL": "Ortak destek guclu",
        "ORDERBOOK_SIGNAL_BADGE": "SUPPORT",
        "ORDERBOOK_SIGNAL_CLASS": "signal-long",
    }


def test_macro_shock_scenario_increases_risk_off_bias():
    data = _base()
    data.update(
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
            "BTC_C": "-3.50%",
            "ETH_C": "-4.20%",
            "GOLD_C": "+1.30%",
            "OIL_C": "+1.40%",
        }
    )

    regime = build_regime_scores(data)
    roo = build_risk_on_off(data)

    assert roo["global_signal"] == "RISK OFF"
    assert roo["macro_stress"]["score"] < 40
    assert regime["subscores"]["Liquidity"] < 50
    assert regime["subscores"]["Volatility"] < 50


def test_broad_easing_scenario_strengthens_risk_on_bias():
    data = _base()
    data.update(
        {
            "VIX": "14.0",
            "VIX_C": "-8.00%",
            "DXY": "97.50",
            "DXY_C": "-1.30%",
            "US10Y": "3.75",
            "US10Y_C": "-2.00%",
            "ETF_FLOW_TOTAL": "+620.0M $",
            "SP500_C": "+2.10%",
            "NASDAQ_C": "+2.80%",
            "DAX_C": "+1.50%",
            "FTSE_C": "+1.00%",
            "NIKKEI_C": "+1.40%",
            "HSI_C": "+1.30%",
            "SHCOMP_C": "+1.10%",
            "BTC_C": "+3.20%",
            "ETH_C": "+4.40%",
            "GOLD_C": "-0.80%",
            "OIL_C": "-0.30%",
        }
    )

    regime = build_regime_scores(data)
    roo = build_risk_on_off(data)

    assert roo["global_signal"] == "RISK ON"
    assert roo["global_score"] >= 60
    assert regime["subscores"]["Liquidity"] >= 70
    assert regime["subscores"]["Volatility"] >= 60


def test_oil_shock_with_weak_equities_raises_macro_stress_drag():
    data = _base()
    data.update(
        {
            "OIL_C": "+6.00%",
            "GOLD_C": "+1.10%",
            "SP500_C": "-1.20%",
            "NASDAQ_C": "-1.60%",
            "DAX_C": "-0.90%",
            "FTSE_C": "-0.80%",
        }
    )

    roo = build_risk_on_off(data)
    drag_labels = {drag["label"] for drag in roo["drags"]}

    assert roo["macro_stress"]["score"] < 50
    assert "OIL" in drag_labels


def test_crypto_positive_but_weak_breadth_stays_selective():
    data = _base()
    data.update(
        {
            "BTC_C": "+4.50%",
            "ETH_C": "+2.20%",
            "TOTAL2_CAP": "$850.0B",
            "TOTAL3_CAP": "$410.0B",
            "OTHERS_CAP": "$80.0B",
            "Dom": "%59.50",
            "SP500_C": "+0.20%",
            "NASDAQ_C": "+0.20%",
        }
    )

    payload = build_analytics_payload(data)

    assert payload["scores"]["participation"]["subfactors"]["crypto"]["score"] < 50
    assert payload["decision"]["verdict"]["verdict"] in {"DİKKAT", "HAYIR"}
    assert payload["decision"]["verdict"]["verdict"] != "EVET"


def test_missing_region_data_remains_unknown_and_neutral():
    roo = build_risk_on_off({"BTC_C": "+0.20%", "ETH_C": "+0.10%"})

    assert {region["signal"] for region in roo["regions"][:3]} == {"UNKNOWN"}
    assert roo["global_signal"] == "NEUTRAL"
    assert roo["sync_q"] < 100


def test_btc_strong_while_nq_weak_surfaces_cross_asset_divergence():
    data = _base()
    data.update({"BTC_C": "+5.00%", "ETH_C": "+5.40%", "NASDAQ_C": "-2.00%", "GOLD_C": "+0.40%"})

    roo = build_risk_on_off(data)
    tx_items = {item["pair"]: item for item in roo["cross_asset_transmission"]["items"]}

    assert tx_items["BTC/NQ"]["spread"] >= 6.0
    assert tx_items["BTC/NQ"]["signal"] == "POSITIVE"
    assert roo["cross_asset_transmission"]["score"] >= 56


def test_factor_monotonicity_for_core_inputs():
    base = _base()

    weak_liq = build_regime_scores({**base, "ETF_FLOW_TOTAL": "-300.0M $", "DXY": "105.0"})
    strong_liq = build_regime_scores({**base, "ETF_FLOW_TOTAL": "+700.0M $", "DXY": "97.0"})
    assert strong_liq["subscores"]["Liquidity"] > weak_liq["subscores"]["Liquidity"]

    calm_vol = build_regime_scores({**base, "VIX": "14.0", "VIX_C": "-5.0%", "BTC_C": "0.60%"})
    stressed_vol = build_regime_scores({**base, "VIX": "36.0", "VIX_C": "+8.0%", "BTC_C": "-7.00%"})
    assert calm_vol["subscores"]["Volatility"] > stressed_vol["subscores"]["Volatility"]

    balanced_positioning = build_regime_scores({**base, "FR": "0.0010%", "LS_Ratio": "1.01", "Taker": "1.01"})
    crowded_positioning = build_regime_scores({**base, "FR": "0.0350%", "LS_Ratio": "1.55", "Taker": "1.32"})
    assert balanced_positioning["subscores"]["Positioning"] > crowded_positioning["subscores"]["Positioning"]


def test_risk_on_off_monotonicity_for_macro_regions_and_transmission():
    base = _base()
    constructive = build_risk_on_off(
        {
            **base,
            "VIX_C": "-7.00%",
            "DXY_C": "-1.20%",
            "US10Y_C": "-1.40%",
            "OIL_C": "-0.80%",
            "SP500_C": "+1.80%",
            "NASDAQ_C": "+2.20%",
            "DAX_C": "+1.40%",
            "FTSE_C": "+1.00%",
            "NIKKEI_C": "+1.30%",
            "HSI_C": "+1.10%",
            "SHCOMP_C": "+0.90%",
            "BTC_C": "+4.00%",
            "ETH_C": "+4.60%",
            "GOLD_C": "-0.40%",
        }
    )
    stressed = build_risk_on_off(
        {
            **base,
            "VIX_C": "+9.00%",
            "DXY_C": "+1.80%",
            "US10Y_C": "+2.20%",
            "OIL_C": "+5.00%",
            "SP500_C": "-2.20%",
            "NASDAQ_C": "-2.80%",
            "DAX_C": "-1.50%",
            "FTSE_C": "-1.10%",
            "NIKKEI_C": "-1.70%",
            "HSI_C": "-1.90%",
            "SHCOMP_C": "-1.30%",
            "BTC_C": "-3.20%",
            "ETH_C": "-3.90%",
            "GOLD_C": "+1.00%",
        }
    )

    assert constructive["global_score"] > stressed["global_score"]
    assert constructive["macro_stress"]["score"] > stressed["macro_stress"]["score"]
    assert constructive["regions"][0]["score"] > stressed["regions"][0]["score"]
    assert constructive["cross_asset_transmission"]["score"] > stressed["cross_asset_transmission"]["score"]


def test_threshold_label_boundaries_are_explicit():
    assert _regime_band(40) == "Defensive"
    assert _regime_band(41) == "Neutral / Mixed"
    assert _regime_band(60) == "Neutral / Mixed"
    assert _regime_band(61) == "Constructive Risk-On"

    assert _fragility_label(34) == "Stable"
    assert _fragility_label(35) == "Manageable"
    assert _fragility_label(55) == "Fragile"
    assert _fragility_label(75) == "Elevated Fragility"

    assert _confidence_label(59) == "Guarded confidence"
    assert _confidence_label(60) == "Moderate confidence"
    assert _confidence_label(80) == "High confidence"

    assert _regime_confidence_label(54, 20) == "Conditional confidence"
    assert _regime_confidence_label(55, 20) == "Moderate confidence"
    assert _regime_confidence_label(74, 20) == "High confidence"

    assert _phase_from_score(38) == "BEAR PHASE"
    assert _phase_from_score(39) == "NEUTRAL PHASE"
    assert _phase_from_score(61) == "NEUTRAL PHASE"
    assert _phase_from_score(62) == "BULL PHASE"

    assert _side_bias_from_state(58, 52) == "LONG"
    assert _side_bias_from_state(42, 48) == "SHORT"
    assert _side_bias_from_state(57, 60) == "NEUTRAL"

    assert _confidence_tier(54) == "LOW"
    assert _confidence_tier(55) == "MEDIUM"
    assert _confidence_tier(75) == "HIGH"

    assert _coverage_quality(66) == "THIN"
    assert _coverage_quality(67) == "PARTIAL"
    assert _coverage_quality(95) == "FULL"


def test_runtime_guardrails_emit_warnings_for_impossible_ratios_and_contract_fields():
    data = {
        **_base(),
        "TOTAL_CAP": "$2.00T",
        "TOTAL2_CAP": "$3.00T",
        "TOTAL3_CAP": "$2.80T",
        "OTHERS_CAP": "$2.30T",
    }

    payload = build_analytics_payload(data)

    assert any("outside 0-100" in warning for warning in payload["validation_warnings"])
    assert {"phase", "side_bias", "playbook", "decomposition", "ai_analysis"} <= set(payload["risk_on_off"])
