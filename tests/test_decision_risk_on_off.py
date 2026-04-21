from domain.analytics import _build_verdict, build_analytics_payload, build_risk_on_off


def _base_payload() -> dict:
    return {
        "ETF_FLOW_TOTAL": "+150.0M $",
        "DXY": "99.20",
        "DXY_C": "-0.60%",
        "US10Y": "4.1100",
        "US10Y_C": "-1.20%",
        "STABLE_C_D": "%9.80",
        "USDT_D": "%5.90",
        "VIX": "18.0",
        "VIX_C": "-3.5%",
        "BTC_C": "2.40%",
        "BTC_7D": "7.20%",
        "FR": "0.0060%",
        "LS_Ratio": "1.04",
        "Taker": "1.06",
        "OI": "3,000,000 BTC",
        "TOTAL_CAP": "$2.40T",
        "TOTAL2_CAP": "$1.18T",
        "TOTAL3_CAP": "$0.92T",
        "OTHERS_CAP": "$210.0B",
        "Dom": "%54.20",
        "ETH_Dom": "%16.10",
        "ETH_C": "1.80%",
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
        "Sup_Wall": "$73,400",
        "Res_Wall": "$76,100",
    }


def _find_component(components: list[dict], key: str) -> dict:
    return next(item for item in components if item["key"] == key)


def _find_region(regions: list[dict], name: str) -> dict:
    return next(region for region in regions if region["name"] == name)


def test_ews_orderbook_parser_supports_turkish_signals():
    payload = build_analytics_payload(_base_payload())
    ews = payload["decision"]["ews"]
    orderbook_component = _find_component(ews["components"], "orderbook")
    assert orderbook_component["score"] >= 70
    assert ews["bias"] == "LONG"


def test_verdict_is_strict_hard_no_when_single_core_metric_breaks():
    verdict = _build_verdict(
        mqs={"score": 44},
        ews={"score": 77},
        scores={"fragility": {"score": 22}, "overall": 71},
    )
    assert verdict["verdict"] == "HAYIR"
    assert verdict["verdict_en"] == "NO TRADE"


def test_risk_drivers_use_risk_contribution_direction_not_raw_change():
    data = _base_payload()
    data.update(
        {
            "DXY_C": "+2.20%",
            "VIX_C": "+7.50%",
            "US10Y_C": "+1.40%",
            "OIL_C": "+0.40%",
            "GOLD_C": "-0.20%",
        }
    )
    roo = build_risk_on_off(data)
    driver_labels = {item["label"] for item in roo["drivers"]}
    drag_labels = {item["label"] for item in roo["drags"]}
    assert "DXY" in drag_labels
    assert "VIX" in drag_labels
    assert "DXY" not in driver_labels


def test_eth_fallback_keeps_crypto_coverage_controlled_when_eth_change_missing():
    data = _base_payload()
    data.pop("ETH_C")
    roo = build_risk_on_off(data)
    crypto_region = _find_region(roo["regions"], "CRYPTO")
    assert crypto_region["coverage"] == "2/2"
    assert all(asset["value"] is not None for asset in crypto_region["assets"])


def test_asia_score_moves_toward_neutral_when_shcomp_data_missing():
    with_csi = build_risk_on_off(_base_payload())

    without_csi_data = _base_payload()
    without_csi_data.pop("SHCOMP_C")
    without_csi = build_risk_on_off(without_csi_data)

    asia_with = _find_region(with_csi["regions"], "ASIA")
    asia_without = _find_region(without_csi["regions"], "ASIA")

    assert asia_without["coverage"] == "2/3"
    assert abs(asia_without["score"] - 50) <= abs(asia_with["score"] - 50)


