from domain.analytics import build_regime_scores


def test_build_regime_scores_returns_factor_model_and_fragility_overlay():
    scores = build_regime_scores(
        {
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
            "FR": "0.0180%",
            "LS_Ratio": "1.28",
            "Taker": "1.18",
            "OI": "3,250,000 BTC",
            "TOTAL_CAP": "$2.40T",
            "TOTAL2_CAP": "$1.18T",
            "TOTAL3_CAP": "$0.92T",
            "OTHERS_CAP": "$210.0B",
            "Dom": "%54.20",
            "SPY_C": "2.60%",
            "RSP_C": "2.10%",
            "IWM_C": "1.80%",
            "QQQ_C": "3.20%",
            "XLK_C": "3.00%",
            "XLF_C": "2.10%",
            "XLI_C": "1.50%",
            "XLE_C": "0.80%",
            "XLY_C": "2.40%",
            "SP500_C": "2.82%",
            "NASDAQ_C": "3.75%",
            "DAX_C": "0.52%",
            "FTSE_C": "0.40%",
            "NIKKEI_C": "1.20%",
        }
    )

    assert scores["overall"] >= 50
    assert scores["fragility"]["score"] >= 45
    assert scores["overlay"] in {"Constructive but Fragile", "Risk-On but Crowded"}
    assert len(scores["factors"]) == 4
    assert scores["dominant_driver"] in {"Liquidity", "Volatility", "Positioning", "Composite Participation"}
    assert "participation" in scores


def test_build_regime_scores_returns_defensive_state_in_risk_off_setup():
    scores = build_regime_scores(
        {
            "ETF_FLOW_TOTAL": "-220.0M $",
            "DXY": "105.10",
            "DXY_C": "+0.90%",
            "US10Y": "4.9800",
            "US10Y_C": "+1.40%",
            "STABLE_C_D": "%14.80",
            "USDT_D": "%8.40",
            "VIX": "31.0",
            "VIX_C": "+6.5%",
            "BTC_C": "-5.20%",
            "BTC_7D": "-11.40%",
            "FR": "-0.0160%",
            "LS_Ratio": "0.82",
            "Taker": "0.84",
            "OI": "3,700,000 BTC",
            "TOTAL_CAP": "$2.00T",
            "TOTAL2_CAP": "$0.72T",
            "TOTAL3_CAP": "$0.40T",
            "OTHERS_CAP": "$90.0B",
            "Dom": "%59.10",
        }
    )

    assert scores["overall"] <= 40
    assert scores["fragility"]["score"] >= 60
    assert scores["regime_band"] in {"Panic / Risk-Off", "Defensive"}
    assert scores["subscores"]["Liquidity"] < 50
    assert scores["subscores"]["Participation"] < 50
