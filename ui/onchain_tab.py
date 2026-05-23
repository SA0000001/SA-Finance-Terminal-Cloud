"""
SA Finance Alpha Terminal — ON-CHAIN DASHBOARD Tab
Renders the On-Chain sekme using Coin Metrics data + onchain_analytics.
Follows the existing terminal design language (theme.py CSS variables).
"""
from __future__ import annotations

import math
from typing import Optional

import pandas as pd
import streamlit as st

from domain.onchain_analytics import OnchainAnalytics, build_onchain_analytics
from services.onchain_data import (
    SOURCE_STATUS_CACHED,
    SOURCE_STATUS_FALLBACK,
    SOURCE_STATUS_LIVE,
    SOURCE_STATUS_PARTIAL,
    SOURCE_STATUS_UNAVAILABLE,
    load_all_onchain,
)
from ui.components import esc


# ─── Formatting helpers ───────────────────────────────────────────────────────

def _fmt_usd(value: Optional[float], decimals: int = 2) -> str:
    if value is None or math.isnan(value):
        return "N/A"
    if abs(value) >= 1e12:
        return f"${value / 1e12:.2f}T"
    if abs(value) >= 1e9:
        return f"${value / 1e9:.2f}B"
    if abs(value) >= 1e6:
        return f"${value / 1e6:.2f}M"
    return f"${value:,.{decimals}f}"


def _fmt_btc(value: Optional[float]) -> str:
    if value is None or math.isnan(value):
        return "N/A"
    return f"{value:,.0f} BTC"


def _fmt_ratio(value: Optional[float], decimals: int = 4) -> str:
    if value is None or math.isnan(value):
        return "N/A"
    return f"{value:.{decimals}f}x"


def _fmt_pct(value: Optional[float], decimals: int = 2) -> str:
    if value is None or math.isnan(value):
        return "N/A"
    return f"{value:.{decimals}f}%"


def _fmt_num(value: Optional[float], decimals: int = 2) -> str:
    if value is None or math.isnan(value):
        return "N/A"
    if abs(value) >= 1e12:
        return f"{value / 1e12:.2f}T"
    if abs(value) >= 1e9:
        return f"{value / 1e9:.2f}B"
    if abs(value) >= 1e6:
        return f"{value / 1e6:.2f}M"
    if abs(value) >= 1e3:
        return f"{value / 1e3:.1f}K"
    return f"{value:.{decimals}f}"


def _fmt_score(score: Optional[int]) -> str:
    if score is None:
        return "N/A"
    return f"{score}/100"


def _safe_float(v) -> Optional[float]:
    try:
        f = float(v)
        if math.isnan(f) or math.isinf(f):
            return None
        return f
    except (TypeError, ValueError):
        return None


# ─── Status badge ─────────────────────────────────────────────────────────────

def _status_badge(status: str) -> str:
    color_map = {
        SOURCE_STATUS_LIVE:        ("var(--positive)", "rgba(50,217,140,0.12)"),
        SOURCE_STATUS_CACHED:      ("var(--accent)",   "rgba(82,200,255,0.10)"),
        SOURCE_STATUS_FALLBACK:    ("var(--warning)",  "rgba(240,192,80,0.12)"),
        SOURCE_STATUS_PARTIAL:     ("var(--warning)",  "rgba(240,192,80,0.12)"),
        SOURCE_STATUS_UNAVAILABLE: ("var(--negative)", "rgba(255,95,114,0.12)"),
    }
    c_text, c_bg = color_map.get(status, ("var(--text-muted)", "rgba(255,255,255,0.04)"))
    return (
        f"<span style='padding:3px 10px;border-radius:999px;"
        f"border:1px solid {c_text};background:{c_bg};"
        f"font-family:var(--font-mono);font-size:0.68rem;"
        f"font-weight:700;color:{c_text}'>{esc(status.upper())}</span>"
    )


# ─── Regime badge ─────────────────────────────────────────────────────────────

def _regime_color(regime: str) -> str:
    if "SUPPORTIVE" in regime:
        return "var(--positive)"
    if "FRAGILE" in regime:
        return "var(--negative)"
    if "UNAVAILABLE" in regime:
        return "var(--text-muted)"
    return "var(--warning)"


# ─── Metric card ──────────────────────────────────────────────────────────────

