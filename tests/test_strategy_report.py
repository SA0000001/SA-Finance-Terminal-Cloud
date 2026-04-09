from prompts.strategy_report import build_strategy_report_prompt
from services.ai_service import _normalize_content, _parse_report_payload, generate_strategy_report
from services.market_data import _normalize_calendar_events


def _sample_context():
    data = {
        "BTC_P": "$67,000",
        "BTC_C": "1.2%",
        "BTC_7D": "4.8%",
        "Dom": "%55.4",
        "ETH_Dom": "%10.8",
        "FR": "%0.0030",
        "OI": "2,900,000 BTC",
        "LS_Ratio": "1.08",
        "Long_Pct": "%51.9",
        "Short_Pct": "%48.1",
        "Taker": "1.02",
        "ETF_FLOW_TOTAL": "+92.0M $",
        "ETF_FLOW_DATE": "01 Apr 2026",
        "ETF_FLOW_SOURCE": "Farside",
        "Total_Stable": "$314.3B",
        "USDT_MCap": "$184.0B",
        "USDC_MCap": "$77.4B",
        "DAI_MCap": "$4.7B",
        "USDT_Dom_Stable": "%58.5",
        "USDT_D": "%7.20",
        "STABLE_C_D": "%11.10",
        "VIX": "19.2",
        "VIX_C": "-17.45%",
        "DXY": "98.8",
        "DXY_C": "-0.61%",
        "FED": "%3.50",
        "US10Y": "4.05",
        "US10Y_C": "-0.71%",
        "SP500": "6,522.41",
        "SP500_C": "2.82%",
        "NASDAQ": "21,574.48",
        "NASDAQ_C": "3.75%",
        "DAX": "22,680.04",
        "DAX_C": "0.52%",
        "NIKKEI": "51,885.85",
        "NIKKEI_C": "-2.79%",
        "GOLD": "$4,712.60",
        "GOLD_C": "4.12%",
        "SILVER": "$75.41",
        "SILVER_C": "7.23%",
        "OIL": "$102.09",
        "OIL_C": "-0.77%",
        "TOTAL_CAP": "$2.45T",
        "TOTAL_CAP_NUM": 2.45e12,
        "TOTAL2_CAP": "$1.12T",
        "TOTAL2_CAP_NUM": 1.12e12,
        "TOTAL3_CAP": "$0.84T",
        "TOTAL3_CAP_NUM": 0.84e12,
        "OTHERS_CAP": "$0.29T",
        "OTHERS_CAP_NUM": 0.29e12,
        "ORDERBOOK_SIGNAL": "Ortak destek guclu",
        "ORDERBOOK_SIGNAL_DETAIL": "Kraken ve Coinbase destekte hizali",
        "ORDERBOOK_SOURCES": "Kraken | OKX | Coinbase",
        "Sup_Wall": "$66,800",
        "Res_Wall": "$68,900",
        "ETH_P": "$2,100.30",
        "ETH_C": "1.10%",
        "ETH_7D": "-2.53%",
        "SOL_P": "$82.96",
        "SOL_C": "-1.07%",
        "SOL_7D": "-8.89%",
        "BNB_P": "$617.85",
        "BNB_C": "0.15%",
        "BNB_7D": "-3.27%",
        "XRP_P": "$1.34",
        "XRP_C": "0.11%",
        "XRP_7D": "-5.26%",
        "ADA_P": "$0.24",
        "ADA_C": "-1.05%",
        "ADA_7D": "-8.99%",
        "AVAX_P": "$8.93",
        "AVAX_C": "-1.17%",
        "AVAX_7D": "-6.92%",
        "DOT_P": "$1.26",
        "DOT_C": "-0.19%",
        "DOT_7D": "-10.46%",
        "LINK_P": "$8.79",
        "LINK_C": "-0.21%",
        "LINK_7D": "-4.72%",
        "NEWS": [{"title": "ETF flows stay positive", "source": "CoinDesk", "time": "01 Apr 09:00"}],
        "ECONOMIC_CALENDAR_SOURCE": "FairEconomy",
        "ECONOMIC_CALENDAR": [
            {
                "title": "US CPI",
                "country": "USD",
                "impact": "High",
                "date": "2026-04-01",
                "time": "15:30",
                "actual": "-",
                "forecast": "3.1%",
                "previous": "3.3%",
            }
        ],
    }
    brief = {
        "regime": {"title": "Constructive Risk-On", "badge": "Bias", "why": ["Liquidity easing", "Vol contained"]},
        "liquidity": {"title": "Supportive", "badge": "Liquidity", "why": ["ETF flows positive"]},
        "positioning": {"title": "Balanced", "badge": "Positioning", "why": ["Funding near neutral"]},
        "focus": {"title": "Support-led continuation", "badge": "Execution", "why": ["Respect support first"]},
    }
    analytics = {
        "scores": {
            "overall": 68,
            "base_score": 71,
            "fragility": {"score": 24, "label": "Stable"},
            "confidence": 63,
            "confidence_label": "Moderate confidence",
            "regime_band": "Constructive Risk-On",
            "overlay": "Constructive Risk-On",
            "bias": "Risk-on korunabilir ama secici kal.",
            "dominant_driver": "Liquidity",
            "weakest_driver": "Participation",
            "summary": "Liquidity rejimi tasiyor.",
            "invalidate_conditions": ["ETF flow zayiflarsa tez bozulur."],
            "watch_next": ["ETF akisi", "DXY", "Funding"],
            "factors": [
                {"label": "Liquidity", "score": 72, "delta_7d": 4, "primary_support": "ETF akislari", "primary_risk": "USDT.D"},
                {"label": "Volatility", "score": 69, "delta_7d": 2, "primary_support": "VIX seviyesi", "primary_risk": "BTC 24s oynaklik"},
                {"label": "Positioning", "score": 64, "delta_7d": 1, "primary_support": "Funding dengesi", "primary_risk": "Open interest"},
                {"label": "Composite Participation", "score": 58, "delta_7d": -1, "primary_support": "Crypto Breadth", "primary_risk": "Macro Breadth"},
            ],
            "participation": {
                "score": 58,
                "state": "Karisik",
                "subfactors": {
                    "macro": {"score": 55, "state": "Karisik"},
                    "crypto": {"score": 61, "state": "Yapici"},
                },
            },
        },
        "scenarios": [
            {"Scenario": "Bullish", "Trigger": "68,900 ustu", "Follow-through": "ETF ve breadth teyidi"},
            {"Scenario": "Base", "Trigger": "66,800-68,900 arasi", "Follow-through": "VIX sakin"},
        ],
    }
    alerts = [{"title": "VIX Alert", "detail": "VIX 20 ustune yaklasiyor"}]
    health_summary = {"healthy_sources": 12, "failed_sources": [], "stale_sources": [], "rows": []}
    return data, brief, analytics, alerts, health_summary


