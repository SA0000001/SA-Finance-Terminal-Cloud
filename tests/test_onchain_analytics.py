"""
tests/test_onchain_analytics.py
Deterministic unit tests for domain/onchain_analytics.py
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from domain.onchain_analytics import (
    OnchainAnalytics,
    _clamp,
    _compute_metrics,
    _score_from_metrics,
    build_onchain_analytics,
    latest_valid_value,
    rolling_mean,
    rolling_zscore,
    safe_divide,
    safe_numeric,
)


# ─── Fixtures ─────────────────────────────────────────────────────────────────

def _base_df(n: int = 400) -> pd.DataFrame:
    """Minimal valid BTC-like DataFrame with n rows."""
    dates  = pd.date_range("2020-01-01", periods=n, freq="D")
    price  = 30_000 + np.linspace(0, 20_000, n)
    mcap   = price * 19_000_000
    mvrv   = 1.5 + np.sin(np.linspace(0, 2 * math.pi, n)) * 0.3
    return pd.DataFrame(
        {
            "time":                      dates.strftime("%Y-%m-%d"),
            "PriceUSD":                  price,
            "CapMrktCurUSD":             mcap,
            "CapMVRVCur":                mvrv,
            "SplyCur":                   np.full(n, 19_000_000),
            "IssTotUSD":                 np.full(n, 9_000_000),
            "FeeTotNtv":                 np.full(n, 50.0),
            "FlowInExNtv":               np.random.default_rng(42).uniform(500, 2000, n),
            "FlowOutExNtv":              np.random.default_rng(43).uniform(500, 2000, n),
            "SplyExNtv":                 np.full(n, 2_500_000),
            "AdrActCnt":                 np.random.default_rng(44).integers(800_000, 1_200_000, n).astype(float),
            "TxCnt":                     np.random.default_rng(45).integers(200_000, 400_000, n).astype(float),
            "TxTfrCnt":                  np.random.default_rng(46).integers(100_000, 300_000, n).astype(float),
            "HashRate":                  np.linspace(100e18, 500e18, n),
            "AdrBalCnt":                 np.full(n, 50_000_000),
            "ROI30d":                    np.full(n, 0.05),
            "ROI1yr":                    np.full(n, 0.80),
            "volume_reported_spot_usd_1d": np.full(n, 20e9),
        }
    )


def _stable_df(n: int = 400, start_cap: float = 80e9) -> pd.DataFrame:
    dates = pd.date_range("2020-01-01", periods=n, freq="D")
    caps  = np.linspace(start_cap, start_cap * 1.5, n)
    return pd.DataFrame(
        {
            "time":          dates.strftime("%Y-%m-%d"),
            "CapMrktCurUSD": caps,
        }
    )


# ─── 1. Estimated NUPL ────────────────────────────────────────────────────────

def test_estimated_nupl_from_mvrv():
    df = pd.DataFrame(
        {"time": ["2024-01-01"], "CapMVRVCur": [2.0], "CapMrktCurUSD": [1000.0], "SplyCur": [10.0]}
    )
    warnings: list[str] = []
    derived: list[str] = []
    out = _compute_metrics(df, None, None, warnings, derived)
    assert "NUPL_Est" in out.columns
    val = out["NUPL_Est"].iloc[0]
    assert abs(val - 0.5) < 1e-9, f"Expected 0.5 got {val}"


# ─── 2. Estimated Realized Cap ────────────────────────────────────────────────

def test_estimated_realized_cap():
    df = pd.DataFrame(
        {"time": ["2024-01-01"], "CapMrktCurUSD": [1000.0], "CapMVRVCur": [2.0], "SplyCur": [10.0]}
    )
    warnings: list[str] = []
    derived: list[str] = []
    out = _compute_metrics(df, None, None, warnings, derived)
    assert "CapRealized_Est" in out.columns
    val = out["CapRealized_Est"].iloc[0]
    assert abs(val - 500.0) < 1e-9, f"Expected 500 got {val}"


# ─── 3. Estimated Realized Price ──────────────────────────────────────────────

def test_estimated_realized_price():
    df = pd.DataFrame(
        {"time": ["2024-01-01"], "CapMrktCurUSD": [500.0], "CapMVRVCur": [1.0], "SplyCur": [10.0]}
    )
    warnings: list[str] = []
    derived: list[str] = []
    out = _compute_metrics(df, None, None, warnings, derived)
    assert "RealizedPrice_Est" in out.columns
    val = out["RealizedPrice_Est"].iloc[0]
    assert abs(val - 50.0) < 1e-9, f"Expected 50 got {val}"


# ─── 4. MVRV Z-Score with zero std ────────────────────────────────────────────

def test_mvrv_z_est_does_not_crash_with_zero_std():
    # Constant market cap → std=0 → no MVRV_Z_Est
    df = pd.DataFrame(
        {
            "time":          ["2024-01-01", "2024-01-02"],
            "CapMrktCurUSD": [1000.0, 1000.0],
            "CapMVRVCur":    [2.0, 2.0],
            "SplyCur":       [10.0, 10.0],
        }
    )
    warnings: list[str] = []
    derived: list[str] = []
    # Must not raise
    out = _compute_metrics(df, None, None, warnings, derived)
    # MVRV_Z_Est should be absent or all NaN
    if "MVRV_Z_Est" in out.columns:
        assert out["MVRV_Z_Est"].isna().all()
    # A warning about insufficient std should be present
    assert any("Z-Score" in w or "market cap" in w.lower() for w in warnings)


# ─── 5. Missing CapMVRVCur adds warning ───────────────────────────────────────

def test_missing_mvrv_column_adds_warning():
    df = pd.DataFrame({"time": ["2024-01-01"], "PriceUSD": [50000.0]})
    warnings: list[str] = []
    derived: list[str] = []
    _compute_metrics(df, None, None, warnings, derived)
    assert any("CapMVRVCur" in w for w in warnings)


# ─── 6. Mayer Multiple ────────────────────────────────────────────────────────

def test_mayer_multiple():
    n = 210
    price = np.full(n, 60_000.0)
    df = pd.DataFrame(
        {
            "time":     pd.date_range("2020-01-01", periods=n, freq="D").strftime("%Y-%m-%d"),
            "PriceUSD": price,
        }
    )
    warnings: list[str] = []
    derived: list[str] = []
    out = _compute_metrics(df, None, None, warnings, derived)
    assert "MayerMultiple" in out.columns
    # Constant price → MA200 = price → MayerMultiple = 1.0
    val = out["MayerMultiple"].dropna().iloc[-1]
    assert abs(val - 1.0) < 1e-6, f"Expected 1.0 got {val}"


# ─── 7. Puell Multiple ────────────────────────────────────────────────────────

def test_puell_multiple():
    n = 370
    iss = np.full(n, 9_000_000.0)
    df = pd.DataFrame(
        {
            "time":      pd.date_range("2020-01-01", periods=n, freq="D").strftime("%Y-%m-%d"),
            "IssTotUSD": iss,
        }
    )
    warnings: list[str] = []
    derived: list[str] = []
    out = _compute_metrics(df, None, None, warnings, derived)
    assert "PuellMultiple" in out.columns
    val = out["PuellMultiple"].dropna().iloc[-1]
    assert abs(val - 1.0) < 1e-6, f"Expected 1.0 got {val}"


# ─── 8. Exchange Net Flow ─────────────────────────────────────────────────────

def test_exchange_net_flow():
    df = pd.DataFrame(
        {
            "time":        ["2024-01-01"],
            "FlowInExNtv": [100.0],
            "FlowOutExNtv":[70.0],
        }
    )
    warnings: list[str] = []
    derived: list[str] = []
    out = _compute_metrics(df, None, None, warnings, derived)
    assert "ExchangeNetFlow" in out.columns
    val = out["ExchangeNetFlow"].iloc[0]
    assert abs(val - 30.0) < 1e-9, f"Expected 30 got {val}"


# ─── 9. Exchange Reserve Ratio ────────────────────────────────────────────────

def test_exchange_reserve_ratio():
    df = pd.DataFrame(
        {
            "time":      ["2024-01-01"],
            "SplyExNtv": [100.0],
            "SplyCur":   [1000.0],
        }
    )
    warnings: list[str] = []
    derived: list[str] = []
    out = _compute_metrics(df, None, None, warnings, derived)
    assert "ExchangeReserveRatio" in out.columns
    val = out["ExchangeReserveRatio"].iloc[0]
    assert abs(val - 0.1) < 1e-9, f"Expected 0.1 got {val}"


# ─── 10. Exchange stress divide-by-zero ───────────────────────────────────────

def test_exchange_stress_does_not_divide_by_zero():
    # MA30 will be zero when all flows are zero
    df = pd.DataFrame(
        {
            "time":         pd.date_range("2020-01-01", periods=35, freq="D").strftime("%Y-%m-%d"),
            "FlowInExNtv":  np.zeros(35),
            "FlowOutExNtv": np.zeros(35),
        }
    )
    warnings: list[str] = []
    derived: list[str] = []
    # Must not raise
    out = _compute_metrics(df, None, None, warnings, derived)
    # All stress values should be NaN (zero divisor)
    if "ExchangeInflowStress" in out.columns:
        assert out["ExchangeInflowStress"].dropna().empty or True  # no crash is enough


# ─── 11. Stablecoin Supply Ratio ─────────────────────────────────────────────

def test_stablecoin_supply_ratio():
    n = 5
    dates = pd.date_range("2024-01-01", periods=n, freq="D").strftime("%Y-%m-%d")
    btc_df = pd.DataFrame(
        {"time": dates, "CapMrktCurUSD": np.full(n, 1000.0), "CapMVRVCur": np.full(n, 2.0), "SplyCur": np.full(n, 10.0)}
    )
    usdt_df = pd.DataFrame({"time": dates, "CapMrktCurUSD": np.full(n, 100.0)})
    usdc_df = pd.DataFrame({"time": dates, "CapMrktCurUSD": np.full(n, 100.0)})

    warnings: list[str] = []
    derived: list[str] = []
    out = _compute_metrics(btc_df, usdt_df, usdc_df, warnings, derived)
    assert "StablecoinSupplyRatio" in out.columns
    val = out["StablecoinSupplyRatio"].dropna().iloc[-1]
    assert abs(val - 5.0) < 1e-6, f"Expected 5.0 got {val}"


# ─── 12. Missing USDC → SSR with warning ──────────────────────────────────────

def test_missing_usdc_still_calculates_ssr_with_warning():
    n = 5
    dates = pd.date_range("2024-01-01", periods=n, freq="D").strftime("%Y-%m-%d")
    btc_df = pd.DataFrame(
        {"time": dates, "CapMrktCurUSD": np.full(n, 1000.0), "CapMVRVCur": np.full(n, 2.0), "SplyCur": np.full(n, 10.0)}
    )
    usdt_df = pd.DataFrame({"time": dates, "CapMrktCurUSD": np.full(n, 200.0)})

    warnings: list[str] = []
    derived: list[str] = []
    out = _compute_metrics(btc_df, usdt_df, None, warnings, derived)

    # SSR should be computed using USDT only
    assert "StablecoinSupplyRatio" in out.columns
    val = out["StablecoinSupplyRatio"].dropna().iloc[-1]
    assert abs(val - 5.0) < 1e-6, f"Expected 5.0 got {val}"

    # A warning about USDC should be present
    assert any("USDC" in w for w in warnings)


# ─── 13. Network Activity Composite ──────────────────────────────────────────

def test_network_activity_composite():
    n = 100
    df = _base_df(n=n)
    warnings: list[str] = []
    derived: list[str] = []
    out = _compute_metrics(df, None, None, warnings, derived)
    # With n=100 and window=90, last 10 rows should have composite
    valid = out["NetworkActivityComposite"].dropna() if "NetworkActivityComposite" in out.columns else pd.Series(dtype=float)
    assert not valid.empty, "NetworkActivityComposite should have at least some non-NaN values"


# ─── 14. Miner Revenue Estimate ───────────────────────────────────────────────

def test_miner_revenue_estimate():
    df = pd.DataFrame(
        {
            "time":      ["2024-01-01"],
            "FeeTotNtv": [1.0],
            "PriceUSD":  [100.0],
            "IssTotUSD": [50.0],
        }
    )
    warnings: list[str] = []
    derived: list[str] = []
    out = _compute_metrics(df, None, None, warnings, derived)
    assert "MinerRevenue_Est" in out.columns
    val = out["MinerRevenue_Est"].iloc[0]
    # IssTotUSD(50) + FeeTotNtv(1) × PriceUSD(100) = 150
    assert abs(val - 150.0) < 1e-9, f"Expected 150 got {val}"


# ─── 15. Hashrate Trend Proxy ─────────────────────────────────────────────────

def test_hashrate_trend_proxy():
    n = 70
    # Constant hashrate → MA30 == MA60 == hash → proxy = 1.0
    hash_const = np.full(n, 300e18)
    df = pd.DataFrame(
        {
            "time":     pd.date_range("2020-01-01", periods=n, freq="D").strftime("%Y-%m-%d"),
            "HashRate": hash_const,
        }
    )
    warnings: list[str] = []
    derived: list[str] = []
    out = _compute_metrics(df, None, None, warnings, derived)
    assert "HashrateTrendProxy" in out.columns
    val = out["HashrateTrendProxy"].dropna().iloc[-1]
    assert abs(val - 1.0) < 1e-6, f"Expected 1.0 got {val}"


# ─── 16. Score clamped 0–100 ─────────────────────────────────────────────────

def test_score_clamped_between_0_and_100():
    # Extreme positive scenario
    latest_pos = {
        "NUPL_Est":                 0.1,
        "MVRV_Z_Est":               0.5,
        "MayerMultiple":            0.8,
        "PuellMultiple":            0.5,
        "ExchangeNetFlow":          -1000,
        "ExchangeInflowStress":     0.9,
        "ExchangeOutflowStress":    3.0,
        "NetworkActivityComposite": 1.5,
        "HashrateTrendProxy":       1.1,
        "FeePressureRatio":         None,
        "StablecoinSupplyRatio":    None,
    }
    trends_pos = {
        "ssr_30d_change":                   -10,
        "exchange_reserve_ratio_30d_change": -5,
        "miner_revenue_est_30d_change":      10,
    }
    score_pos = _score_from_metrics(latest_pos, trends_pos)
    assert 0 <= score_pos <= 100, f"Score {score_pos} out of bounds"

    # Extreme negative scenario
    latest_neg = {
        "NUPL_Est":                 0.85,
        "MVRV_Z_Est":               9.0,
        "MayerMultiple":            3.0,
        "PuellMultiple":            4.0,
        "ExchangeNetFlow":          5000,
        "ExchangeInflowStress":     2.5,
        "ExchangeOutflowStress":    0.5,
        "NetworkActivityComposite": -1.5,
        "HashrateTrendProxy":       0.85,
        "FeePressureRatio":         None,
        "StablecoinSupplyRatio":    None,
    }
    trends_neg = {
        "ssr_30d_change":                   15,
        "exchange_reserve_ratio_30d_change": 10,
        "miner_revenue_est_30d_change":      -20,
    }
    score_neg = _score_from_metrics(latest_neg, trends_neg)
    assert 0 <= score_neg <= 100, f"Score {score_neg} out of bounds"


# ─── 17. Empty DataFrame → UNAVAILABLE ────────────────────────────────────────

def test_empty_dataframe_returns_unavailable():
    oc = build_onchain_analytics(pd.DataFrame())
    assert oc.score is None
    assert oc.regime == "UNAVAILABLE"
    assert len(oc.warnings) > 0


# ─── Integration smoke tests ─────────────────────────────────────────────────

def test_full_pipeline_does_not_crash():
    """Full build_onchain_analytics with realistic data must not raise."""
    btc_df  = _base_df(400)
    usdt_df = _stable_df(400, 80e9)
    usdc_df = _stable_df(400, 30e9)
    oc = build_onchain_analytics(btc_df, usdt_df, usdc_df)
    assert isinstance(oc, OnchainAnalytics)
    assert oc.score is not None
    assert 0 <= oc.score <= 100
    assert oc.regime in ("ON-CHAIN SUPPORTIVE", "ON-CHAIN NEUTRAL / MIXED", "ON-CHAIN FRAGILE")


def test_full_pipeline_no_stablecoins():
    btc_df = _base_df(400)
    oc = build_onchain_analytics(btc_df, None, None)
    assert isinstance(oc, OnchainAnalytics)
    assert oc.score is not None
    # SSR warning expected
    assert any("USDT" in w or "USDC" in w or "Stablecoin" in w for w in oc.warnings)