def _metric_card(label: str, value: str, sub: str = "", color: str = "") -> str:
    val_color = color if color else "var(--text-primary)"
    sub_html = (
        f"<div style='font-family:var(--font-mono);font-size:0.62rem;"
        f"color:var(--text-muted);margin-top:3px'>{esc(sub)}</div>"
        if sub else ""
    )
    return (
        f"<div class='metric-card'>"
        f"<div class='mc-label'>{esc(label)}</div>"
        f"<div class='mc-value' style='color:{val_color}'>{esc(value)}</div>"
        f"{sub_html}"
        f"</div>"
    )


def _render_metric_row(items: list[tuple], cols: int = 4) -> None:
    """Render a row of metric cards. Each item: (label, value) or (label, value, sub) or (label, value, sub, color)."""
    columns = st.columns(cols)
    for i, item in enumerate(items):
        label = item[0]
        value = item[1] if len(item) > 1 else "N/A"
        sub   = item[2] if len(item) > 2 else ""
        color = item[3] if len(item) > 3 else ""
        with columns[i % cols]:
            st.markdown(_metric_card(label, value, sub, color), unsafe_allow_html=True)


# ─── Section header ───────────────────────────────────────────────────────────

def _section_header(kicker: str, title: str = "") -> None:
    title_html = (
        f"<div style='font-size:1.0rem;font-weight:700;color:var(--text-primary);margin-top:2px'>{esc(title)}</div>"
        if title else ""
    )
    st.markdown(
        f"<div style='font-family:var(--font-mono);font-size:0.62rem;"
        f"letter-spacing:0.16em;text-transform:uppercase;"
        f"color:var(--accent);margin-bottom:4px'>{esc(kicker)}</div>"
        f"{title_html}",
        unsafe_allow_html=True,
    )


# ─── Driver list renderer ─────────────────────────────────────────────────────

def _driver_list(items: list[str], kind: str) -> str:
    """kind: positive | negative | neutral | warning"""
    color_map = {
        "positive": "var(--positive)",
        "negative": "var(--negative)",
        "neutral":  "var(--warning)",
        "warning":  "var(--text-muted)",
    }
    prefix_map = {
        "positive": "▲",
        "negative": "▼",
        "neutral":  "◆",
        "warning":  "⚠",
    }
    color  = color_map.get(kind, "var(--text-muted)")
    prefix = prefix_map.get(kind, "·")
    if not items:
        return ""
    rows = "".join(
        f"<div style='display:flex;gap:8px;align-items:baseline;padding:4px 0;"
        f"border-bottom:1px solid rgba(100,140,185,0.06)'>"
        f"<span style='color:{color};font-size:0.72rem;min-width:12px'>{prefix}</span>"
        f"<span style='font-size:0.78rem;color:var(--text-secondary);line-height:1.5'>{esc(d)}</span>"
        f"</div>"
        for d in items
    )
    return rows


# ─── Chart helpers ────────────────────────────────────────────────────────────

def _try_line_chart(df: pd.DataFrame, cols: list[str], title: str, height: int = 200) -> None:
    """Render line chart only if df has valid data for at least one col."""
    available = [c for c in cols if c in df.columns]
    if not available:
        st.caption(f"ℹ {title}: insufficient data")
        return
    chart_df = df[["time"] + available].copy() if "time" in df.columns else df[available].copy()
    if "time" in chart_df.columns:
        chart_df = chart_df.set_index("time")
    chart_df = chart_df.replace([float("inf"), float("-inf")], None).dropna(how="all")
    if chart_df.empty:
        st.caption(f"ℹ {title}: no data to display")
        return
    st.markdown(
        f"<div style='font-family:var(--font-mono);font-size:0.62rem;"
        f"letter-spacing:0.12em;text-transform:uppercase;"
        f"color:var(--text-muted);margin-bottom:4px'>{esc(title)}</div>",
        unsafe_allow_html=True,
    )
    st.line_chart(chart_df, height=height, use_container_width=True)


# ─── Panels ───────────────────────────────────────────────────────────────────

def _render_overview_panel(
    oc: OnchainAnalytics,
    btc_status: str,
    latest_date: Optional[str],
) -> None:
    _section_header("On-Chain Overview")

    regime_color = _regime_color(oc.regime)
    price = _safe_float(oc.latest.get("PriceUSD"))
    price_str = _fmt_usd(price, 0) if price else "N/A"

    score_str = _fmt_score(oc.score)

    overview_items = [
        ("BTC Price",       price_str,                     "PriceUSD",                ""),
        ("On-Chain Score",  score_str,                     "0–100",                   "var(--accent)"),
        ("On-Chain Regime", oc.regime,                     "",                        regime_color),
        ("Source Status",   btc_status.upper(),            "",                        ""),
        ("Latest Date",     latest_date or "N/A",          "Coin Metrics daily",      ""),
    ]
    _render_metric_row(overview_items, cols=5)


