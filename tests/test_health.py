from services.health import build_health_summary, merge_source_health, normalize_health_display_text
from ui.layout import normalize_health_cell


def test_merge_source_health_drops_inactive_fallback_sources():
    previous = {
        "TradingView USDT.D": {
            "source": "TradingView USDT.D",
            "ok": True,
            "latency_ms": 120.0,
            "fetched_at": "2026-04-01T00:00:00+00:00",
            "last_success_at": "2026-04-01T00:00:00+00:00",
            "error": "",
            "stale_after_seconds": 300,
        },
        "CoinGecko Global": {
            "source": "CoinGecko Global",
            "ok": True,
            "latency_ms": 160.0,
            "fetched_at": "2026-03-31T22:22:50+00:00",
            "last_success_at": "2026-03-31T22:22:50+00:00",
            "error": "",
            "stale_after_seconds": 900,
        },
    }
    latest = {
        "TradingView USDT.D": {
            "source": "TradingView USDT.D",
            "ok": True,
            "latency_ms": 95.0,
            "fetched_at": "2026-04-01T00:05:00+00:00",
            "last_success_at": "2026-04-01T00:05:00+00:00",
            "error": "",
            "stale_after_seconds": 300,
        }
    }

    merged = merge_source_health(previous, latest)

    assert set(merged) == {"TradingView USDT.D"}


def test_merge_source_health_keeps_last_success_for_current_failure():
    previous = {
        "OKX Funding": {
            "source": "OKX Funding",
            "ok": True,
            "latency_ms": 88.0,
            "fetched_at": "2026-04-01T00:00:00+00:00",
            "last_success_at": "2026-04-01T00:00:00+00:00",
            "error": "",
            "stale_after_seconds": 300,
        }
    }
    latest = {
        "OKX Funding": {
            "source": "OKX Funding",
            "ok": False,
            "latency_ms": 210.0,
            "fetched_at": "2026-04-01T00:02:00+00:00",
            "last_success_at": None,
            "error": "HTTP error",
            "stale_after_seconds": 300,
        }
    }

    merged = merge_source_health(previous, latest)

    assert merged["OKX Funding"]["last_success_at"] == "2026-04-01T00:00:00+00:00"
    assert merged["OKX Funding"]["error"] == "HTTP error"


def test_build_health_summary_redacts_sensitive_url_details():
    health_state = {
        "FRED FEDFUNDS": {
            "source": "FRED FEDFUNDS",
            "ok": False,
            "latency_ms": 123.0,
            "fetched_at": "2026-04-01T08:00:00+00:00",
            "last_success_at": "2026-04-01T07:00:00+00:00",
            "error": "HTTP error: 500 Server Error for url: https://api.stlouisfed.org/fred/series/observations?series_id=FEDFUNDS&api_key=supersecret&file_type=json",
            "stale_after_seconds": 21600,
        }
    }

    summary = build_health_summary(health_state)

    assert summary["rows"][0]["Hata"] == "FRED gecici sunucu hatasi (500); son basarili veri korunuyor."
    assert "supersecret" not in summary["rows"][0]["Hata"]


def test_build_health_summary_maps_known_market_cap_parse_error_to_fallback_copy():
    health_state = {
        "TradingView Market Cap": {
            "source": "TradingView Market Cap",
            "ok": False,
            "latency_ms": 80.0,
            "fetched_at": "2026-04-01T08:00:00+00:00",
            "last_success_at": "2026-04-01T07:00:00+00:00",
            "error": "Parse error: tradingview market cap not found",
            "stale_after_seconds": 300,
        }
    }

    summary = build_health_summary(health_state)

    assert summary["rows"][0]["Hata"] == "TradingView market cap metni parse edilemedi; CoinGecko fallback kullaniliyor."


def test_build_health_summary_flattens_html_markup_fragments_to_plain_text():
    health_state = {
        "CoinGecko Global": {
            "source": "CoinGecko Global",
            "ok": False,
            "latency_ms": 80.0,
            "fetched_at": "2026-04-01T08:00:00+00:00",
            "last_success_at": None,
            "error": """
                <div class="health-issue-row">
                    <div>
                        <div class="health-issue-source">TradingView Market Cap</div>
                        <div class="health-issue-error">TradingView market cap metni parse edilemedi; CoinGecko fallback kullaniliyor.</div>
                    </div>
                </div>
            """,
            "stale_after_seconds": 900,
        }
    }

    summary = build_health_summary(health_state)

    assert summary["rows"][0]["Hata"] == "TradingView market cap metni parse edilemedi; CoinGecko fallback kullaniliyor."


def test_normalize_health_display_text_handles_nested_values():
    value = [
        None,
        {"error": "<div>TradingView USDT.D</div>", "detail": "Parse error: tradingview usdt.d not found"},
    ]

    assert normalize_health_display_text(value) == "TradingView USDT.D | Parse error: tradingview usdt.d not found"


def test_normalize_health_cell_returns_plain_text_for_html_fragments():
    value = '<div class="health-issue-error">TradingView market cap metni parse edilemedi; CoinGecko fallback kullaniliyor.</div>'

    assert normalize_health_cell(value) == "TradingView market cap metni parse edilemedi; CoinGecko fallback kullaniliyor."