def test_strategy_report_prompt_includes_new_sections_and_tags():
    data, brief, analytics, alerts, health_summary = _sample_context()
    prompt = build_strategy_report_prompt(data, brief, analytics, alerts, health_summary, depth="Orta")

    assert "<terminal_report>" in prompt
    assert "<x_lead>" in prompt
    assert "<x_thread>" in prompt
    assert "Ekonomik takvim" in prompt
    assert "Veri sagligi" in prompt
    assert "SA Finance Alpha Makro Bulteni Giris" in prompt
    assert "Long / Short / Bekle ve Kritik Riskler" in prompt
    assert "1/5 ..." in prompt
    assert "Fragile confidence" in prompt
    assert "SP500:" in prompt
    assert "NASDAQ:" in prompt
    assert "GOLD:" in prompt
    assert "ETH:" in prompt
    assert "LINK:" in prompt


def test_parse_report_payload_splits_tagged_response():
    data, brief, analytics, _, _ = _sample_context()
    raw = """
<terminal_report>
### Bugunun Ozeti
Kisa rapor
</terminal_report>
<x_lead>
Lead metni
</x_lead>
<x_thread>
1/4 Bir
2/4 Iki
3/4 Uc
4/4 Dort
</x_thread>
"""
    parsed = _parse_report_payload(raw, data, brief, analytics)

    assert "Kisa rapor" in parsed["terminal_report"]
    assert parsed["x_lead"] == "Lead metni"
    assert parsed["x_thread"].startswith("1/4")