def _render_valuation_panel(oc: OnchainAnalytics, df_computed: Optional[pd.DataFrame]) -> None:
    _section_header("Valuation Layer", "Valuation Panel")

    latest = oc.latest
    mvrv        = _safe_float(latest.get("CapMVRVCur"))
    nupl        = _safe_float(latest.get("NUPL_Est"))
    rcap        = _safe_float(latest.get("CapRealized_Est"))
    rprice      = _safe_float(latest.get("RealizedPrice_Est"))
    mvrv_z      = _safe_float(latest.get("MVRV_Z_Est"))
    mayer       = _safe_float(latest.get("MayerMultiple"))
    mcap        = _safe_float(latest.get("CapMrktCurUSD"))

    items = [
        ("MVRV",                   _fmt_num(mvrv, 2) if mvrv else "N/A",          "Coin Metrics",           ""),
        ("Estimated NUPL",         _fmt_num(nupl, 4) if nupl is not None else "N/A", "Derived from MVRV",  ""),
        ("Estimated Realized Cap", _fmt_usd(rcap) if rcap else "N/A",             "Derived",                ""),
        ("Estimated Realized Price", _fmt_usd(rprice, 0) if rprice else "N/A",    "Derived",                ""),
        ("Estimated MVRV Z-Score", _fmt_num(mvrv_z, 2) if mvrv_z is not None else "N/A", "Derived",        "var(--warning)" if mvrv_z and mvrv_z > 5 else ""),
        ("Mayer Multiple",         _fmt_ratio(mayer, 3) if mayer else "N/A",      "Price / MA200",          ""),
        ("Market Cap",             _fmt_usd(mcap) if mcap else "N/A",             "Coin Metrics",           ""),
    ]
    _render_metric_row(items, cols=4)

    st.markdown(
        "<div style='font-size:0.72rem;color:var(--text-muted);line-height:1.5;"
        "padding:8px 10px;border-radius:6px;border:1px solid var(--border);"
        "background:rgba(255,255,255,0.02);margin-top:8px'>"
        "Estimated NUPL, Estimated Realized Cap, Estimated Realized Price ve "
        "Estimated MVRV Z-Score; Coin Metrics MVRV ve Market Cap verilerinden "
        "türetilmiş yaklaşık metriklerdir. Doğrudan resmi NUPL / Realized Cap "
        "/ Z-Score serisi değildir."
        "</div>",
        unsafe_allow_html=True,
    )

    if df_computed is not None and not df_computed.empty:
        with st.expander("Valuation Charts", expanded=False):
            c1, c2 = st.columns(2)
            with c1:
                _try_line_chart(df_computed, ["PriceUSD", "RealizedPrice_Est"], "Price vs Estimated Realized Price")
                _try_line_chart(df_computed, ["NUPL_Est"], "Estimated NUPL")
                _try_line_chart(df_computed, ["MayerMultiple"], "Mayer Multiple")
            with c2:
                _try_line_chart(df_computed, ["CapMVRVCur", "NUPL_Est"], "MVRV & Estimated NUPL")
                _try_line_chart(df_computed, ["MVRV_Z_Est"], "Estimated MVRV Z-Score")


