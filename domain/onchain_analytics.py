"""
SA Finance Alpha Terminal — On-Chain Analytics Domain
Computes derived metrics, on-chain score (0-100) and driver summaries
from Coin Metrics BTC / USDT / USDC DataFrames.

Design constraints:
  - Never mutates input DataFrames (always works on copies).
  - Never raises; missing data → warnings list, graceful fallback.
  - No SettingWithCopyWarning: all assignments on explicit copies.
  - All new columns use the canonical internal naming standard.
  - Score clamped to [0, 100].
  - Empty DF → score=None, regime="UNAVAILABLE".
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

# ── Regime thresholds ─────────────────────────────────────────────────────────
_SCORE_START       = 50
_REGIME_SUPPORTIVE = 65
_REGIME_FRAGILE    = 40


# ─── Dataclass ───────────────────────────────────────────────────────────────

@dataclass
class OnchainAnalytics:
    latest: dict
    trends: dict
    score: Optional[int]
    regime: str
    positive_drivers: list[str]
    negative_drivers: list[str]
    neutral_drivers: list[str]
    warnings: list[str]
    derived_columns: list[str]


# ─── Scalar helpers ───────────────────────────────────────────────────────────

def safe_numeric(series: pd.Series) -> pd.Series:
    """Coerce to numeric; replace inf with NaN."""
    s = pd.to_numeric(series, errors="coerce")
    return s.replace([np.inf, -np.inf], np.nan)


def safe_divide(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    """Element-wise division; NaN where denominator is 0 or NaN."""
    denom = denominator.replace(0, np.nan)
    return numerator / denom


def rolling_mean(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window=window, min_periods=window).mean()


def rolling_zscore(series: pd.Series, window: int) -> pd.Series:
    m = series.rolling(window=window, min_periods=window).mean()
    s = series.rolling(window=window, min_periods=window).std(ddof=0)
    s = s.replace(0, np.nan)
    return (series - m) / s


def pct_change(series: pd.Series, periods: int = 1) -> pd.Series:
    return series.pct_change(periods=periods) * 100


def latest_valid_value(series: pd.Series) -> Optional[float]:
    """Return last non-NaN value or None."""
    clean = series.dropna()
    if clean.empty:
        return None
    val = clean.iloc[-1]
    if math.isnan(val) or math.isinf(val):
        return None
    return float(val)


def _lv(df: pd.DataFrame, col: str) -> Optional[float]:
    if col not in df.columns:
        return None
    return latest_valid_value(df[col])


# ─── Metric computation ────────────────────────────────────────────────────────

def _compute_metrics(
    df: pd.DataFrame,
    usdt_df: Optional[pd.DataFrame],
    usdc_df: Optional[pd.DataFrame],
    warnings: list[str],
    derived: list[str],
) -> pd.DataFrame:
    """
    Add all derived columns to a COPY of df.
    Never modifies original.
    """
    out = df.copy()

    # ── 1. Estimated NUPL ─────────────────────────────────────────────────
    if "CapMVRVCur" in out.columns:
        mvrv = safe_numeric(out["CapMVRVCur"])
        # NUPL_Est = 1 - (1 / MVRV)  ; only when MVRV > 0
        valid_mvrv = mvrv.where(mvrv > 0, other=np.nan)
        out = out.copy()
        out["NUPL_Est"] = 1.0 - (1.0 / valid_mvrv)
        derived.append("NUPL_Est")
    else:
        warnings.append(
            "CapMVRVCur missing; estimated NUPL and estimated realized cap cannot be calculated."
        )

    # ── 2. Estimated Realized Cap ─────────────────────────────────────────
    if "CapMrktCurUSD" in out.columns and "CapMVRVCur" in out.columns:
        mcap  = safe_numeric(out["CapMrktCurUSD"])
        mvrv2 = safe_numeric(out["CapMVRVCur"]).where(safe_numeric(out["CapMVRVCur"]) > 0, np.nan)
        out["CapRealized_Est"] = mcap / mvrv2
        derived.append("CapRealized_Est")
    elif "CapMrktCurUSD" not in out.columns:
        warnings.append(
            "CapMrktCurUSD missing; estimated realized cap and estimated MVRV Z-Score cannot be calculated."
        )

    # ── 3. Estimated Realized Price ───────────────────────────────────────
    if "CapRealized_Est" in out.columns and "SplyCur" in out.columns:
        sply = safe_numeric(out["SplyCur"]).where(safe_numeric(out["SplyCur"]) > 0, np.nan)
        out["RealizedPrice_Est"] = safe_numeric(out["CapRealized_Est"]) / sply
        derived.append("RealizedPrice_Est")

    # ── 4. Estimated MVRV Z-Score ─────────────────────────────────────────
    if "CapMrktCurUSD" in out.columns and "CapRealized_Est" in out.columns:
        mcap  = safe_numeric(out["CapMrktCurUSD"])
        rcap  = safe_numeric(out["CapRealized_Est"])
        mcap_std = mcap.std(skipna=True)
        if mcap_std and not math.isnan(mcap_std) and mcap_std > 0:
            out["MVRV_Z_Est"] = (mcap - rcap) / mcap_std
            derived.append("MVRV_Z_Est")
        else:
            warnings.append(
                "Insufficient market cap history; estimated MVRV Z-Score cannot be calculated."
            )

    # ── 5. Mayer Multiple ─────────────────────────────────────────────────
    if "PriceUSD" in out.columns:
        price = safe_numeric(out["PriceUSD"])
        ma200 = rolling_mean(price, 200)
        out["MayerMultiple"] = safe_divide(price, ma200)
        derived.append("MayerMultiple")

    # ── 6. Puell Multiple ─────────────────────────────────────────────────
    if "IssTotUSD" in out.columns:
        iss = safe_numeric(out["IssTotUSD"])
        ma365 = rolling_mean(iss, 365)
        out["PuellMultiple"] = safe_divide(iss, ma365)
        derived.append("PuellMultiple")

    # ── 7. Stablecoin Supply Ratio ────────────────────────────────────────
    # time kolonlari farkli dtype olabilir (str vs datetime64).
    # Guvli merge icin tum time kolonlarini normalize et (date-only datetime64).
    def _norm_time(df: pd.DataFrame) -> pd.DataFrame:
        d = df.copy()
        if "time" in d.columns:
            d["time"] = pd.to_datetime(d["time"], errors="coerce").dt.normalize()
        return d

    if "time" in out.columns:
        out["time"] = pd.to_datetime(out["time"], errors="coerce").dt.normalize()

    stable_cap: Optional[pd.Series] = None
    if usdt_df is not None and not usdt_df.empty and "CapMrktCurUSD" in usdt_df.columns:
        if usdc_df is not None and not usdc_df.empty and "CapMrktCurUSD" in usdc_df.columns:
            usdt_m = _norm_time(usdt_df[["time", "CapMrktCurUSD"]]).rename(columns={"CapMrktCurUSD": "_usdt"})
            usdc_m = _norm_time(usdc_df[["time", "CapMrktCurUSD"]]).rename(columns={"CapMrktCurUSD": "_usdc"})
            merged = usdt_m.merge(usdc_m, on="time", how="outer")
            merged["_usdt"] = safe_numeric(merged.get("_usdt", pd.Series(dtype=float)))
            merged["_usdc"] = safe_numeric(merged.get("_usdc", pd.Series(dtype=float)))
            merged["_stable_total"] = merged["_usdt"].fillna(0) + merged["_usdc"].fillna(0)
            if "time" in out.columns:
                out = out.merge(merged[["time", "_stable_total"]], on="time", how="left")
                stable_cap = safe_numeric(out["_stable_total"]).where(
                    safe_numeric(out["_stable_total"]) > 0, np.nan
                )
        else:
            warnings.append("USDC data unavailable; Stablecoin Supply Ratio uses USDT only.")
            usdt_m = _norm_time(usdt_df[["time", "CapMrktCurUSD"]]).rename(columns={"CapMrktCurUSD": "_stable_total"})
            if "time" in out.columns:
                out = out.merge(usdt_m, on="time", how="left")
                stable_cap = safe_numeric(out["_stable_total"]).where(
                    safe_numeric(out["_stable_total"]) > 0, np.nan
                )
    elif usdc_df is not None and not usdc_df.empty and "CapMrktCurUSD" in usdc_df.columns:
        warnings.append("USDT data unavailable; Stablecoin Supply Ratio uses USDC only.")
        usdc_m = _norm_time(usdc_df[["time", "CapMrktCurUSD"]]).rename(columns={"CapMrktCurUSD": "_stable_total"})
        if "time" in out.columns:
            out = out.merge(usdc_m, on="time", how="left")
            stable_cap = safe_numeric(out["_stable_total"]).where(
                safe_numeric(out["_stable_total"]) > 0, np.nan
            )
    else:
        warnings.append("Both USDT and USDC unavailable; Stablecoin Supply Ratio cannot be calculated.")

    if stable_cap is not None and "CapMrktCurUSD" in out.columns:
        btc_cap = safe_numeric(out["CapMrktCurUSD"]).where(
            safe_numeric(out["CapMrktCurUSD"]) > 0, np.nan
        )
        out["StablecoinSupplyRatio"] = safe_divide(btc_cap, stable_cap)
        derived.append("StablecoinSupplyRatio")

    # ── 8. Exchange Net Flow ──────────────────────────────────────────────
    if "FlowInExNtv" in out.columns and "FlowOutExNtv" in out.columns:
        out["ExchangeNetFlow"] = (
            safe_numeric(out["FlowInExNtv"]) - safe_numeric(out["FlowOutExNtv"])
        )
        derived.append("ExchangeNetFlow")

    # ── 9. Exchange Reserve Ratio ─────────────────────────────────────────
    if "SplyExNtv" in out.columns and "SplyCur" in out.columns:
        sply_ex  = safe_numeric(out["SplyExNtv"]).where(safe_numeric(out["SplyExNtv"]) >= 0, np.nan)
        sply_cur = safe_numeric(out["SplyCur"]).where(safe_numeric(out["SplyCur"]) > 0, np.nan)
        out["ExchangeReserveRatio"] = sply_ex / sply_cur
        derived.append("ExchangeReserveRatio")

    # ── 10. Exchange Inflow Stress ────────────────────────────────────────
    if "FlowInExNtv" in out.columns:
        flow_in = safe_numeric(out["FlowInExNtv"])
        ma30_in = rolling_mean(flow_in, 30).where(rolling_mean(flow_in, 30) > 0, np.nan)
        out["ExchangeInflowStress"] = safe_divide(flow_in, ma30_in)
        derived.append("ExchangeInflowStress")

    # ── 11. Exchange Outflow Stress ───────────────────────────────────────
    if "FlowOutExNtv" in out.columns:
        flow_out = safe_numeric(out["FlowOutExNtv"])
        ma30_out = rolling_mean(flow_out, 30).where(rolling_mean(flow_out, 30) > 0, np.nan)
        out["ExchangeOutflowStress"] = safe_divide(flow_out, ma30_out)
        derived.append("ExchangeOutflowStress")

    # ── 12. Network Activity Composite ────────────────────────────────────
    z_series: list[pd.Series] = []
    for col in ["AdrActCnt", "TxCnt", "TxTfrCnt"]:
        if col in out.columns:
            z = rolling_zscore(safe_numeric(out[col]), 90)
            z_series.append(z)
        else:
            warnings.append(f"{col} missing; NetworkActivityComposite uses available columns only.")
    if z_series:
        stacked = pd.concat(z_series, axis=1)
        out["NetworkActivityComposite"] = stacked.mean(axis=1)
        derived.append("NetworkActivityComposite")
    else:
        warnings.append("No columns available for NetworkActivityComposite.")

    # ── 13. Fee Pressure Ratio ────────────────────────────────────────────
    if "FeeTotNtv" in out.columns:
        fee = safe_numeric(out["FeeTotNtv"])
        if "TxCnt" in out.columns:
            denom_col = safe_numeric(out["TxCnt"]).where(safe_numeric(out["TxCnt"]) > 0, np.nan)
        elif "TxTfrCnt" in out.columns:
            denom_col = safe_numeric(out["TxTfrCnt"]).where(safe_numeric(out["TxTfrCnt"]) > 0, np.nan)
        else:
            denom_col = None
        if denom_col is not None:
            out["FeePressureRatio"] = safe_divide(fee, denom_col)
            derived.append("FeePressureRatio")

    # ── 14. Miner Revenue Estimate ────────────────────────────────────────
    if "FeeTotNtv" in out.columns and "PriceUSD" in out.columns and "IssTotUSD" in out.columns:
        fee_ntv = safe_numeric(out["FeeTotNtv"]).where(safe_numeric(out["FeeTotNtv"]) >= 0, np.nan)
        price   = safe_numeric(out["PriceUSD"]).where(safe_numeric(out["PriceUSD"]) > 0, np.nan)
        iss_usd = safe_numeric(out["IssTotUSD"]).where(safe_numeric(out["IssTotUSD"]) >= 0, np.nan)
        out["FeeTotUSD_Est"]    = fee_ntv * price
        out["MinerRevenue_Est"] = iss_usd + out["FeeTotUSD_Est"]
        derived.extend(["FeeTotUSD_Est", "MinerRevenue_Est"])

    # ── 15. Hashrate Trend Proxy ──────────────────────────────────────────
    if "HashRate" in out.columns:
        hr   = safe_numeric(out["HashRate"]).where(safe_numeric(out["HashRate"]) > 0, np.nan)
        ma30 = rolling_mean(hr, 30).where(rolling_mean(hr, 30) > 0, np.nan)
        ma60 = rolling_mean(hr, 60).where(rolling_mean(hr, 60) > 0, np.nan)
        out["HashrateTrendProxy"] = safe_divide(ma30, ma60)
        derived.append("HashrateTrendProxy")

    # ── Clean up helper merge columns ─────────────────────────────────────
    for tmp in ["_usdt", "_usdc", "_stable_total"]:
        if tmp in out.columns:
            out = out.drop(columns=[tmp])

    # ── Final NaN/inf sweep ───────────────────────────────────────────────
    out = out.replace([np.inf, -np.inf], np.nan)

    return out


# ─── Latest dict ─────────────────────────────────────────────────────────────

_LATEST_KEYS: list[str] = [
    "CapMVRVCur", "AdrActCnt", "AdrBalCnt",
    "FlowInExNtv", "FlowOutExNtv", "SplyExNtv",
    "TxCnt", "TxTfrCnt", "HashRate", "FeeTotNtv",
    "ROI30d", "ROI1yr", "volume_reported_spot_usd_1d",
    "CapMrktCurUSD", "PriceUSD",
    "NUPL_Est", "CapRealized_Est", "RealizedPrice_Est",
    "MVRV_Z_Est", "MayerMultiple", "PuellMultiple",
    "StablecoinSupplyRatio", "ExchangeNetFlow",
    "ExchangeReserveRatio", "ExchangeInflowStress",
    "ExchangeOutflowStress", "NetworkActivityComposite",
    "FeePressureRatio", "FeeTotUSD_Est", "MinerRevenue_Est",
    "HashrateTrendProxy",
]

_ALIASES = {
    "nupl_estimated":          "NUPL_Est",
    "realized_cap_estimated":  "CapRealized_Est",
    "mvrv_z_estimated":        "MVRV_Z_Est",
}


def _build_latest(df: pd.DataFrame) -> dict:
    out: dict = {}
    for key in _LATEST_KEYS:
        out[key] = _lv(df, key)
    # backward-compat aliases
    for alias, canonical in _ALIASES.items():
        out[alias] = out.get(canonical)
    return out


# ─── Trends dict ─────────────────────────────────────────────────────────────

def _build_trends(df: pd.DataFrame) -> dict:
    trends: dict = {}

    def _change(col: str, periods: int) -> Optional[float]:
        if col not in df.columns:
            return None
        s = safe_numeric(df[col]).dropna()
        if len(s) <= periods:
            return None
        val_now  = float(s.iloc[-1])
        val_prev = float(s.iloc[-1 - periods])
        if val_prev == 0 or math.isnan(val_prev):
            return None
        return round((val_now - val_prev) / abs(val_prev) * 100, 4)

    pairs: list[tuple[str, str, int]] = [
        ("CapMVRVCur",             "CapMVRVCur_7d_change",  7),
        ("CapMVRVCur",             "CapMVRVCur_30d_change", 30),
        ("AdrActCnt",              "AdrActCnt_7d_change",   7),
        ("AdrActCnt",              "AdrActCnt_30d_change",  30),
        ("SplyExNtv",              "SplyExNtv_7d_change",   7),
        ("SplyExNtv",              "SplyExNtv_30d_change",  30),
        ("PriceUSD",               "PriceUSD_7d_change",    7),
        ("PriceUSD",               "PriceUSD_30d_change",   30),
        ("NUPL_Est",               "nupl_est_7d_change",    7),
        ("NUPL_Est",               "nupl_est_30d_change",   30),
        ("RealizedPrice_Est",      "realized_price_est_30d_change", 30),
        ("MVRV_Z_Est",             "mvrv_z_est_7d_change",  7),
        ("MVRV_Z_Est",             "mvrv_z_est_30d_change", 30),
        ("MayerMultiple",          "mayer_multiple_30d_change", 30),
        ("PuellMultiple",          "puell_multiple_30d_change", 30),
        ("StablecoinSupplyRatio",  "ssr_30d_change",         30),
        ("ExchangeReserveRatio",   "exchange_reserve_ratio_30d_change", 30),
        ("NetworkActivityComposite","network_activity_composite_30d_change", 30),
        ("MinerRevenue_Est",       "miner_revenue_est_30d_change", 30),
        ("HashrateTrendProxy",     "hashrate_trend_proxy_30d_change", 30),
    ]
    for col, key, periods in pairs:
        trends[key] = _change(col, periods)

    return trends


# ─── Score logic ─────────────────────────────────────────────────────────────

def _clamp(score: float) -> int:
    return max(0, min(100, int(round(score))))


def _score_from_metrics(latest: dict, trends: dict) -> int:
    score = float(_SCORE_START)

    # ── Estimated NUPL ────────────────────────────────────────────────────
    nupl = latest.get("NUPL_Est")
    if nupl is not None:
        if nupl < 0.25:
            score += 5
        elif nupl <= 0.50:
            score += 2
        elif nupl <= 0.70:
            score -= 5
        else:
            score -= 10

    # ── Estimated MVRV Z-Score ────────────────────────────────────────────
    mz = latest.get("MVRV_Z_Est")
    if mz is not None:
        if mz < 2:
            score += 5
        elif mz <= 5:
            score += 1
        elif mz <= 7:
            score -= 6
        else:
            score -= 12

    # ── Mayer Multiple ────────────────────────────────────────────────────
    mm = latest.get("MayerMultiple")
    if mm is not None:
        if mm < 1.0:
            score += 3
        elif mm <= 1.5:
            score += 2
        elif mm <= 2.4:
            score -= 3
        else:
            score -= 8

    # ── Puell Multiple ────────────────────────────────────────────────────
    pm = latest.get("PuellMultiple")
    if pm is not None:
        if pm < 0.7:
            score += 4
        elif pm <= 1.5:
            score += 2
        elif pm <= 3.0:
            score -= 3
        else:
            score -= 8

    # ── Stablecoin Supply Ratio (30d change) ──────────────────────────────
    ssr_chg = trends.get("ssr_30d_change")
    if ssr_chg is not None:
        if ssr_chg < -5:
            score += 5
        elif ssr_chg > 5:
            score -= 5

    # ── Exchange Net Flow ─────────────────────────────────────────────────
    enf = latest.get("ExchangeNetFlow")
    if enf is not None:
        if enf < 0:
            score += 5
        elif enf > 0:
            score -= 5

    # ── Exchange Reserve Ratio (30d change) ───────────────────────────────
    err_chg = trends.get("exchange_reserve_ratio_30d_change")
    if err_chg is not None:
        if err_chg < 0:
            score += 4
        elif err_chg > 0:
            score -= 4

    # ── Exchange Inflow Stress ────────────────────────────────────────────
    eis = latest.get("ExchangeInflowStress")
    if eis is not None:
        if eis > 2.0:
            score -= 8
        elif eis > 1.5:
            score -= 4

    # ── Exchange Outflow Stress ───────────────────────────────────────────
    eos = latest.get("ExchangeOutflowStress")
    if eos is not None:
        if eos > 2.0:
            score += 5
        elif eos > 1.5:
            score += 3

    # ── Network Activity Composite ────────────────────────────────────────
    nac = latest.get("NetworkActivityComposite")
    if nac is not None:
        if nac > 0.5:
            score += 5
        elif nac < -0.5:
            score -= 5

    # ── Hashrate Trend Proxy ──────────────────────────────────────────────
    htp = latest.get("HashrateTrendProxy")
    if htp is not None:
        if htp > 1.05:
            score += 3
        elif htp < 0.95:
            score -= 3

    # ── Miner Revenue Estimate (30d, soft ±2) ─────────────────────────────
    mr_chg = trends.get("miner_revenue_est_30d_change")
    if mr_chg is not None:
        if mr_chg > 0:
            score += 2
        elif mr_chg < 0:
            score -= 2

    return _clamp(score)


def _regime_label(score: int) -> str:
    if score >= _REGIME_SUPPORTIVE:
        return "ON-CHAIN SUPPORTIVE"
    if score <= _REGIME_FRAGILE:
        return "ON-CHAIN FRAGILE"
    return "ON-CHAIN NEUTRAL / MIXED"


# ─── Driver logic ─────────────────────────────────────────────────────────────

def _build_drivers(latest: dict, trends: dict) -> tuple[list[str], list[str], list[str]]:
    pos: list[str] = []
    neg: list[str] = []
    neu: list[str] = []

    # ── Estimated NUPL ────────────────────────────────────────────────────
    nupl = latest.get("NUPL_Est")
    if nupl is not None:
        if nupl < 0:
            pos.append("Estimated NUPL capitulation / unrealized loss bölgesinde.")
        elif nupl < 0.25:
            pos.append("Estimated NUPL düşük-orta kâr bölgesinde; aşırı ısınma sinyali sınırlı.")
        elif nupl < 0.50:
            neu.append("Estimated NUPL orta kâr bölgesinde.")
        elif nupl < 0.70:
            neg.append("Estimated NUPL yüksek kâr bölgesine yaklaşıyor; kâr realizasyonu riski artıyor.")
        else:
            neg.append("Estimated NUPL tarihsel olarak aşırı kâr / ısınma bölgesinde.")

    # ── Estimated MVRV Z-Score ────────────────────────────────────────────
    mz = latest.get("MVRV_Z_Est")
    if mz is not None:
        if mz < 0:
            pos.append("Estimated MVRV Z-Score düşük/değerleme baskısı bölgesinde.")
        elif mz < 2:
            pos.append("Estimated MVRV Z-Score düşük-normal değerleme bölgesinde.")
        elif mz < 5:
            neu.append("Estimated MVRV Z-Score boğa genişleme bölgesinde.")
        elif mz < 7:
            neg.append("Estimated MVRV Z-Score ısınma bölgesine yaklaşıyor.")
        else:
            neg.append("Estimated MVRV Z-Score tarihsel aşırı değerleme bölgesinde.")

    # ── Mayer Multiple ────────────────────────────────────────────────────
    mm = latest.get("MayerMultiple")
    if mm is not None:
        if mm <= 1.5:
            neu.append("Mayer Multiple trend üstü ama aşırı ısınma bölgesinde değil.") if mm >= 1.0 else pos.append("Mayer Multiple uzun vadeli ortalamanın altında.")
        else:
            neg.append("Mayer Multiple tarihsel ısınma bölgesine yaklaşıyor.")

    # ── Puell Multiple ────────────────────────────────────────────────────
    pm = latest.get("PuellMultiple")
    if pm is not None:
        if pm < 0.7:
            pos.append("Puell Multiple madenci gelir tarafında tarihsel dip bölgesinde.")
        elif pm <= 1.5:
            pos.append("Puell Multiple normal madenci gelir bölgesinde.")
        elif pm <= 3.0:
            neg.append("Puell Multiple yükselmiş madenci geliri gösteriyor.")
        else:
            neg.append("Puell Multiple madenci gelir tarafında tarihsel ısınma riskine işaret ediyor.")

    # ── Exchange Net Flow ─────────────────────────────────────────────────
    enf = latest.get("ExchangeNetFlow")
    if enf is not None:
        if enf < 0:
            pos.append("Borsalardan net BTC çıkışı var; spot arz baskısı azalıyor.")
        else:
            neg.append("Borsalara net BTC girişi var; potansiyel satış baskısı artıyor.")

    # ── Exchange Reserve Ratio ────────────────────────────────────────────
    err_chg = trends.get("exchange_reserve_ratio_30d_change")
    if err_chg is not None:
        if err_chg < 0:
            pos.append("Exchange reserve ratio 30 günlük bazda düşüyor.")
        else:
            neg.append("Exchange reserve ratio 30 günlük bazda artıyor.")

    # ── Exchange Inflow Stress ────────────────────────────────────────────
    eis = latest.get("ExchangeInflowStress")
    if eis is not None:
        if eis > 2.0:
            neg.append("Exchange inflow stress çok yükseldi; borsa girişlerinde anormal artış var.")
        elif eis > 1.5:
            neg.append("Exchange inflow stress yükseldi; borsa girişlerinde anormal artış var.")

    # ── Exchange Outflow Stress ───────────────────────────────────────────
    eos = latest.get("ExchangeOutflowStress")
    if eos is not None:
        if eos > 2.0:
            pos.append("Exchange outflow stress çok güçlü; borsalardan belirgin BTC çıkışı var.")
        elif eos > 1.5:
            pos.append("Exchange outflow stress güçlü; borsalardan BTC çıkışı hızlandı.")

    # ── Network Activity Composite ────────────────────────────────────────
    nac = latest.get("NetworkActivityComposite")
    if nac is not None:
        if nac > 0.5:
            pos.append("Network activity composite pozitif bölgede; ağ kullanımı artıyor.")
        elif nac < -0.5:
            neg.append("Network activity composite zayıf bölgede; ağ kullanımı düşük.")
        else:
            neu.append("Network activity composite nötr bölgede.")

    # ── Stablecoin Supply Ratio ───────────────────────────────────────────
    ssr_chg = trends.get("ssr_30d_change")
    if ssr_chg is not None:
        if ssr_chg < -5:
            pos.append("Stablecoin Supply Ratio 30 günlük bazda düşüyor; stablecoin likiditesi artıyor.")
        elif ssr_chg > 5:
            neg.append("Stablecoin Supply Ratio 30 günlük bazda artıyor; stablecoin likiditesi zayıflıyor.")
        else:
            neu.append("Stablecoin Supply Ratio 30 günlük bazda yatay.")

    # ── Hashrate Trend Proxy ──────────────────────────────────────────────
    htp = latest.get("HashrateTrendProxy")
    if htp is not None:
        if htp > 1.05:
            pos.append("Hashrate trend proxy kısa vadeli ağ gücünün toparlandığını gösteriyor.")
        elif htp < 0.95:
            neg.append("Hashrate trend proxy zayıflıyor; kısa vadeli hash gücü düşüşte.")
        else:
            neu.append("Hashrate trend proxy nötr bölgede.")

    # ── Miner Revenue Estimate ────────────────────────────────────────────
    mr_chg = trends.get("miner_revenue_est_30d_change")
    if mr_chg is not None:
        if mr_chg > 0:
            neu.append("Miner revenue estimate toparlanıyor ancak tek başına yön sinyali değildir.")
        elif mr_chg < 0:
            neg.append("Miner revenue estimate 30 günlük bazda düşüyor.")

    # ── Fee Pressure Ratio ────────────────────────────────────────────────
    fpr = latest.get("FeePressureRatio")
    if fpr is not None and fpr > 0:
        neu.append("Fee pressure ratio hesaplandı; ağ yoğunluğu takipte.")

    return pos, neg, neu


# ─── Main entrypoint ─────────────────────────────────────────────────────────

def build_onchain_analytics(
    btc_df: pd.DataFrame,
    usdt_df: Optional[pd.DataFrame] = None,
    usdc_df: Optional[pd.DataFrame] = None,
) -> OnchainAnalytics:
    """
    Build full on-chain analytics from Coin Metrics DataFrames.
    Never raises. Empty input → score=None, regime=UNAVAILABLE.
    """
    warnings: list[str] = []
    derived: list[str] = []

    # ── Empty guard ───────────────────────────────────────────────────────
    if btc_df is None or btc_df.empty:
        warnings.append("BTC DataFrame boş; on-chain analytics hesaplanamıyor.")
        return OnchainAnalytics(
            latest={},
            trends={},
            score=None,
            regime="UNAVAILABLE",
            positive_drivers=[],
            negative_drivers=[],
            neutral_drivers=[],
            warnings=warnings,
            derived_columns=[],
        )

    # ── Sort by time ──────────────────────────────────────────────────────
    df = btc_df.copy()
    if "time" in df.columns:
        df["time"] = pd.to_datetime(df["time"], errors="coerce")
        df = df.sort_values("time").reset_index(drop=True)

    # ── Normalize stable DFs ──────────────────────────────────────────────
    def _norm_stable(sdf: Optional[pd.DataFrame]) -> Optional[pd.DataFrame]:
        if sdf is None or sdf.empty:
            return None
        s = sdf.copy()
        if "time" in s.columns:
            # Always parse to datetime64 so merge keys match BTC df
            s["time"] = pd.to_datetime(s["time"], errors="coerce")
        if "CapMrktCurUSD" in s.columns:
            s["CapMrktCurUSD"] = safe_numeric(s["CapMrktCurUSD"])
        return s

    usdt_norm = _norm_stable(usdt_df)
    usdc_norm = _norm_stable(usdc_df)

    # ── Compute metrics ───────────────────────────────────────────────────
    try:
        df_computed = _compute_metrics(df, usdt_norm, usdc_norm, warnings, derived)
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"Metric computation error: {exc}")
        df_computed = df

    # ── Latest / trends ───────────────────────────────────────────────────
    latest = _build_latest(df_computed)
    trends = _build_trends(df_computed)

    # ── Score & regime ────────────────────────────────────────────────────
    try:
        score = _score_from_metrics(latest, trends)
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"Score calculation error: {exc}")
        score = None

    regime = _regime_label(score) if score is not None else "UNAVAILABLE"

    # ── Drivers ───────────────────────────────────────────────────────────
    try:
        pos_drivers, neg_drivers, neu_drivers = _build_drivers(latest, trends)
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"Driver build error: {exc}")
        pos_drivers, neg_drivers, neu_drivers = [], [], []

    return OnchainAnalytics(
        latest=latest,
        trends=trends,
        score=score,
        regime=regime,
        positive_drivers=pos_drivers,
        negative_drivers=neg_drivers,
        neutral_drivers=neu_drivers,
        warnings=warnings,
        derived_columns=list(set(derived)),
    )
