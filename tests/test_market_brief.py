from domain.market_brief import build_market_brief


def test_build_market_brief_returns_risk_on_and_support_focus():
    brief = build_market_brief(
        {
            "BTC_C": "3.25%",
            "FR": "0.0100%",
            "USDT_D": "%4.20",
            "STABLE_C_D": "%4.80",
            "VIX": "18.5",
            "ETF_FLOW_TOTAL": "+150.0M $",
            "ETF_FLOW_DATE": "31 Mar 2026",
            "LS_Signal": "Long agirlikli",
            "LS_Ratio": "1.20",
            "Taker": "1.05",
            "ORDERBOOK_SIGNAL": "ortak destek guclu",
            "ORDERBOOK_SIGNAL_DETAIL": "Kraken 97k",
            "ORDERBOOK_SIGNAL_BADGE": "SUPPORT",
            "ORDERBOOK_SIGNAL_CLASS": "signal-long",
            "Wall_Status": "denge",
        }
    )

    assert brief["regime"]["class"] == "signal-long"
    assert brief["positioning"]["class"] == "signal-short"
    assert brief["liquidity"]["class"] == "signal-long"
    assert brief["focus"]["class"] == "signal-long"


def test_build_market_brief_returns_defensive_bias_when_liquidity_is_risk_off():
    brief = build_market_brief(
        {
            "BTC_C": "-2.50%",
            "FR": "-0.0100%",
            "USDT_D": "%7.40",
            "STABLE_C_D": "%8.10",
            "VIX": "29.0",
            "ETF_FLOW_TOTAL": "-80.0M $",
            "ETF_FLOW_DATE": "31 Mar 2026",
            "LS_Signal": "Short agirlikli",
            "LS_Ratio": "0.85",
            "Taker": "0.92",
            "ORDERBOOK_SIGNAL": "ortak direnc guclu",
            "ORDERBOOK_SIGNAL_DETAIL": "Coinbase 101k",
            "ORDERBOOK_SIGNAL_BADGE": "RESISTANCE",
            "ORDERBOOK_SIGNAL_CLASS": "signal-short",
            "Wall_Status": "denge",
        }
    )

    assert brief["regime"]["class"] == "signal-short"
    assert brief["positioning"]["class"] == "signal-short"
    assert brief["liquidity"]["class"] == "signal-short"
    assert brief["focus"]["class"] == "signal-short"


def test_build_market_brief_surfaces_waiting_state_when_derivatives_missing():
    brief = build_market_brief(
        {
            "BTC_C": "0.50%",
            "USDT_D": "%7.20",
            "STABLE_C_D": "%13.00",
            "VIX": "22.0",
            "ETF_FLOW_TOTAL": "-",
            "LS_Signal": "-",
            "LS_Ratio": "-",
            "Taker": "-",
            "FR": "-",
            "ORDERBOOK_SIGNAL": "-",
            "ORDERBOOK_SIGNAL_DETAIL": "-",
            "Wall_Status": "-",
        }
    )

    assert brief["positioning"]["title"] == "Turev akis bekleniyor"
    assert brief["positioning"]["badge"] == "DATA"
    assert brief["focus"]["title"] == "Order book teyidi bekleniyor"