def _render_exchange_panel(oc: OnchainAnalytics, df_computed: Optional[pd.DataFrame]) -> None:
    _section_header("Exchange Flow Layer", "Exchange Flow Panel")

    latest = oc.latest
    enf     = _safe_float(latest.get("ExchangeNetFlow"))
    err     = _safe_float(latest.get("ExchangeReserveRatio"))
    eis     = _safe_float(latest.get("ExchangeInflowStress"))
    eos     = _safe_float(latest.get("ExchangeOutflowStress"))
    sply_ex = _safe_float(latest.get("SplyExNtv"))
    inflow  = _safe_float(latest.get("FlowInExNtv"))
    outflow = _safe_float(latest.get("FlowOutExNtv"))

    def _flow_color(v: Optional[float], positive_is_bad: bool) -> str:
        if v is None:
            return ""
        if positive_is_bad:
            return "var(--negative)" if v > 0 else "var(--positive)"
        return "var(--positive)" if v > 0 else "var(--negative)"

    items = [
        ("Exchange Net Flow",      _fmt_btc(enf) if enf is not None else "N/A",   "In - Out",               _flow_color(enf, True)),
        ("Exchange Reserve Ratio", _fmt_ratio(err, 4) if err else "N/A",           "SplyEx / SplyCur",       ""),
        ("Exchange Inflow Stress", _fmt_ratio(eis, 2) if eis else "N/A",           "vs MA30",                "var(--negative)" if eis and eis > 1.5 else ""),
        ("Exchange Outflow Stress",_fmt_ratio(eos, 2) if eos else "N/A",           "vs MA30",                "var(--positive)" if eos and eos > 1.5 else ""),
        ("Exchange Supply",        _fmt_btc(sply_ex) if sply_ex else "N/A",        "SplyExNtv",              ""),
        ("Inflow (FlowInExNtv)",   _fmt_btc(inflow) if inflow is not None else "N/A", "",                    ""),
        ("Outflow (FlowOutExNtv)", _fmt_btc(outflow) if outflow is not None else "N/A", "",                  ""),
    ]
    _render_metric_row(items, cols=4)

    if df_computed is not None and not df_computed.empty:
        with st.expander("Exchange Flow Charts", expanded=False):
            c1, c2 = st.columns(2)
            with c1:
                _try_line_chart(df_computed, ["FlowInExNtv", "FlowOutExNtv"], "Inflow / Outflow")
                _try_line_chart(df_computed, ["SplyExNtv"], "Exchange Supply (SplyExNtv)")
            with c2:
                _try_line_chart(df_computed, ["ExchangeNetFlow"], "Exchange Net Flow")
                _try_line_chart(df_computed, ["ExchangeReserveRatio"], "Exchange Reserve Ratio")
                _try_line_chart(df_computed, ["ExchangeInflowStress", "ExchangeOutflowStress"], "Inflow & Outflow Stress")


def _render_miner_network_panel(oc: OnchainAnalytics, df_computed: Optional[pd.DataFrame]) -> None:
    _section_header("Miner & Network Layer", "Miner / Network Panel")

    latest = oc.latest
    puell   = _safe_float(latest.get("PuellMultiple"))
    mr_est  = _safe_float(latest.get("MinerRevenue_Est"))
    htp     = _safe_float(latest.get("HashrateTrendProxy"))
    hr      = _safe_float(latest.get("HashRate"))
    nac     = _safe_float(latest.get("NetworkActivityComposite"))
    fpr     = _safe_float(latest.get("FeePressureRatio"))
    adr     = _safe_float(latest.get("AdrActCnt"))
    txcnt   = _safe_float(latest.get("TxCnt"))
    tftcnt  = _safe_float(latest.get("TxTfrCnt"))

    items = [
        ("Puell Multiple",          _fmt_ratio(puell, 3) if puell else "N/A",          "IssTotUSD / MA365",       ""),
        ("Miner Revenue Estimate",  _fmt_usd(mr_est) if mr_est else "N/A",             "IssTotUSD + Fees×Price",  ""),
        ("Hashrate Trend Proxy",    _fmt_ratio(htp, 4) if htp else "N/A",              "MA30 / MA60",             "var(--positive)" if htp and htp > 1.0 else "var(--warning)"),
        ("Hash Rate",               _fmt_num(hr) if hr else "N/A",                     "HashRate",                ""),
        ("Network Activity",        _fmt_num(nac, 3) if nac is not None else "N/A",    "Z-Score composite",       ""),
        ("Fee Pressure Ratio",      _fmt_num(fpr, 6) if fpr else "N/A",               "FeeTotNtv / TxCnt",       ""),
        ("Active Addresses",        _fmt_num(adr) if adr else "N/A",                   "AdrActCnt",               ""),
        ("TxCnt",                   _fmt_num(txcnt) if txcnt else "N/A",               "",                        ""),
        ("TxTfrCnt",                _fmt_num(tftcnt) if tftcnt else "N/A",             "",                        ""),
    ]
    _render_metric_row(items, cols=4)

    st.markdown(
        "<div style='font-size:0.72rem;color:var(--text-muted);line-height:1.5;"
        "padding:6px 10px;border-radius:6px;border:1px solid var(--border);"
        "background:rgba(255,255,255,0.02);margin-top:6px'>"
        "Miner Revenue Estimate = IssTotUSD + (FeeTotNtv × PriceUSD). "
        "Resmi miner reserve metriği değildir."
        "</div>",
        unsafe_allow_html=True,
    )

    if df_computed is not None and not df_computed.empty:
        with st.expander("Miner & Network Charts", expanded=False):
            c1, c2 = st.columns(2)
            with c1:
                _try_line_chart(df_computed, ["PuellMultiple"], "Puell Multiple")
                _try_line_chart(df_computed, ["MinerRevenue_Est"], "Miner Revenue Estimate")
                _try_line_chart(df_computed, ["HashRate"], "Hash Rate")
            with c2:
                _try_line_chart(df_computed, ["HashrateTrendProxy"], "Hashrate Trend Proxy")
                _try_line_chart(df_computed, ["NetworkActivityComposite"], "Network Activity Composite")
                _try_line_chart(df_computed, ["AdrActCnt"], "Active Addresses")
                _try_line_chart(df_computed, ["TxCnt", "TxTfrCnt"], "TxCnt / TxTfrCnt")


