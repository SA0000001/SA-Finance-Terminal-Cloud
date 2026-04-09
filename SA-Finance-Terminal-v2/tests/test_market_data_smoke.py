from services import market_data


def _health_entry(name: str):
    return {
        name: {
            "source": name,
            "ok": True,
            "latency_ms": 10.0,
            "fetched_at": "2026-03-31T10:00:00+00:00",
            "last_success_at": "2026-03-31T10:00:00+00:00",
            "error": "",
            "stale_after_seconds": 300,
        }
    }


def test_load_terminal_data_merges_cached_segments(monkeypatch):
    monkeypatch.setattr(
        market_data,
        "veri_motoru",
        lambda fred_api_key="": {
            "BTC_P": "$100,000",
            "Total_Stable_Num": 100.0,
            "_health": _health_entry("base"),
        },
    )
    monkeypatch.setattr(
        market_data,
        "turev_cek",
        lambda: {
            "FR": "%0.0100",
            "_health": _health_entry("derivatives"),
        },
    )
    monkeypatch.setattr(
        market_data,
        "fetch_live_market_cap_segments",
        lambda: {
            "TOTAL_CAP_NUM": 1000.0,
            "TOTAL_CAP": "$1.0B",
            "_health": _health_entry("market_cap"),
        },
    )

    data = market_data.load_terminal_data("fred-key")

    assert data["BTC_P"] == "$100,000"
    assert data["FR"] == "%0.0100"
    assert data["TOTAL_CAP"] == "$1.0B"
    assert data["STABLE_C_D"] == "%10.00"
    assert set(data["_health"]) == {"base", "derivatives", "market_cap"}