def test_normalize_content_supports_provider_style_content_parts():
    content = [
        {"type": "text", "text": "<terminal_report>Rapor</terminal_report>"},
        {"type": "output_text", "output_text": "<x_lead>Lead</x_lead>"},
        {"content": "<x_thread>1/4 A</x_thread>"},
    ]

    normalized = _normalize_content(content)

    assert "<terminal_report>Rapor</terminal_report>" in normalized
    assert "<x_lead>Lead</x_lead>" in normalized
    assert "<x_thread>1/4 A</x_thread>" in normalized


def test_parse_report_payload_falls_back_when_content_is_not_tagged_string():
    data, brief, analytics, _, _ = _sample_context()
    raw = [{"type": "text", "text": "Provider came back without tags"}]

    parsed = _parse_report_payload(raw, data, brief, analytics)

    assert "### SA Finance Alpha Makro Bulteni Giris" in parsed["terminal_report"]
    assert "Makro Ortam ve Risk Istahi" in parsed["terminal_report"]
    assert "SP500" in parsed["terminal_report"]
    assert "ETF, Stablecoin ve Altcoinler" in parsed["terminal_report"]
    assert "ETH" in parsed["terminal_report"]
    assert "Fragile confidence" not in parsed["terminal_report"]
    assert "Mixed overlay" not in parsed["terminal_report"]
    assert parsed["x_lead"]
    assert parsed["x_thread"].startswith("1/5")
    assert "BTC'den" in parsed["x_thread"]
    assert "Provider came back without tags" in parsed["raw"]


def test_normalize_calendar_events_keeps_only_near_high_impact_items():
    now = __import__("pandas").Timestamp("2026-04-01 10:00:00", tz="Europe/Istanbul")
    events = [
        {"title": "US CPI", "country": "USD", "impact": "High", "date": "2026-04-01", "time": "15:30"},
        {"title": "Old Event", "country": "USD", "impact": "High", "date": "2026-03-29", "time": "10:00"},
        {"title": "Low Impact", "country": "EUR", "impact": "Low", "date": "2026-04-01", "time": "12:00"},
        {"title": "Tomorrow Event", "country": "USD", "impact": "High", "date": "2026-04-02", "time": "17:00"},
    ]

    normalized = _normalize_calendar_events(events, now=now)

    titles = [item["title"] for item in normalized]
    assert "US CPI" in titles
    assert "Tomorrow Event" in titles
    assert "Old Event" not in titles
    assert "Low Impact" not in titles


class _FakeMessage:
    def __init__(self, content):
        self.content = content


class _FakeChoice:
    def __init__(self, content):
        self.message = _FakeMessage(content)


class _FakeResponse:
    def __init__(self, content):
        self.choices = [_FakeChoice(content)]


class _FakeCompletions:
    def __init__(self, content):
        self._content = content

    def create(self, **kwargs):
        return _FakeResponse(self._content)


class _FakeChat:
    def __init__(self, content):
        self.completions = _FakeCompletions(content)


class _FakeClient:
    def __init__(self, content):
        self.chat = _FakeChat(content)


def test_generate_strategy_report_supports_legacy_depth_only_call():
    data, _, analytics, _, _ = _sample_context()
    client = _FakeClient("<terminal_report>Legacy</terminal_report><x_lead>Lead</x_lead><x_thread>1/5 A</x_thread>")

    report = generate_strategy_report(client, data, depth="Orta")

    assert "Legacy" in report["terminal_report"]
    assert report["x_lead"] == "Lead"
    assert report["x_thread"].startswith("1/5")
    assert report["terminal_report"]
    assert analytics["scores"]["overall"] == 68


def test_generate_strategy_report_supports_context_rich_call():
    data, brief, analytics, alerts, health_summary = _sample_context()
    client = _FakeClient("<terminal_report>Rich</terminal_report><x_lead>Lead</x_lead><x_thread>1/5 A</x_thread>")

    report = generate_strategy_report(
        client,
        data,
        brief,
        analytics,
        alerts,
        health_summary,
        depth="Orta",
    )

    assert "Rich" in report["terminal_report"]
    assert report["x_lead"] == "Lead"
    assert report["x_thread"].startswith("1/5")