def _render_stablecoin_panel(
    oc: OnchainAnalytics,
    usdt_result,
    usdc_result,
    df_computed: Optional[pd.DataFrame],
) -> None:
    _section_header("Stablecoin Liquidity Layer", "Stablecoin Liquidity Panel")

    latest = oc.latest
    ssr = _safe_float(latest.get("StablecoinSupplyRatio"))

    # USDT / USDC latest market cap
    usdt_cap: Optional[float] = None
    usdc_cap: Optional[float] = None
    if usdt_result and not usdt_result.df.empty and "CapMrktCurUSD" in usdt_result.df.columns:
        s = pd.to_numeric(usdt_result.df["CapMrktCurUSD"], errors="coerce").dropna()
        if not s.empty:
            usdt_cap = float(s.iloc[-1])
    if usdc_result and not usdc_result.df.empty and "CapMrktCurUSD" in usdc_result.df.columns:
        s = pd.to_numeric(usdc_result.df["CapMrktCurUSD"], errors="coerce").dropna()
        if not s.empty:
            usdc_cap = float(s.iloc[-1])

    combined = None
    if usdt_cap is not None and usdc_cap is not None:
        combined = usdt_cap + usdc_cap
    elif usdt_cap is not None:
        combined = usdt_cap
    elif usdc_cap is not None:
        combined = usdc_cap

    items = [
        ("Stablecoin Supply Ratio",    _fmt_ratio(ssr, 2) if ssr else "N/A",       "BTC MCap / Stable MCap",  ""),
        ("USDT Market Cap",            _fmt_usd(usdt_cap) if usdt_cap else "N/A",  "Coin Metrics",            ""),
        ("USDC Market Cap",            _fmt_usd(usdc_cap) if usdc_cap else "N/A",  "Coin Metrics",            ""),
        ("Combined Stablecoin MCap",   _fmt_usd(combined) if combined else "N/A",  "USDT + USDC",             ""),
    ]
    _render_metric_row(items, cols=4)

    if df_computed is not None and not df_computed.empty:
        with st.expander("Stablecoin Charts", expanded=False):
            _try_line_chart(df_computed, ["StablecoinSupplyRatio"], "Stablecoin Supply Ratio")