def test_phase_side_and_playbook_are_derived_for_extreme_regimes():
    bull = _base_payload()
    bull.update(
        {
            "BTC_C": "4.80%",
            "ETH_C": "6.20%",
            "NASDAQ_C": "1.10%",
            "SP500_C": "1.00%",
            "DXY_C": "-1.40%",
            "VIX_C": "-6.80%",
            "US10Y_C": "-1.90%",
            "GOLD_C": "-1.20%",
            "OIL_C": "0.30%",
        }
    )
    bull_roo = build_risk_on_off(bull)
    assert bull_roo["phase"] == "BULL PHASE"
    assert bull_roo["side_bias"] == "LONG"
    assert bull_roo["playbook"].startswith("long bias")

    bear = _base_payload()
    bear.update(
        {
            "BTC_C": "-4.60%",
            "ETH_C": "-6.00%",
            "NASDAQ_C": "1.60%",
            "SP500_C": "1.30%",
            "DXY_C": "+1.80%",
            "VIX_C": "+8.20%",
            "US10Y_C": "+1.70%",
            "GOLD_C": "+1.40%",
            "OIL_C": "+1.10%",
            "NIKKEI_C": "-1.20%",
            "HSI_C": "-1.10%",
            "SHCOMP_C": "-0.90%",
            "DAX_C": "-1.00%",
            "FTSE_C": "-0.70%",
        }
    )
    bear_roo = build_risk_on_off(bear)
    assert bear_roo["phase"] == "BEAR PHASE"
    assert bear_roo["side_bias"] == "SHORT"
    assert bear_roo["playbook"].startswith("short bias")


def test_driver_bar_normalization_is_monotonic_by_contribution_magnitude():
    data = _base_payload()
    data.update(
        {
            "BTC_C": "5.20%",
            "ETH_C": "2.10%",
            "NASDAQ_C": "0.30%",
            "SP500_C": "0.20%",
            "DXY_C": "-0.40%",
            "VIX_C": "-0.80%",
        }
    )
    roo = build_risk_on_off(data)
    assert len(roo["drivers"]) >= 2
    assert roo["drivers"][0]["bar_pct"] >= roo["drivers"][1]["bar_pct"]
    assert abs(roo["drivers"][0]["impact"]) >= abs(roo["drivers"][1]["impact"])
    assert 20 <= roo["drivers"][0]["bar_pct"] <= 100
    assert 20 <= roo["drivers"][1]["bar_pct"] <= 100


def test_decomposition_totals_are_bounded_and_sign_consistent_with_scores():
    roo = build_risk_on_off(_base_payload())
    decomposition = roo["decomposition"]

    for key, score_key in (("strict", "strict_score"), ("live", "live_score")):
        total = decomposition[key]["total"]
        score = roo[score_key]
        assert -5.0 <= total <= 5.0
        if score > 50:
            assert total >= 0
        elif score < 50:
            assert total <= 0
        assert {"mkt", "stress", "btc_tx", "prelim_factor", "total"} <= set(decomposition[key].keys())


def test_cross_asset_transmission_signal_respects_threshold_direction():
    risk_on_data = _base_payload()
    risk_on_data.update({"BTC_C": "4.20%", "ETH_C": "5.10%", "NASDAQ_C": "1.00%", "GOLD_C": "-0.80%"})
    risk_on = build_risk_on_off(risk_on_data)["cross_asset_transmission"]
    assert risk_on["signal"] == "RISK ON"
    assert risk_on["score"] >= 56

    risk_off_data = _base_payload()
    risk_off_data.update({"BTC_C": "-4.20%", "ETH_C": "-5.20%", "NASDAQ_C": "1.20%", "GOLD_C": "1.10%"})
    risk_off = build_risk_on_off(risk_off_data)["cross_asset_transmission"]
    assert risk_off["signal"] == "RISK OFF"
    assert risk_off["score"] <= 44


def test_ai_analysis_is_non_empty_and_mentions_top_driver_and_drag():
    roo = build_risk_on_off(_base_payload())
    ai = roo["ai_analysis"]
    assert ai["text"].strip()
    if roo["drivers"]:
        assert roo["drivers"][0]["label"] in ai["top_driver"]
    if roo["drags"]:
        assert roo["drags"][0]["label"] in ai["top_drag"]


def test_oil_upshock_is_treated_as_risk_off_drag():
    data = _base_payload()
    data.update(
        {
            "OIL_C": "+5.00%",
            "DXY_C": "0.00%",
            "VIX_C": "0.00%",
            "US10Y_C": "0.00%",
            "GOLD_C": "0.00%",
            "BTC_C": "0.10%",
            "ETH_C": "0.10%",
        }
    )
    roo = build_risk_on_off(data)
    drag_labels = {item["label"] for item in roo["drags"]}
    assert "OIL" in drag_labels
    macro_assets = {item["label"]: item for item in roo["macro_stress"]["assets"]}
    assert macro_assets["OIL"]["risk_sign"] == -1