def _render_driver_summary(oc: OnchainAnalytics) -> None:
    _section_header("Driver Summary", "On-Chain Signal Breakdown")

    col_pos, col_neg, col_neu = st.columns(3)

    with col_pos:
        st.markdown(
            "<div style='font-family:var(--font-mono);font-size:0.62rem;"
            "letter-spacing:0.12em;text-transform:uppercase;"
            "color:var(--positive);margin-bottom:6px'>Pozitif Driver</div>",
            unsafe_allow_html=True,
        )
        if oc.positive_drivers:
            st.markdown(
                f"<div style='padding:10px 12px;border-radius:var(--r-sm);"
                f"border:1px solid rgba(50,217,140,0.15);background:rgba(50,217,140,0.04)'>"
                f"{_driver_list(oc.positive_drivers, 'positive')}</div>",
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                "<div style='font-size:0.76rem;color:var(--text-muted)'>Aktif pozitif driver yok.</div>",
                unsafe_allow_html=True,
            )

    with col_neg:
        st.markdown(
            "<div style='font-family:var(--font-mono);font-size:0.62rem;"
            "letter-spacing:0.12em;text-transform:uppercase;"
            "color:var(--negative);margin-bottom:6px'>Negatif Driver</div>",
            unsafe_allow_html=True,
        )
        if oc.negative_drivers:
            st.markdown(
                f"<div style='padding:10px 12px;border-radius:var(--r-sm);"
                f"border:1px solid rgba(255,95,114,0.15);background:rgba(255,95,114,0.04)'>"
                f"{_driver_list(oc.negative_drivers, 'negative')}</div>",
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                "<div style='font-size:0.76rem;color:var(--text-muted)'>Aktif negatif driver yok.</div>",
                unsafe_allow_html=True,
            )

    with col_neu:
        st.markdown(
            "<div style='font-family:var(--font-mono);font-size:0.62rem;"
            "letter-spacing:0.12em;text-transform:uppercase;"
            "color:var(--warning);margin-bottom:6px'>Nötr / Mixed</div>",
            unsafe_allow_html=True,
        )
        if oc.neutral_drivers:
            st.markdown(
                f"<div style='padding:10px 12px;border-radius:var(--r-sm);"
                f"border:1px solid rgba(240,192,80,0.15);background:rgba(240,192,80,0.04)'>"
                f"{_driver_list(oc.neutral_drivers, 'neutral')}</div>",
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                "<div style='font-size:0.76rem;color:var(--text-muted)'>Nötr driver yok.</div>",
                unsafe_allow_html=True,
            )

    # Warnings
    all_warnings = oc.warnings
    if all_warnings:
        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
        warn_rows = _driver_list(all_warnings, "warning")
        st.markdown(
            f"<div style='padding:10px 12px;border-radius:var(--r-sm);"
            f"border:1px solid rgba(100,140,185,0.18);background:rgba(255,255,255,0.02)'>"
            f"<div style='font-family:var(--font-mono);font-size:0.6rem;"
            f"letter-spacing:0.12em;text-transform:uppercase;"
            f"color:var(--text-muted);margin-bottom:6px'>Uyarılar / Eksik Veri</div>"
            f"{warn_rows}</div>",
            unsafe_allow_html=True,
        )


# ─── Data preparation with caching ───────────────────────────────────────────

@st.cache_data(ttl=3600, show_spinner=False)
def _load_and_compute(force_refresh: bool = False):
    """
    Load all Coin Metrics data and run analytics.
    Cached for 1 hour to avoid repeated GitHub requests.
    Returns (oc, btc_result, usdt_result, usdc_result, df_computed_json_safe).
    """
    results = load_all_onchain(force_refresh=force_refresh)
    btc_r   = results["btc"]
    usdt_r  = results["usdt"]
    usdc_r  = results["usdc"]

    # Build analytics
    usdt_df = usdt_r.df if not usdt_r.df.empty else None
    usdc_df = usdc_r.df if not usdc_r.df.empty else None

    from domain.onchain_analytics import build_onchain_analytics, _compute_metrics
    import numpy as np

    oc = build_onchain_analytics(btc_r.df, usdt_df, usdc_df)

    # Build computed df for charts (do it here so it's cached)
    df_computed = None
    if not btc_r.df.empty:
        try:
            warnings_tmp: list[str] = []
            derived_tmp: list[str] = []
            df_sorted = btc_r.df.copy()
            if "time" in df_sorted.columns:
                df_sorted["time"] = pd.to_datetime(df_sorted["time"], errors="coerce")
                df_sorted = df_sorted.sort_values("time").reset_index(drop=True)
            df_computed = _compute_metrics(df_sorted, usdt_df, usdc_df, warnings_tmp, derived_tmp)
        except Exception:  # noqa: BLE001
            df_computed = btc_r.df.copy()

    return oc, btc_r, usdt_r, usdc_r, df_computed


# ─── Main render function ─────────────────────────────────────────────────────

def render_onchain_tab() -> None:
    """
    Main entry point called from app.py.
    Renders the full ON-CHAIN DASHBOARD tab.
    """
    st.markdown(
        '<div class="s-kicker">On-Chain Intelligence</div>'
        '<div class="s-title">ON-CHAIN DASHBOARD</div>'
        '<div class="s-subtitle">'
        'Coin Metrics günlük CSV verilerinden türetilmiş BTC on-chain / valuation / '
        'exchange / miner / network metrikleri. Veriler günlük frekansta güncellenir.'
        '</div>',
        unsafe_allow_html=True,
    )
    st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)

    # ── Refresh control ───────────────────────────────────────────────────
    ctrl_col, _ = st.columns([0.3, 0.7])
    with ctrl_col:
        force_refresh = st.button(
            "🔄 Veriyi Yenile",
            help="Coin Metrics GitHub'dan son CSV'leri indir (cache'i atla)",
            use_container_width=True,
        )

    # ── Load data (cached unless force_refresh) ───────────────────────────
    with st.spinner("On-chain veriler hazırlanıyor…"):
        try:
            oc, btc_r, usdt_r, usdc_r, df_computed = _load_and_compute(
                force_refresh=bool(force_refresh)
            )
        except Exception as exc:  # noqa: BLE001
            st.error(f"On-chain veri yüklenirken hata: {exc}")
            return

    # ── Source status bar ─────────────────────────────────────────────────
    btc_status = btc_r.source_status
    status_html = (
        f"<div style='display:flex;align-items:center;gap:10px;flex-wrap:wrap;"
        f"padding:8px 12px;border-radius:var(--r-sm);border:1px solid var(--border);"
        f"background:rgba(255,255,255,0.02);margin-bottom:12px'>"
        f"<span style='font-family:var(--font-mono);font-size:0.62rem;"
        f"color:var(--text-muted);letter-spacing:0.1em'>DATA SOURCE</span>"
        f"<span style='font-family:var(--font-mono);font-size:0.68rem;color:var(--text-muted)'>BTC</span>"
        f"{_status_badge(btc_r.source_status)}"
        f"<span style='font-family:var(--font-mono);font-size:0.68rem;color:var(--text-muted)'>USDT</span>"
        f"{_status_badge(usdt_r.source_status)}"
        f"<span style='font-family:var(--font-mono);font-size:0.68rem;color:var(--text-muted)'>USDC</span>"
        f"{_status_badge(usdc_r.source_status)}"
        f"<span style='font-family:var(--font-mono);font-size:0.62rem;color:var(--text-muted);margin-left:8px'>"
        f"Son güncelleme: {btc_r.fetched_at or 'N/A'}"
        f"</span>"
        f"</div>"
    )
    st.markdown(status_html, unsafe_allow_html=True)

    # Missing column warnings (compact)
    all_missing = btc_r.missing_columns + usdt_r.missing_columns + usdc_r.missing_columns
    if all_missing:
        st.warning(f"Bazı kolonlar eksik: {', '.join(all_missing)}")

    # ── UNAVAILABLE guard ─────────────────────────────────────────────────
    if oc.regime == "UNAVAILABLE":
        st.error(
            "On-chain veri şu an mevcut değil. GitHub erişimi başarısız "
            "ve lokal cache de bulunamadı. Tekrar denemek için 'Veriyi Yenile' butonunu kullan."
        )
        if oc.warnings:
            with st.expander("Teknik Detaylar", expanded=False):
                for w in oc.warnings:
                    st.caption(f"⚠ {w}")
        return

    # ── Panels ────────────────────────────────────────────────────────────
    _render_overview_panel(oc, btc_status, btc_r.latest_date)

    st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)
    _render_valuation_panel(oc, df_computed)

    st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)
    _render_exchange_panel(oc, df_computed)

    st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)
    _render_miner_network_panel(oc, df_computed)

    st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)
    _render_stablecoin_panel(oc, usdt_r, usdc_r, df_computed)

    st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)
    _render_driver_summary(oc)

    # ── Footer disclaimer ─────────────────────────────────────────────────
    st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)
    st.markdown(
        "<div style='font-size:0.7rem;color:var(--text-faint);line-height:1.6;"
        "padding:10px 14px;border-radius:6px;border:1px solid var(--border-soft);"
        "background:rgba(255,255,255,0.01)'>"
        "Kaynak: Coin Metrics Community Data (coinmetrics.io). "
        "Estimated NUPL, Estimated Realized Cap, Estimated Realized Price ve "
        "Estimated MVRV Z-Score türetilmiş yaklaşık metriklerdir; "
        "resmi Glassnode veya CryptoQuant serilerinin birebir karşılığı değildir. "
        "Bu sayfa finansal tavsiye içermez; yalnızca veri rejimi yorumlar."
        "</div>",
        unsafe_allow_html=True,
    )
