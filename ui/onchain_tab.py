"""
SA Finance Alpha Terminal — ON-CHAIN DASHBOARD Tab
Renders the On-Chain sekme using Coin Metrics data + onchain_analytics.
Follows the existing terminal design language (theme.py CSS variables).
"""
from __future__ import annotations

import math
from typing import Optional

import pandas as pd
import plotly.graph_objects as go
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
from services.onchain_manual import (
    METRIC_HELP,
    METRIC_KEYS,
    METRIC_LABELS,
    delete_entry,
    entry_count,
    get_metric_safe,
    has_today_entry,
    load_all_entries,
    load_entry,
    load_latest_entry,
    save_entry,
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

_CHART_START = pd.Timestamp("2025-01-01")

# Terminal palette (mirrors theme.py CSS vars)
_C_ACCENT   = "#52c8ff"
_C_POSITIVE = "#32d98c"
_C_NEGATIVE = "#ff5f72"
_C_WARNING  = "#f0c050"
_C_MUTED    = "#8aa0b8"
_C_BG       = "#081422"
_C_SURFACE  = "#0c1b2e"
_C_BORDER   = "rgba(100,140,185,0.18)"
_C_TEXT_PRI = "#eef3fa"
_C_TEXT_SEC = "#bfcedd"
_FONT_MONO  = "IBM Plex Mono, Courier New, monospace"

# Default line colour palette (cycles for multi-series charts)
_LINE_COLORS = [_C_ACCENT, _C_POSITIVE, _C_NEGATIVE, _C_WARNING, _C_MUTED]

# Pretty display name map (internal col → legend label)
_COL_LABELS: dict[str, str] = {
    "PriceUSD":                 "BTC Price",
    "RealizedPrice_Est":        "Est. Realized Price",
    "CapMVRVCur":               "MVRV",
    "NUPL_Est":                 "Est. NUPL",
    "MVRV_Z_Est":               "Est. MVRV Z-Score",
    "MayerMultiple":            "Mayer Multiple",
    "PuellMultiple":            "Puell Multiple",
    "FlowInExNtv":              "Inflow",
    "FlowOutExNtv":             "Outflow",
    "ExchangeNetFlow":          "Net Flow",
    "SplyExNtv":                "Exchange Supply",
    "ExchangeReserveRatio":     "Reserve Ratio",
    "ExchangeInflowStress":     "Inflow Stress",
    "ExchangeOutflowStress":    "Outflow Stress",
    "AdrActCnt":                "Active Addresses",
    "TxCnt":                    "Tx Count",
    "TxTfrCnt":                 "Tx Transfer Count",
    "NetworkActivityComposite": "Network Activity",
    "FeePressureRatio":         "Fee Pressure",
    "MinerRevenue_Est":         "Miner Revenue Est.",
    "HashRate":                 "Hash Rate",
    "HashrateTrendProxy":       "Hashrate Trend Proxy",
    "StablecoinSupplyRatio":    "SSR",
}

# Columns that benefit from a secondary y-axis (second colour group)
_SECONDARY_COLS: set[str] = {"NUPL_Est", "ExchangeOutflowStress", "TxTfrCnt"}


def _plotly_layout(title: str, height: int) -> dict:
    """Base Plotly layout dict matching terminal dark theme."""
    return dict(
        height=height,
        margin=dict(l=10, r=10, t=36, b=28),
        paper_bgcolor=_C_BG,
        plot_bgcolor=_C_SURFACE,
        font=dict(family=_FONT_MONO, size=10, color=_C_TEXT_SEC),
        title=dict(
            text=title.upper(),
            font=dict(family=_FONT_MONO, size=10, color=_C_MUTED),
            x=0.01, y=0.98, xanchor="left", yanchor="top",
        ),
        legend=dict(
            orientation="h",
            x=0, y=-0.12,
            font=dict(family=_FONT_MONO, size=9, color=_C_TEXT_SEC),
            bgcolor="rgba(0,0,0,0)",
            bordercolor="rgba(0,0,0,0)",
        ),
        xaxis=dict(
            showgrid=True,
            gridcolor="rgba(100,140,185,0.08)",
            gridwidth=1,
            zeroline=False,
            tickfont=dict(family=_FONT_MONO, size=9, color=_C_MUTED),
            tickformat="%b %Y",
            linecolor="rgba(100,140,185,0.18)",
            showline=True,
        ),
        yaxis=dict(
            showgrid=True,
            gridcolor="rgba(100,140,185,0.08)",
            gridwidth=1,
            zeroline=False,
            tickfont=dict(family=_FONT_MONO, size=9, color=_C_MUTED),
            linecolor="rgba(100,140,185,0.18)",
            showline=False,
            side="left",
        ),
        yaxis2=dict(
            overlaying="y",
            side="right",
            showgrid=False,
            zeroline=False,
            tickfont=dict(family=_FONT_MONO, size=9, color=_C_MUTED),
            showline=False,
        ),
        hovermode="x",
        hoverlabel=dict(
            bgcolor="rgb(255,255,255)",
            bordercolor="rgb(82,200,255)",
            namelength=-1,
            align="left",
            font=dict(
                family="IBM Plex Mono, Courier New, monospace",
                size=11,
                color="rgb(238,243,250)",
            ),
        ),
    )


def _prep_chart_df(
    df: pd.DataFrame,
    cols: list[str],
) -> tuple[pd.DataFrame, list[str]]:
    """Filter to 2025+, drop all-NaN cols, sort. Returns (df, available_cols)."""
    available = [c for c in cols if c in df.columns]
    if not available:
        return pd.DataFrame(), []
    chart_df = df[["time"] + available].copy()
    chart_df["time"] = pd.to_datetime(chart_df["time"], errors="coerce")
    chart_df = chart_df[chart_df["time"] >= _CHART_START]
    chart_df = chart_df.dropna(subset=["time"]).sort_values("time")
    chart_df = chart_df.replace([float("inf"), float("-inf")], None)
    chart_df = chart_df.dropna(axis=1, how="all")
    available = [c for c in available if c in chart_df.columns]
    return chart_df, available


def _oc_chart(
    df: pd.DataFrame,
    cols: list[str],
    title: str,
    height: int = 280,
    use_secondary: bool = False,
    fill_first: bool = False,
    zero_line: bool = False,
) -> None:
    """
    Render a styled Plotly line chart in the terminal dark theme.

    Args:
        df:           Computed DataFrame with time column.
        cols:         Column names to plot.
        title:        Chart title (uppercased automatically).
        height:       Pixel height.
        use_secondary: If True, second series uses right y-axis.
        fill_first:   Fill area under the first series.
        zero_line:    Draw a y=0 reference line.
    """
    chart_df, available = _prep_chart_df(df, cols)
    if chart_df.empty or not available:
        st.markdown(
            f"<div style='font-family:{_FONT_MONO};font-size:0.6rem;"
            f"color:{_C_MUTED};padding:6px 0;text-transform:uppercase'>"
            f"{esc(title)} — veri yetersiz</div>",
            unsafe_allow_html=True,
        )
        return

    fig = go.Figure()
    layout = _plotly_layout(title, height)

    for i, col in enumerate(available):
        color = _LINE_COLORS[i % len(_LINE_COLORS)]
        label = _COL_LABELS.get(col, col)
        is_secondary = use_secondary and i > 0
        yaxis = "y2" if is_secondary else "y1"

        trace_kwargs: dict = dict(
            x=chart_df["time"],
            y=chart_df[col],
            name=label,
            mode="lines",
            line=dict(color=color, width=1.5),
            yaxis=yaxis,
            hovertemplate=f"<b>{label}</b>: %{{y:.4f}}<extra></extra>",
            hoverlabel=dict(
                bgcolor="rgb(255,255,255)",
                bordercolor=color,
                font=dict(
                    family="IBM Plex Mono, Courier New, monospace",
                    size=11,
                    color="rgb(238,243,250)",
                ),
            ),
        )
        if fill_first and i == 0:
            trace_kwargs["fill"] = "tozeroy"
            trace_kwargs["fillcolor"] = color.replace("#", "rgba(").rstrip(")")                 if color.startswith("rgba") else f"rgba({int(color[1:3],16)},{int(color[3:5],16)},{int(color[5:7],16)},0.06)"

        fig.add_trace(go.Scatter(**trace_kwargs))

    if zero_line:
        fig.add_hline(
            y=0,
            line=dict(color=_C_MUTED, width=1, dash="dot"),
            opacity=0.4,
        )

    # Remove secondary y-axis from layout if unused
    if not use_secondary or len(available) < 2:
        layout.pop("yaxis2", None)

    fig.update_layout(**layout)
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


def _oc_dual_axis_chart(
    df: pd.DataFrame,
    col_primary: str,
    col_secondary: str,
    title: str,
    height: int = 280,
) -> None:
    """Two-series chart with independent y-axes (e.g. Price + Realized Price)."""
    chart_df, available = _prep_chart_df(df, [col_primary, col_secondary])
    if chart_df.empty or col_primary not in available:
        st.markdown(
            f"<div style='font-family:{_FONT_MONO};font-size:0.6rem;"
            f"color:{_C_MUTED};padding:6px 0;text-transform:uppercase'>"
            f"{esc(title)} — veri yetersiz</div>",
            unsafe_allow_html=True,
        )
        return

    fig = go.Figure()
    layout = _plotly_layout(title, height)

    # Primary
    fig.add_trace(go.Scatter(
        x=chart_df["time"], y=chart_df[col_primary],
        name=_COL_LABELS.get(col_primary, col_primary),
        mode="lines",
        line=dict(color=_C_ACCENT, width=1.8),
        yaxis="y1",
        hovertemplate=f"<b>{_COL_LABELS.get(col_primary, col_primary)}</b>: $%{{y:,.0f}}<extra></extra>",
        hoverlabel=dict(
            bgcolor="rgb(255,255,255)",
            bordercolor=_C_ACCENT,
            font=dict(family="IBM Plex Mono, Courier New, monospace", size=11, color="rgb(238,243,250)"),
        ),
    ))

    # Secondary (right axis)
    if col_secondary in available:
        fig.add_trace(go.Scatter(
            x=chart_df["time"], y=chart_df[col_secondary],
            name=_COL_LABELS.get(col_secondary, col_secondary),
            mode="lines",
            line=dict(color=_C_POSITIVE, width=1.4, dash="dot"),
            yaxis="y2",
            hovertemplate=f"<b>{_COL_LABELS.get(col_secondary, col_secondary)}</b>: $%{{y:,.0f}}<extra></extra>",
            hoverlabel=dict(
                bgcolor="rgb(255,255,255)",
                bordercolor=_C_POSITIVE,
                font=dict(family="IBM Plex Mono, Courier New, monospace", size=11, color="rgb(238,243,250)"),
            ),
        ))
        layout["yaxis2"] = dict(
            overlaying="y", side="right", showgrid=False,
            zeroline=False, tickfont=dict(family=_FONT_MONO, size=9, color=_C_POSITIVE),
        )

    fig.update_layout(**layout)
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


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

    # charts rendered in the unified section below


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

    # charts rendered in the unified section below


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

    # charts rendered in the unified section below


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

    # charts rendered in the unified section below




def _render_charts_section(df_computed: Optional[pd.DataFrame]) -> None:
    """
    Unified CHARTS section — all on-chain charts in one expander,
    organised in 2-column grid rows, styled with Plotly terminal theme.
    Data range: 2025-01-01 → latest.
    """
    if df_computed is None or df_computed.empty:
        return

    st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)
    _section_header("Historical Charts", "CHARTS · 2025-01-01 → Güncel")

    with st.expander("Chartları Göster / Gizle", expanded=True):

        # ── Row 1: Valuation ──────────────────────────────────────────────
        st.markdown(
            "<div style='font-family:var(--font-mono);font-size:0.62rem;"
            "letter-spacing:0.16em;text-transform:uppercase;"
            "color:var(--accent);padding:10px 0 4px'>Valuation</div>",
            unsafe_allow_html=True,
        )
        r1c1, r1c2 = st.columns(2)
        with r1c1:
            _oc_dual_axis_chart(
                df_computed, "PriceUSD", "RealizedPrice_Est",
                "PriceUSD + Estimated Realized Price", height=260,
            )
        with r1c2:
            _oc_chart(
                df_computed, ["MVRV_Z_Est"],
                "Estimated MVRV Z-Score", height=260,
            )

        r2c1, r2c2 = st.columns(2)
        with r2c1:
            _oc_chart(
                df_computed, ["CapMVRVCur", "NUPL_Est"],
                "MVRV + Estimated NUPL", height=260,
                use_secondary=True,
            )
        with r2c2:
            _oc_chart(
                df_computed, ["PuellMultiple"],
                "Puell Multiple", height=260,
            )

        r3c1, r3c2 = st.columns(2)
        with r3c1:
            _oc_chart(
                df_computed, ["MayerMultiple"],
                "Mayer Multiple", height=260,
            )
        with r3c2:
            _oc_chart(
                df_computed, ["NUPL_Est"],
                "Estimated NUPL", height=260,
            )

        # ── Row 4: Exchange Flow ──────────────────────────────────────────
        st.markdown(
            "<div style='font-family:var(--font-mono);font-size:0.62rem;"
            "letter-spacing:0.16em;text-transform:uppercase;"
            "color:var(--accent);padding:14px 0 4px'>Exchange Flow</div>",
            unsafe_allow_html=True,
        )
        r4c1, r4c2 = st.columns(2)
        with r4c1:
            _oc_chart(
                df_computed, ["FlowInExNtv", "FlowOutExNtv"],
                "Inflow / Outflow", height=260,
            )
        with r4c2:
            _oc_chart(
                df_computed, ["ExchangeNetFlow"],
                "Exchange Net Flow", height=260,
                zero_line=True,
            )

        r5c1, r5c2 = st.columns(2)
        with r5c1:
            _oc_chart(
                df_computed, ["SplyExNtv"],
                "Exchange Supply (SplyExNtv)", height=260,
            )
        with r5c2:
            _oc_chart(
                df_computed, ["ExchangeReserveRatio"],
                "Exchange Reserve Ratio", height=260,
            )

        r6c1, r6c2 = st.columns(2)
        with r6c1:
            _oc_chart(
                df_computed, ["ExchangeInflowStress", "ExchangeOutflowStress"],
                "Exchange Stress", height=260,
                use_secondary=False,
            )

        # ── Row 7: Miner & Network ────────────────────────────────────────
        st.markdown(
            "<div style='font-family:var(--font-mono);font-size:0.62rem;"
            "letter-spacing:0.16em;text-transform:uppercase;"
            "color:var(--accent);padding:14px 0 4px'>Miner & Network</div>",
            unsafe_allow_html=True,
        )
        r7c1, r7c2 = st.columns(2)
        with r7c1:
            _oc_chart(
                df_computed, ["MinerRevenue_Est"],
                "Miner Revenue Estimate", height=260,
            )
        with r7c2:
            _oc_chart(
                df_computed, ["HashrateTrendProxy"],
                "Hashrate Trend Proxy", height=260,
            )

        r8c1, r8c2 = st.columns(2)
        with r8c1:
            _oc_chart(
                df_computed, ["NetworkActivityComposite"],
                "Network Activity Composite", height=260,
                zero_line=True,
            )
        with r8c2:
            _oc_chart(
                df_computed, ["AdrActCnt"],
                "Active Addresses", height=260,
            )

        r9c1, r9c2 = st.columns(2)
        with r9c1:
            _oc_chart(
                df_computed, ["TxCnt", "TxTfrCnt"],
                "TxCnt / TxTfrCnt", height=260,
                use_secondary=True,
            )
        with r9c2:
            _oc_chart(
                df_computed, ["HashRate"],
                "Hash Rate", height=260,
            )

        # ── Row 10: Stablecoin ────────────────────────────────────────────
        st.markdown(
            "<div style='font-family:var(--font-mono);font-size:0.62rem;"
            "letter-spacing:0.16em;text-transform:uppercase;"
            "color:var(--accent);padding:14px 0 4px'>Stablecoin Liquidity</div>",
            unsafe_allow_html=True,
        )
        r10c1, _ = st.columns(2)
        with r10c1:
            _oc_chart(
                df_computed, ["StablecoinSupplyRatio"],
                "Stablecoin Supply Ratio", height=260,
            )

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
            # Normalize stable DFs time columns to same dtype before passing to _compute_metrics
            def _ensure_datetime(sdf):
                if sdf is None or sdf.empty:
                    return sdf
                s = sdf.copy()
                if "time" in s.columns:
                    s["time"] = pd.to_datetime(s["time"], errors="coerce")
                return s
            usdt_df_norm = _ensure_datetime(usdt_df)
            usdc_df_norm = _ensure_datetime(usdc_df)
            df_computed = _compute_metrics(df_sorted, usdt_df_norm, usdc_df_norm, warnings_tmp, derived_tmp)
        except Exception as _exc:  # noqa: BLE001
            import traceback
            traceback.print_exc()
            df_computed = btc_r.df.copy()

    return oc, btc_r, usdt_r, usdc_r, df_computed


# ─── Manuel mod: Sidebar form ────────────────────────────────────────────────

def _render_manual_sidebar_form() -> None:
    """
    Sidebar'da günlük on-chain metrik giriş formu.
    Yalnızca Manuel Mod aktifken çağrılır.
    """
    from datetime import date as _date

    st.sidebar.markdown("---")
    st.sidebar.markdown(
        "<div style='font-family:var(--font-mono);font-size:0.65rem;"
        "letter-spacing:0.14em;text-transform:uppercase;"
        "color:var(--accent);margin-bottom:6px'>📊 On-Chain Veri Girişi</div>",
        unsafe_allow_html=True,
    )

    # Tarih seçici
    entry_date = st.sidebar.date_input(
        "Tarih",
        value=_date.today(),
        help="Hangi güne ait veri giriyorsunuz?",
    ).isoformat()  # type: ignore[union-attr]

    # Mevcut kaydı yükle (ön-doldurmak için)
    existing = load_entry(entry_date) or {}

    st.sidebar.markdown(
        "<div style='font-size:0.62rem;color:var(--text-muted);margin:4px 0 8px'>CryptoQuant / Glassnode'dan alınan değerleri girin.</div>",
        unsafe_allow_html=True,
    )

    # ── Grup 1: Valuation ─────────────────────────────────────────────────
    st.sidebar.markdown("**Valuation**")
    nupl       = st.sidebar.number_input(METRIC_LABELS["nupl"],            value=float(existing.get("nupl") or 0.0),          step=0.001,  format="%.4f",  help=METRIC_HELP["nupl"],            key="moc_nupl")
    sopr       = st.sidebar.number_input(METRIC_LABELS["sopr"],            value=float(existing.get("sopr") or 1.0),          step=0.001,  format="%.4f",  help=METRIC_HELP["sopr"],            key="moc_sopr")
    mvrv       = st.sidebar.number_input(METRIC_LABELS["mvrv"],            value=float(existing.get("mvrv") or 1.0),          step=0.01,   format="%.4f",  help=METRIC_HELP["mvrv"],            key="moc_mvrv")
    mvrv_z     = st.sidebar.number_input(METRIC_LABELS["mvrv_z_score"],    value=float(existing.get("mvrv_z_score") or 0.0),  step=0.1,    format="%.4f",  help=METRIC_HELP["mvrv_z_score"],    key="moc_mvrv_z")
    lth_cb     = st.sidebar.number_input(METRIC_LABELS["lth_cost_basis"],  value=float(existing.get("lth_cost_basis") or 0.0),  step=100.0, format="%.0f", help=METRIC_HELP["lth_cost_basis"],  key="moc_lth_cb")
    sth_cb     = st.sidebar.number_input(METRIC_LABELS["sth_cost_basis"],  value=float(existing.get("sth_cost_basis") or 0.0),  step=100.0, format="%.0f", help=METRIC_HELP["sth_cost_basis"],  key="moc_sth_cb")
    realized_p = st.sidebar.number_input(METRIC_LABELS["realized_price"],  value=float(existing.get("realized_price") or 0.0),  step=100.0, format="%.0f", help=METRIC_HELP["realized_price"],  key="moc_realized_p")
    sth_rpl    = st.sidebar.number_input(METRIC_LABELS["sth_rpl"],         value=float(existing.get("sth_rpl") or 0.0),       step=0.1,    format="%.2f",  help=METRIC_HELP["sth_rpl"],         key="moc_sth_rpl")

    # ── Grup 2: Exchange & Derivatives ───────────────────────────────────
    st.sidebar.markdown("**Exchange & Derivatives**")
    ex_netflow   = st.sidebar.number_input(METRIC_LABELS["exchange_netflow"],    value=float(existing.get("exchange_netflow") or 0.0),    step=100.0,  format="%.0f",  help=METRIC_HELP["exchange_netflow"],    key="moc_ex_netflow")
    ex_reserve   = st.sidebar.number_input(METRIC_LABELS["exchange_reserve"],    value=float(existing.get("exchange_reserve") or 0.0),    step=1000.0, format="%.0f",  help=METRIC_HELP["exchange_reserve"],    key="moc_ex_reserve")
    funding      = st.sidebar.number_input(METRIC_LABELS["funding_rate"],        value=float(existing.get("funding_rate") or 0.0),        step=0.001,  format="%.4f",  help=METRIC_HELP["funding_rate"],        key="moc_funding")
    oi           = st.sidebar.number_input(METRIC_LABELS["open_interest"],       value=float(existing.get("open_interest") or 0.0),       step=0.1,    format="%.2f",  help=METRIC_HELP["open_interest"],       key="moc_oi")
    long_liq     = st.sidebar.number_input(METRIC_LABELS["long_liquidations"],   value=float(existing.get("long_liquidations") or 0.0),   step=1.0,    format="%.1f",  help=METRIC_HELP["long_liquidations"],   key="moc_long_liq")
    short_liq    = st.sidebar.number_input(METRIC_LABELS["short_liquidations"],  value=float(existing.get("short_liquidations") or 0.0),  step=1.0,    format="%.1f",  help=METRIC_HELP["short_liquidations"],  key="moc_short_liq")
    cb_prem      = st.sidebar.number_input(METRIC_LABELS["coinbase_premium"],    value=float(existing.get("coinbase_premium") or 0.0),    step=0.01,   format="%.4f",  help=METRIC_HELP["coinbase_premium"],    key="moc_cb_prem")
    etf_flow     = st.sidebar.number_input(METRIC_LABELS["etf_flow_cumulative"], value=float(existing.get("etf_flow_cumulative") or 0.0), step=0.1,    format="%.2f",  help=METRIC_HELP["etf_flow_cumulative"], key="moc_etf_flow")

    # ── Not ───────────────────────────────────────────────────────────────
    notes = st.sidebar.text_area("Not (opsiyonel)", value=existing.get("notes") or "", height=60, key="moc_notes")

    # ── Kaydet butonu ─────────────────────────────────────────────────────
    col_save, col_clear = st.sidebar.columns(2)
    with col_save:
        if st.button("💾 Kaydet", use_container_width=True, key="moc_save_btn"):
            entry = {
                "nupl":                nupl,
                "sopr":                sopr,
                "mvrv":                mvrv,
                "mvrv_z_score":        mvrv_z,
                "lth_cost_basis":      lth_cb     if lth_cb     != 0.0 else None,
                "sth_cost_basis":      sth_cb     if sth_cb     != 0.0 else None,
                "realized_price":      realized_p if realized_p != 0.0 else None,
                "sth_rpl":             sth_rpl,
                "exchange_netflow":    ex_netflow,
                "exchange_reserve":    ex_reserve if ex_reserve != 0.0 else None,
                "funding_rate":        funding,
                "open_interest":       oi         if oi         != 0.0 else None,
                "long_liquidations":   long_liq   if long_liq   != 0.0 else None,
                "short_liquidations":  short_liq  if short_liq  != 0.0 else None,
                "coinbase_premium":    cb_prem,
                "etf_flow_cumulative": etf_flow   if etf_flow   != 0.0 else None,
                "notes":               notes.strip() or None,
            }
            save_entry(entry, entry_date)
            st.sidebar.success(f"✓ {entry_date} kaydedildi")
            st.rerun()
    with col_clear:
        if st.button("🗑 Sil", use_container_width=True, key="moc_del_btn"):
            if delete_entry(entry_date):
                st.sidebar.warning(f"{entry_date} silindi")
                st.rerun()


# ─── Manuel mod: Dashboard render ────────────────────────────────────────────

def _signal_color(value: Optional[float], bull_above: Optional[float] = None,
                   bear_above: Optional[float] = None, bull_below: Optional[float] = None,
                   bear_below: Optional[float] = None) -> str:
    """Basit renk mantığı: bull → positive, bear → negative, nötr → text-primary."""
    if value is None:
        return "var(--text-muted)"
    if bull_below is not None and value < bull_below:
        return "var(--positive)"
    if bear_above is not None and value > bear_above:
        return "var(--negative)"
    if bull_above is not None and value > bull_above:
        return "var(--positive)"
    if bear_below is not None and value < bear_below:
        return "var(--negative)"
    return "var(--text-primary)"


def _render_manual_dashboard(entry: dict) -> None:
    """Manuel girdi dict'inden on-chain dashboard paneli oluştur."""

    def _gm(key: str) -> Optional[float]:
        return get_metric_safe(entry, key)

    saved_at = entry.get("_saved_at", "?")
    entry_date_display = entry.get("_date", saved_at)

    # ── Başlık bandı ──────────────────────────────────────────────────────
    st.markdown(
        f"<div style='display:flex;align-items:center;gap:12px;flex-wrap:wrap;"
        f"padding:8px 14px;border-radius:var(--r-sm);border:1px solid var(--border);"
        f"background:rgba(82,200,255,0.05);margin-bottom:12px'>"
        f"<span style='font-family:var(--font-mono);font-size:0.62rem;"
        f"color:var(--accent);letter-spacing:0.1em'>MANUEL MOD</span>"
        f"<span style='font-family:var(--font-mono);font-size:0.68rem;"
        f"color:var(--text-muted)'>Kayıt: {esc(saved_at)} UTC</span>"
        f"<span style='font-family:var(--font-mono);font-size:0.62rem;"
        f"color:var(--text-muted)'>Toplam kayıt: {entry_count()}</span>"
        f"</div>",
        unsafe_allow_html=True,
    )

    # ── Valuation paneli ──────────────────────────────────────────────────
    _section_header("Valuation Layer", "Valuation · Manuel Giriş")

    nupl       = _gm("nupl")
    sopr       = _gm("sopr")
    mvrv       = _gm("mvrv")
    mvrv_z     = _gm("mvrv_z_score")
    lth_cb     = _gm("lth_cost_basis")
    sth_cb     = _gm("sth_cost_basis")
    realized_p = _gm("realized_price")
    sth_rpl    = _gm("sth_rpl")

    def _nupl_zone(v: Optional[float]) -> str:
        if v is None: return ""
        if v < 0:     return "Loss Zone"
        if v < 0.25:  return "Hope"
        if v < 0.50:  return "Belief"
        if v < 0.75:  return "Euphoria"
        return "Greed / Top"

    def _mvrv_zone(v: Optional[float]) -> str:
        if v is None: return ""
        if v < 1.0:   return "Ucuz / Akümülasyon"
        if v < 2.4:   return "Normal"
        if v < 3.7:   return "Dikkat"
        return "Aşırı Isınma"

    def _mvrv_z_zone(v: Optional[float]) -> str:
        if v is None: return ""
        if v < 0:     return "Dip Bölgesi"
        if v < 3:     return "Nötr"
        if v < 7:     return "Dikkat"
        return "Aşırı Isınma"

    def _sth_rpl_label(v: Optional[float]) -> str:
        if v is None: return ""
        return "Kârda ✓" if v >= 0 else "Zararda"

    val_items = [
        ("NUPL",            _fmt_num(nupl, 4)       if nupl      is not None else "N/A",
         _nupl_zone(nupl),
         _signal_color(nupl, bear_above=0.5, bull_below=0.25)),
        ("SOPR",            _fmt_num(sopr, 4)       if sopr      is not None else "N/A",
         "Spent Output P/R",
         _signal_color(sopr, bull_above=1.001, bear_below=0.98)),
        ("MVRV Ratio",      _fmt_num(mvrv, 4)       if mvrv      is not None else "N/A",
         _mvrv_zone(mvrv),
         _signal_color(mvrv, bear_above=3.7, bull_below=1.0)),
        ("MVRV Z-Score",    _fmt_num(mvrv_z, 4)     if mvrv_z    is not None else "N/A",
         _mvrv_z_zone(mvrv_z),
         _signal_color(mvrv_z, bear_above=7.0, bull_below=0.0)),
        ("LTH Cost Basis",  _fmt_usd(lth_cb, 0)     if lth_cb    else "N/A",
         "BTC Cost Basis LTH", ""),
        ("STH Cost Basis",  _fmt_usd(sth_cb, 0)     if sth_cb    else "N/A",
         "BTC Cost Basis STH", ""),
        ("Realized Price",  _fmt_usd(realized_p, 0) if realized_p else "N/A",
         "Tüm coin ortalama", ""),
        ("STH P&L",         f"{sth_rpl:+.2f}%"      if sth_rpl   is not None else "N/A",
         _sth_rpl_label(sth_rpl),
         _signal_color(sth_rpl, bull_above=0, bear_below=-5)),
    ]
    _render_metric_row(val_items, cols=4)

    st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)

    # ── Exchange & Derivatives paneli ────────────────────────────────────
    _section_header("Exchange & Derivatives Layer", "Exchange Flow · Türev Piyasa · Manuel Giriş")

    ex_netflow = _gm("exchange_netflow")
    ex_reserve = _gm("exchange_reserve")
    funding    = _gm("funding_rate")
    oi         = _gm("open_interest")
    long_liq   = _gm("long_liquidations")
    short_liq  = _gm("short_liquidations")
    cb_prem    = _gm("coinbase_premium")
    etf_flow   = _gm("etf_flow_cumulative")

    def _netflow_label(v: Optional[float]) -> str:
        if v is None: return ""
        return "Çıkış (bullish)" if v < 0 else "Giriş (satış baskısı)"

    def _funding_label(v: Optional[float]) -> str:
        if v is None: return ""
        if v > 0.05:  return "Aşırı Long / Overcrowding"
        if v > 0.01:  return "Long ağırlıklı"
        if v < -0.01: return "Short ağırlıklı"
        return "Nötr / Sağlıklı"

    def _liq_label(long: Optional[float], short: Optional[float]) -> str:
        if long is None or short is None: return ""
        ratio = long / short if short > 0 else 0
        if ratio > 3:   return "Long Flush ⚠"
        if ratio < 0.33: return "Short Squeeze"
        return "Dengeli"

    exd_items = [
        ("Exchange Netflow", f"{ex_netflow:+,.0f} BTC" if ex_netflow is not None else "N/A",
         _netflow_label(ex_netflow),
         _signal_color(ex_netflow, bear_above=0, bull_below=0)),
        ("Exchange Reserve", f"{ex_reserve:,.0f} BTC" if ex_reserve else "N/A",
         "Toplam borsa", ""),
        ("Funding Rate",     f"{funding:+.4f}%" if funding is not None else "N/A",
         _funding_label(funding),
         _signal_color(funding, bear_above=0.05, bull_below=-0.01)),
        ("Open Interest",    f"${oi:.2f}B" if oi else "N/A",
         "USD milyar", ""),
        ("Long Liquidations",  f"${long_liq:.1f}M" if long_liq else "N/A",
         "Long Flush riski",
         "var(--negative)" if long_liq and long_liq > 100 else "var(--text-primary)"),
        ("Short Liquidations", f"${short_liq:.1f}M" if short_liq else "N/A",
         "Short Squeeze sinyali",
         "var(--positive)" if short_liq and short_liq > 100 else "var(--text-primary)"),
    ]
    _render_metric_row(exd_items, cols=3)

    # Liquidation balance bar
    if long_liq and short_liq and (long_liq + short_liq) > 0:
        total_liq = long_liq + short_liq
        long_pct  = long_liq / total_liq * 100
        short_pct = short_liq / total_liq * 100
        liq_label = _liq_label(long_liq, short_liq)
        liq_color = "var(--negative)" if long_pct > 65 else ("var(--positive)" if short_pct > 65 else "var(--accent)")
        st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)
        st.markdown(
            f"<div style='padding:10px 14px;border-radius:var(--r-sm);"
            f"border:1px solid var(--border);background:rgba(255,255,255,0.02)'>"
            f"<div style='font-family:var(--font-mono);font-size:0.60rem;"
            f"letter-spacing:0.12em;text-transform:uppercase;"
            f"color:var(--text-muted);margin-bottom:6px'>LİKİDASYON DAĞILIMI (24s)</div>"
            f"<div style='display:flex;gap:0;border-radius:3px;overflow:hidden;height:14px'>"
            f"<div style='width:{long_pct:.1f}%;background:rgba(255,95,114,0.7);'></div>"
            f"<div style='width:{short_pct:.1f}%;background:rgba(50,217,140,0.7);'></div>"
            f"</div>"
            f"<div style='display:flex;justify-content:space-between;"
            f"font-family:var(--font-mono);font-size:0.68rem;margin-top:4px'>"
            f"<span style='color:var(--negative)'>Long {long_pct:.1f}% (${long_liq:.0f}M)</span>"
            f"<span style='color:{liq_color};font-weight:600'>{liq_label}</span>"
            f"<span style='color:var(--positive)'>Short {short_pct:.1f}% (${short_liq:.0f}M)</span>"
            f"</div></div>",
            unsafe_allow_html=True,
        )

    # Coinbase Premium + ETF Flow
    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
    inst_items = [
        ("Coinbase Premium", f"{cb_prem:+.4f}" if cb_prem is not None else "N/A",
         "Pozitif = ABD kurumsal alımı",
         _signal_color(cb_prem, bull_above=0.01, bear_below=-0.05)),
        ("Kümülatif ETF Flow", f"${etf_flow:.1f}B" if etf_flow else "N/A",
         "USD milyar", ""),
    ]
    _render_metric_row(inst_items, cols=4)

    st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)

    # ── BCRM-14 Skor Paneli ───────────────────────────────────────────────
    _section_header("SA Finance Alpha BTC Core-14", "BCRM Skor · Rejim · Katman Analizi")

    main_score, layer_scores, pos_d, neg_d = _compute_manual_score(entry)
    risk_flags = _compute_risk_flags(entry)

    # Rejim etiket
    if main_score <= 20:
        regime = "Capitulation / Deep Bearish"
        regime_color = "var(--negative)"
    elif main_score <= 40:
        regime = "Defensive Bearish"
        regime_color = "#ff8c42"
    elif main_score <= 60:
        regime = "Neutral / Mixed"
        regime_color = "var(--text-muted)"
    elif main_score <= 75:
        regime = "Constructive Bullish"
        regime_color = "var(--positive)"
    elif main_score <= 85:
        regime = "Strong Bullish"
        regime_color = "#00e5b4"
    else:
        regime = "Overheated / Distribution Risk"
        regime_color = "#f5c518"

    # Ana skor kartı
    st.markdown(
        f"<div style='display:flex;align-items:center;gap:20px;flex-wrap:wrap;"
        f"padding:14px 18px;border-radius:var(--r-sm);"
        f"border:1px solid {regime_color}33;"
        f"background:linear-gradient(135deg,{regime_color}08,transparent);margin-bottom:12px'>"
        f"<div>"
        f"<div style='font-family:var(--font-mono);font-size:0.58rem;letter-spacing:0.18em;"
        f"text-transform:uppercase;color:var(--text-muted);margin-bottom:3px'>BCRM SKORU</div>"
        f"<div style='font-family:var(--font-mono);font-size:2.2rem;font-weight:700;"
        f"color:{regime_color};line-height:1'>{main_score}<span style='font-size:1rem;"
        f"color:var(--text-muted)'>/100</span></div>"
        f"</div>"
        f"<div style='flex:1;min-width:180px'>"
        f"<div style='font-family:var(--font-mono);font-size:0.58rem;letter-spacing:0.14em;"
        f"text-transform:uppercase;color:var(--text-muted);margin-bottom:3px'>REJİM</div>"
        f"<div style='font-size:1.05rem;font-weight:600;color:{regime_color}'>{regime}</div>"
        f"</div>"
        f"<div>"
        f"<div style='font-family:var(--font-mono);font-size:0.58rem;letter-spacing:0.14em;"
        f"text-transform:uppercase;color:var(--text-muted);margin-bottom:3px'>GÜNCELLENDİ</div>"
        f"<div style='font-family:var(--font-mono);font-size:0.72rem;"
        f"color:var(--text-muted)'>{esc(entry.get('_saved_at','?'))[:16]} UTC</div>"
        f"</div>"
        f"</div>",
        unsafe_allow_html=True,
    )

    # Katman skorları
    layer_labels = {
        "valuation":     ("Değerleme / Döngü",   "25%"),
        "holder":        ("Holder Davranışı",     "20%"),
        "exchange":      ("Borsa Arzı / Akış",   "15%"),
        "derivatives":   ("Türev Piyasa Riski",  "20%"),
        "institutional": ("Kurumsal Talep",       "20%"),
    }

    st.markdown(
        "<div style='font-family:var(--font-mono);font-size:0.60rem;letter-spacing:0.14em;"
        "text-transform:uppercase;color:var(--text-muted);margin:10px 0 6px'>KATMAN SKORLARI</div>",
        unsafe_allow_html=True,
    )

    layer_cols = st.columns(5)
    for i, (k, (label, weight)) in enumerate(layer_labels.items()):
        ls = layer_scores.get(k, 50)
        lc = "var(--positive)" if ls >= 65 else ("var(--negative)" if ls <= 40 else "var(--text-muted)")
        with layer_cols[i]:
            st.markdown(
                f"<div style='text-align:center;padding:10px 6px;"
                f"border-radius:var(--r-sm);border:1px solid var(--border);"
                f"background:rgba(255,255,255,0.02)'>"
                f"<div style='font-family:var(--font-mono);font-size:1.35rem;font-weight:700;"
                f"color:{lc};line-height:1.1'>{ls}</div>"
                f"<div style='font-family:var(--font-mono);font-size:0.56rem;"
                f"color:var(--text-muted);margin-top:2px'>/100</div>"
                f"<div style='font-size:0.68rem;color:var(--text-secondary);"
                f"margin-top:4px;line-height:1.3'>{label}</div>"
                f"<div style='font-family:var(--font-mono);font-size:0.56rem;"
                f"color:var(--text-muted)'>{weight}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )

    # Driver özeti
    st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
    col_pos, col_neg = st.columns(2)
    with col_pos:
        st.markdown(
            "<div style='font-family:var(--font-mono);font-size:0.60rem;"
            "letter-spacing:0.12em;text-transform:uppercase;"
            "color:var(--positive);margin-bottom:6px'>✓ Pozitif Sinyaller</div>",
            unsafe_allow_html=True,
        )
        st.markdown(
            f"<div style='padding:8px 12px;border-radius:var(--r-sm);"
            f"border:1px solid rgba(50,217,140,0.15);background:rgba(50,217,140,0.04)'>"
            f"{_driver_list(pos_d, 'positive') or '<span style=\"font-size:0.76rem;color:var(--text-muted)\">Pozitif sinyal yok</span>'}"
            f"</div>",
            unsafe_allow_html=True,
        )
    with col_neg:
        st.markdown(
            "<div style='font-family:var(--font-mono);font-size:0.60rem;"
            "letter-spacing:0.12em;text-transform:uppercase;"
            "color:var(--negative);margin-bottom:6px'>✗ Negatif Sinyaller</div>",
            unsafe_allow_html=True,
        )
        st.markdown(
            f"<div style='padding:8px 12px;border-radius:var(--r-sm);"
            f"border:1px solid rgba(255,95,114,0.15);background:rgba(255,95,114,0.04)'>"
            f"{_driver_list(neg_d, 'negative') or '<span style=\"font-size:0.76rem;color:var(--text-muted)\">Negatif sinyal yok</span>'}"
            f"</div>",
            unsafe_allow_html=True,
        )

    # Risk Bayrakları
    if risk_flags:
        st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
        st.markdown(
            "<div style='font-family:var(--font-mono);font-size:0.60rem;letter-spacing:0.14em;"
            "text-transform:uppercase;color:var(--text-muted);margin-bottom:6px'>⚑ RİSK BAYRAKLARI</div>",
            unsafe_allow_html=True,
        )
        flags_html = "".join(
            f"<span style='display:inline-block;margin:2px 4px 2px 0;"
            f"padding:3px 10px;border-radius:20px;"
            f"border:1px solid {color}44;background:{color}11;"
            f"font-family:var(--font-mono);font-size:0.65rem;color:{color}'>"
            f"{flag}</span>"
            for flag, color in risk_flags
        )
        st.markdown(
            f"<div style='padding:8px 12px;border-radius:var(--r-sm);"
            f"border:1px solid var(--border);background:rgba(255,255,255,0.01)'>"
            f"{flags_html}</div>",
            unsafe_allow_html=True,
        )

    # Not
    if entry.get("notes"):
        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
        st.markdown(
            f"<div style='font-size:0.76rem;color:var(--text-muted);padding:8px 12px;"
            f"border-radius:var(--r-sm);border:1px solid var(--border-soft);"
            f"background:rgba(255,255,255,0.01)'>"
            f"<span style='font-family:var(--font-mono);font-size:0.58rem;"
            f"color:var(--text-faint)'>NOT · </span>{esc(entry['notes'])}"
            f"</div>",
            unsafe_allow_html=True,
        )


def _compute_manual_score(entry: dict) -> tuple[int, dict[str, int], list[str], list[str]]:
    """
    BCRM-14 Skor Motoru
    ====================
    5 katman → ağırlıklı ana skor (0–100)

    Katmanlar:
      A) Valuation / Cycle          — 25%  (NUPL, MVRV, MVRV Z-Score, Realized Price)
      B) Holder Behavior            — 20%  (LTH/STH Cost Basis, SOPR, STH P&L)
      C) Exchange Flows             — 15%  (Netflow, Reserve)
      D) Derivatives Risk           — 20%  (Funding, OI, Long/Short Liquidations)
      E) Institutional Demand       — 20%  (Coinbase Premium, ETF Flow)

    Döndürür: (ana_skor, {katman: skor}, pozitif_driver_listesi, negatif_driver_listesi)
    """
    def _g(k: str) -> Optional[float]:
        return get_metric_safe(entry, k)

    pos: list[str] = []
    neg: list[str] = []

    # ── Katman A: Valuation / Cycle — 25% ─────────────────────────────────
    # İç ağırlıklar: NUPL 30%, MVRV 25%, MVRV Z-Score 25%, Realized Price 20%
    a_scores: list[tuple[float, float]] = []  # (skor, ağırlık)

    nupl = _g("nupl")
    if nupl is not None:
        # Sağlıklı bölge 0.25–0.55, aşırı uçlar penalized
        if nupl < 0:
            s = 15; neg.append(f"NUPL {nupl:.3f} — Loss Zone, ağır stres")
        elif nupl < 0.25:
            s = 40; pos.append(f"NUPL {nupl:.3f} — Hope bölgesi, akümülasyon")
        elif nupl <= 0.55:
            s = 75; pos.append(f"NUPL {nupl:.3f} — Sağlıklı orta bant")
        elif nupl <= 0.70:
            s = 55; neg.append(f"NUPL {nupl:.3f} — Euphoria, dikkat")
        else:
            s = 25; neg.append(f"NUPL {nupl:.3f} — Dağıtım bölgesi, aşırı ısınma")
        a_scores.append((s, 0.30))

    mvrv = _g("mvrv")
    if mvrv is not None:
        if mvrv < 1.0:
            s = 20; neg.append(f"MVRV {mvrv:.3f} — Piyasa zararla, ayı stresi")
        elif mvrv < 1.2:
            s = 45
        elif mvrv <= 2.4:
            s = 75; pos.append(f"MVRV {mvrv:.3f} — Yapıcı değerleme bölgesi")
        elif mvrv <= 3.0:
            s = 50; neg.append(f"MVRV {mvrv:.3f} — Dikkat bölgesi")
        else:
            s = 20; neg.append(f"MVRV {mvrv:.3f} — Pahalı / Aşırı ısınma riski")
        a_scores.append((s, 0.25))

    mvrv_z = _g("mvrv_z_score")
    if mvrv_z is not None:
        if mvrv_z < 0:
            s = 25; neg.append(f"MVRV Z-Score {mvrv_z:.2f} — Zayıf değerleme")
        elif mvrv_z <= 1:
            s = 45
        elif mvrv_z <= 4:
            s = 78; pos.append(f"MVRV Z-Score {mvrv_z:.2f} — Sağlıklı bant")
        elif mvrv_z <= 6:
            s = 45; neg.append(f"MVRV Z-Score {mvrv_z:.2f} — Dikkat bölgesi")
        else:
            s = 15; neg.append(f"MVRV Z-Score {mvrv_z:.2f} — Aşırı ısınma / Tepe riski")
        a_scores.append((s, 0.25))

    real_p  = _g("realized_price")
    sth_cb  = _g("sth_cost_basis")
    lth_cb  = _g("lth_cost_basis")
    # Realized Price skoru: Fiyat üstünde mi altında mı (proxy: STH basis vs realized)
    if real_p and sth_cb:
        if sth_cb > real_p * 1.10:
            s = 75; pos.append(f"Realized Price: STH basis realized üstünde — piyasa kârlı yapı")
        elif sth_cb > real_p:
            s = 62
        elif sth_cb > real_p * 0.90:
            s = 40; neg.append(f"Realized Price: STH basis realized'a yakın — sıkışma")
        else:
            s = 20; neg.append(f"Realized Price: STH basis realized altında — stres")
        a_scores.append((s, 0.20))

    layer_a = int(round(sum(s * w for s, w in a_scores) / sum(w for _, w in a_scores))) if a_scores else 50

    # ── Katman B: Holder Behavior — 20% ───────────────────────────────────
    # İç ağırlıklar: Cost Basis 35%, SOPR 35%, STH P&L 30%
    b_scores: list[tuple[float, float]] = []

    # Cost Basis: fiyat proxy olarak STH basis kullanıyoruz
    # LTH üstü = yapısal pozitif (+10), STH üstü = kısa vadeli pozitif (+8)
    if sth_cb and lth_cb:
        if sth_cb > lth_cb * 1.05:
            # STH basis, LTH'nin belirgin üstünde → geç döngü / dikkat
            s = 45; neg.append(f"STH basis LTH'nin belirgin üstünde — geç döngü sinyali")
        elif sth_cb > lth_cb:
            s = 75; pos.append(f"Fiyat > STH Cost Basis > LTH Cost Basis — sağlıklı holder yapısı")
        elif sth_cb > lth_cb * 0.95:
            s = 55
        else:
            s = 25; neg.append(f"STH basis LTH altında — kısa vadeli holder baskısı")
        b_scores.append((s, 0.35))

    sopr = _g("sopr")
    if sopr is not None:
        if sopr > 1.03:
            s = 45; neg.append(f"SOPR {sopr:.4f} — Realize profit baskısı")
        elif sopr >= 1.00:
            s = 72; pos.append(f"SOPR {sopr:.4f} — Kârlı satış, piyasa sağlıklı")
        elif sopr >= 0.97:
            s = 35; neg.append(f"SOPR {sopr:.4f} — Zarar realizasyonu")
        else:
            s = 15; neg.append(f"SOPR {sopr:.4f} — Sert capitulation / satış baskısı")
        b_scores.append((s, 0.35))

    sth_rpl = _g("sth_rpl")
    if sth_rpl is not None:
        if sth_rpl < -15:
            s = 30; neg.append(f"STH P&L {sth_rpl:+.2f}% — Ağır zarar, capitulation bölgesi")
        elif sth_rpl < 0:
            s = 45; neg.append(f"STH P&L {sth_rpl:+.2f}% — STH zararda")
        elif sth_rpl <= 15:
            s = 70; pos.append(f"STH P&L {sth_rpl:+.2f}% — Kontrollü kâr, sağlıklı")
        elif sth_rpl <= 30:
            s = 55
        else:
            s = 30; neg.append(f"STH P&L {sth_rpl:+.2f}% — Aşırı kâr realizasyonu riski")
        b_scores.append((s, 0.30))

    layer_b = int(round(sum(s * w for s, w in b_scores) / sum(w for _, w in b_scores))) if b_scores else 50

    # ── Katman C: Exchange Flows — 15% ────────────────────────────────────
    # İç ağırlıklar: Netflow 55%, Reserve 45%
    c_scores: list[tuple[float, float]] = []

    ex_netflow = _g("exchange_netflow")
    if ex_netflow is not None:
        if ex_netflow < -3000:
            s = 85; pos.append(f"Exchange netflow {ex_netflow:+,.0f} BTC — Güçlü çekilme, arz sıkışması")
        elif ex_netflow < -500:
            s = 70; pos.append(f"Exchange netflow {ex_netflow:+,.0f} BTC — Net outflow trendi")
        elif ex_netflow <= 500:
            s = 52
        elif ex_netflow <= 2000:
            s = 35; neg.append(f"Exchange netflow {ex_netflow:+,.0f} BTC — Borsaya giriş artıyor")
        else:
            s = 15; neg.append(f"Exchange netflow {ex_netflow:+,.0f} BTC — Güçlü inflow, satış baskısı")
        c_scores.append((s, 0.55))

    ex_reserve = _g("exchange_reserve")
    if ex_reserve is not None:
        # Mutlak değer yerine trend proxy: çok düşük rezerv yapısal olumlu
        if ex_reserve < 2_200_000:
            s = 80; pos.append(f"Exchange reserve {ex_reserve:,.0f} BTC — Tarihsel düşük, arz sıkışması")
        elif ex_reserve < 2_600_000:
            s = 65
        elif ex_reserve < 3_000_000:
            s = 48
        else:
            s = 30; neg.append(f"Exchange reserve {ex_reserve:,.0f} BTC — Yüksek borsa arzı")
        c_scores.append((s, 0.45))

    layer_c = int(round(sum(s * w for s, w in c_scores) / sum(w for _, w in c_scores))) if c_scores else 50

    # ── Katman D: Derivatives Risk — 20% ──────────────────────────────────
    # İç ağırlıklar: Funding 30%, OI 35%, Liquidations 35%
    d_scores: list[tuple[float, float]] = []

    funding = _g("funding_rate")
    if funding is not None:
        if -0.005 <= funding <= 0.02:
            s = 72; pos.append(f"Funding {funding:+.4f}% — Nötr/sağlıklı, overcrowding yok")
        elif funding > 0.05:
            s = 20; neg.append(f"Funding {funding:+.4f}% — Aşırı long overcrowding")
        elif funding > 0.02:
            s = 45; neg.append(f"Funding {funding:+.4f}% — Long ağırlıklı, dikkat")
        elif funding < -0.02:
            s = 40; neg.append(f"Funding {funding:+.4f}% — Aşırı short, stres")
        else:
            s = 58; pos.append(f"Funding {funding:+.4f}% — Hafif negatif, short squeeze potansiyeli")
        d_scores.append((s, 0.30))

    oi = _g("open_interest")
    if oi is not None:
        # OI tek başına değil, funding ile birlikte yorumlanmalı
        # Burada mutlak değer eşikleri (milyar USD)
        if oi < 15:
            s = 70; pos.append(f"OI ${oi:.1f}B — Kaldıraç temizlenmiş, sağlıklı zemin")
        elif oi <= 25:
            s = 58
        elif oi <= 35:
            # Yüksek OI + yüksek funding = tehlike, yüksek OI + nötr funding = ok
            if funding is not None and funding > 0.03:
                s = 30; neg.append(f"OI ${oi:.1f}B + yüksek funding — Birikmiş kaldıraç riski")
            else:
                s = 48
        else:
            s = 22; neg.append(f"OI ${oi:.1f}B — Aşırı kaldıraç birikimi")
        d_scores.append((s, 0.35))

    long_liq  = _g("long_liquidations")
    short_liq = _g("short_liquidations")
    if long_liq is not None and short_liq is not None:
        total_liq = long_liq + short_liq
        long_dom  = long_liq / total_liq if total_liq > 0 else 0.5
        if total_liq < 20:
            s = 68; pos.append(f"Likidasyonlar düşük (${total_liq:.0f}M) — Kaldıraç dengeli")
        elif total_liq < 80:
            if long_dom > 0.65:
                s = 38; neg.append(f"Long flush baskın (${long_liq:.0f}M / ${total_liq:.0f}M) — Downside stres")
            elif long_dom < 0.35:
                s = 65; pos.append(f"Short squeeze baskın (${short_liq:.0f}M) — Yukarı baskı")
            else:
                s = 55
        else:
            if long_dom > 0.65:
                s = 18; neg.append(f"Ağır long flush (${long_liq:.0f}M) — Leverage Flush ⚠")
            elif long_dom < 0.35:
                s = 62; pos.append(f"Güçlü short squeeze (${short_liq:.0f}M)")
            else:
                s = 35; neg.append(f"Yoğun çift taraflı tasfiye (${total_liq:.0f}M) — Oynaklık riski")
        d_scores.append((s, 0.35))
    elif long_liq is not None:
        if long_liq > 150:
            s = 20; neg.append(f"Long liquidation yüksek (${long_liq:.0f}M) — Long flush")
        elif long_liq > 50:
            s = 40; neg.append(f"Long liquidation orta (${long_liq:.0f}M)")
        else:
            s = 65
        d_scores.append((s, 0.35))
    elif short_liq is not None:
        if short_liq > 150:
            s = 72; pos.append(f"Short liquidation yüksek (${short_liq:.0f}M) — Short squeeze")
        elif short_liq > 50:
            s = 60
        else:
            s = 55
        d_scores.append((s, 0.35))

    layer_d = int(round(sum(s * w for s, w in d_scores) / sum(w for _, w in d_scores))) if d_scores else 50

    # ── Katman E: Institutional Demand — 20% ──────────────────────────────
    # İç ağırlıklar: ETF Flow 55%, Coinbase Premium 45%
    e_scores: list[tuple[float, float]] = []

    etf_flow = _g("etf_flow_cumulative")
    if etf_flow is not None:
        if etf_flow > 70:
            s = 88; pos.append(f"Kümülatif ETF akışı ${etf_flow:.1f}B — Güçlü kurumsal birikim")
        elif etf_flow > 45:
            s = 72; pos.append(f"Kümülatif ETF akışı ${etf_flow:.1f}B — Pozitif kurumsal talep")
        elif etf_flow > 20:
            s = 52
        elif etf_flow > 5:
            s = 35; neg.append(f"Kümülatif ETF akışı ${etf_flow:.1f}B — Kurumsal talep zayıf")
        else:
            s = 18; neg.append(f"Kümülatif ETF akışı ${etf_flow:.1f}B — ETF ilgisi çok düşük")
        e_scores.append((s, 0.55))

    cb_prem = _g("coinbase_premium")
    if cb_prem is not None:
        if cb_prem > 0.10:
            s = 85; pos.append(f"Coinbase premium {cb_prem:+.4f} — Güçlü ABD kurumsal alımı")
        elif cb_prem > 0.01:
            s = 68; pos.append(f"Coinbase premium {cb_prem:+.4f} — Pozitif ABD spot talebi")
        elif cb_prem >= -0.05:
            s = 50
        elif cb_prem >= -0.15:
            s = 32; neg.append(f"Coinbase premium {cb_prem:+.4f} — ABD satımı")
        else:
            s = 15; neg.append(f"Coinbase premium {cb_prem:+.4f} — Güçlü ABD satış baskısı")
        e_scores.append((s, 0.45))

    layer_e = int(round(sum(s * w for s, w in e_scores) / sum(w for _, w in e_scores))) if e_scores else 50

    # ── Ana Skor ──────────────────────────────────────────────────────────
    layer_scores = {
        "valuation":     layer_a,
        "holder":        layer_b,
        "exchange":      layer_c,
        "derivatives":   layer_d,
        "institutional": layer_e,
    }

    # Veri olan katmanlar ağırlıklı ortalama
    weights = {"valuation": 0.25, "holder": 0.20, "exchange": 0.15, "derivatives": 0.20, "institutional": 0.20}
    available = {k: v for k, v in layer_scores.items() if _has_layer_data(k, entry)}

    if available:
        total_w   = sum(weights[k] for k in available)
        main_score = sum(layer_scores[k] * weights[k] for k in available) / total_w
    else:
        main_score = 50.0

    return max(0, min(100, int(round(main_score)))), layer_scores, pos, neg


def _has_layer_data(layer: str, entry: dict) -> bool:
    """Katmanda en az bir metrik girilmiş mi?"""
    layer_keys = {
        "valuation":     ["nupl", "mvrv", "mvrv_z_score", "realized_price"],
        "holder":        ["sth_cost_basis", "lth_cost_basis", "sopr", "sth_rpl"],
        "exchange":      ["exchange_netflow", "exchange_reserve"],
        "derivatives":   ["funding_rate", "open_interest", "long_liquidations", "short_liquidations"],
        "institutional": ["coinbase_premium", "etf_flow_cumulative"],
    }
    return any(get_metric_safe(entry, k) is not None for k in layer_keys.get(layer, []))


def _compute_risk_flags(entry: dict) -> list[tuple[str, str]]:
    """
    BCRM-14 Risk Bayrakları.
    Döndürür: [(bayrak_adı, renk_css_var), ...]
    """
    def _g(k: str) -> Optional[float]:
        return get_metric_safe(entry, k)

    flags: list[tuple[str, str]] = []
    funding   = _g("funding_rate")
    oi        = _g("open_interest")
    long_liq  = _g("long_liquidations")
    short_liq = _g("short_liquidations")
    ex_net    = _g("exchange_netflow")
    etf_flow  = _g("etf_flow_cumulative")
    cb_prem   = _g("coinbase_premium")
    nupl      = _g("nupl")
    mvrv      = _g("mvrv")
    mvrv_z    = _g("mvrv_z_score")
    sopr      = _g("sopr")
    sth_rpl   = _g("sth_rpl")
    sth_cb    = _g("sth_cost_basis")
    lth_cb    = _g("lth_cost_basis")

    # Derivatives
    if funding and oi and funding > 0.04 and oi > 25:
        flags.append(("Long Overcrowding Risk", "var(--negative)"))
    if funding and funding < -0.015 and sth_cb and lth_cb and sth_cb > lth_cb * 0.95:
        flags.append(("Short Squeeze Setup", "var(--positive)"))
    if long_liq and short_liq and (long_liq + short_liq) > 0:
        if long_liq / (long_liq + short_liq) > 0.70 and (long_liq + short_liq) > 80:
            flags.append(("Leverage Flush ⚠", "var(--negative)"))
        if short_liq / (long_liq + short_liq) > 0.70 and (long_liq + short_liq) > 80:
            flags.append(("Short Squeeze Active", "var(--positive)"))

    # Exchange
    if ex_net and ex_net > 3000:
        flags.append(("Exchange Inflow Stress", "var(--negative)"))

    # Institutional
    if etf_flow and cb_prem and etf_flow < 20 and cb_prem < -0.05:
        flags.append(("Institutional Demand Weakness", "var(--negative)"))

    # Holder stress
    if sopr and sopr < 0.97 and sth_rpl and sth_rpl < -10:
        flags.append(("Holder Stress / Capitulation", "var(--negative)"))
    if sth_cb and lth_cb and sth_cb < lth_cb * 0.95:
        flags.append(("STH Cost Basis Pressure", "var(--negative)"))

    # Overheated
    if nupl and nupl > 0.70:
        flags.append(("Overheated Valuation — NUPL", "var(--warning)"))
    if mvrv and mvrv > 3.0:
        flags.append(("Overheated Valuation — MVRV", "var(--warning)"))
    if mvrv_z and mvrv_z > 6:
        flags.append(("Overheated Valuation — Z-Score", "var(--warning)"))

    return flags


# ─── Geçmiş kayıt tablosu ────────────────────────────────────────────────────

def _render_history_table() -> None:
    """Kayıtlı tüm günlük girişleri tablo olarak göster."""
    all_entries = load_all_entries()
    if not all_entries:
        st.info("Henüz kayıtlı on-chain veri yok.")
        return

    rows = []
    for dt_key in sorted(all_entries.keys(), reverse=True):
        e = all_entries[dt_key]
        rows.append({
            "Tarih":           dt_key,
            "NUPL":            f"{e['nupl']:.4f}"         if e.get("nupl")            is not None else "—",
            "SOPR":            f"{e['sopr']:.4f}"         if e.get("sopr")            is not None else "—",
            "MVRV":            f"{e['mvrv']:.4f}"         if e.get("mvrv")            is not None else "—",
            "MVRV Z":          f"{e['mvrv_z_score']:.2f}" if e.get("mvrv_z_score")    is not None else "—",
            "LTH Basis":       f"${e['lth_cost_basis']:,.0f}" if e.get("lth_cost_basis") else "—",
            "STH Basis":       f"${e['sth_cost_basis']:,.0f}" if e.get("sth_cost_basis") else "—",
            "Realized P.":     f"${e['realized_price']:,.0f}" if e.get("realized_price")  else "—",
            "STH P&L":         f"{e['sth_rpl']:+.2f}%"    if e.get("sth_rpl")         is not None else "—",
            "Netflow (BTC)":   f"{e['exchange_netflow']:+,.0f}" if e.get("exchange_netflow") is not None else "—",
            "Reserve (BTC)":   f"{e['exchange_reserve']:,.0f}" if e.get("exchange_reserve") else "—",
            "Funding":         f"{e['funding_rate']:+.4f}%" if e.get("funding_rate")   is not None else "—",
            "OI ($B)":         f"{e['open_interest']:.2f}"  if e.get("open_interest")  is not None else "—",
            "Long Liq ($M)":   f"{e['long_liquidations']:.1f}"  if e.get("long_liquidations")  is not None else "—",
            "Short Liq ($M)":  f"{e['short_liquidations']:.1f}" if e.get("short_liquidations") is not None else "—",
            "CB Premium":      f"{e['coinbase_premium']:+.4f}" if e.get("coinbase_premium") is not None else "—",
            "ETF ($B)":        f"{e['etf_flow_cumulative']:.1f}" if e.get("etf_flow_cumulative") is not None else "—",
            "Kaydedildi":      e.get("_saved_at", "?")[:16],
        })

    df_hist = pd.DataFrame(rows)
    st.dataframe(df_hist, use_container_width=True, hide_index=True)


# ─── Main render function ─────────────────────────────────────────────────────

def render_onchain_tab() -> None:
    """
    Main entry point called from app.py.
    Renders the full ON-CHAIN DASHBOARD tab.
    Manuel Mod / Coin Metrics Mod toggle ile çalışır.
    """
    st.markdown(
        '<div class="s-kicker">On-Chain Intelligence</div>'
        '<div class="s-title">ON-CHAIN DASHBOARD</div>'
        '<div class="s-subtitle">'
        'Manuel girdi modu: CryptoQuant / Glassnode değerlerini sidebar\'dan girin. '
        'Coin Metrics modu: GitHub CSV (2 haftadır güncelleme almayabilir).'
        '</div>',
        unsafe_allow_html=True,
    )
    st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)

    # ── Mod seçici ────────────────────────────────────────────────────────
    mode_col, info_col = st.columns([0.4, 0.6])
    with mode_col:
        use_manual = st.toggle(
            "📊 Manuel Mod",
            value=True,
            help="Aktif: CryptoQuant/Glassnode değerlerini sidebar'dan gir. "
                 "Pasif: Coin Metrics GitHub CSV (güncel olmayabilir).",
            key="onchain_manual_mode",
        )
    with info_col:
        if use_manual:
            today_ok = has_today_entry()
            latest   = load_latest_entry()
            latest_date = None
            if latest:
                # en son kayıt tarihini bul
                all_e = load_all_entries()
                latest_date = max(all_e.keys()) if all_e else None
            badge_color = "var(--positive)" if today_ok else "var(--warning)"
            badge_text  = "Bugün girildi ✓" if today_ok else "Bugün veri yok"
            st.markdown(
                f"<div style='font-family:var(--font-mono);font-size:0.68rem;"
                f"color:{badge_color};padding-top:8px'>"
                f"{badge_text}"
                f"{'  ·  Son kayıt: ' + latest_date if latest_date else ''}"
                f"  ·  Toplam: {entry_count()} gün"
                f"</div>",
                unsafe_allow_html=True,
            )

    st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)

    # ─────────────────────────────────────────────────────────────────────
    # MANUEL MOD
    # ─────────────────────────────────────────────────────────────────────
    if use_manual:
        _render_manual_sidebar_form()

        latest_entry = load_latest_entry()
        if latest_entry is None:
            st.info(
                "Henüz on-chain veri girilmedi. Sol sidebar'daki formu kullanarak "
                "bugünün metriklerini kaydedin."
            )
            return

        _render_manual_dashboard(latest_entry)

        # Geçmiş kayıtlar
        st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)
        with st.expander(f"📅 Geçmiş Kayıtlar ({entry_count()} gün)", expanded=False):
            _render_history_table()

        # Footer
        st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)
        st.markdown(
            "<div style='font-size:0.7rem;color:var(--text-faint);line-height:1.6;"
            "padding:10px 14px;border-radius:6px;border:1px solid var(--border-soft);"
            "background:rgba(255,255,255,0.01)'>"
            "Manuel Mod: Değerler CryptoQuant / Glassnode / Coinglass gibi kaynaklardan "
            "elle girilmiştir. Skor ve driver listesi bu değerlerden hesaplanmıştır. "
            "Bu sayfa finansal tavsiye içermez."
            "</div>",
            unsafe_allow_html=True,
        )
        return

    # ─────────────────────────────────────────────────────────────────────
    # COIN METRICS MODU (mevcut davranış)
    # ─────────────────────────────────────────────────────────────────────
    ctrl_col, _ = st.columns([0.3, 0.7])
    with ctrl_col:
        force_refresh = st.button(
            "🔄 Veriyi Yenile",
            help="Coin Metrics GitHub'dan son CSV'leri indir (cache'i atla)",
            use_container_width=True,
        )

    with st.spinner("On-chain veriler hazırlanıyor…"):
        try:
            oc, btc_r, usdt_r, usdc_r, df_computed = _load_and_compute(
                force_refresh=bool(force_refresh)
            )
        except Exception as exc:  # noqa: BLE001
            st.error(f"On-chain veri yüklenirken hata: {exc}")
            return

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

    all_missing = btc_r.missing_columns + usdt_r.missing_columns + usdc_r.missing_columns
    if all_missing:
        st.warning(f"Bazı kolonlar eksik: {', '.join(all_missing)}")

    if oc.regime == "UNAVAILABLE":
        st.error(
            "On-chain veri şu an mevcut değil. GitHub erişimi başarısız "
            "ve lokal cache de bulunamadı. Manuel Mod'u aktifleştirerek devam edebilirsin."
        )
        if oc.warnings:
            with st.expander("Teknik Detaylar", expanded=False):
                for w in oc.warnings:
                    st.caption(f"⚠ {w}")
        return

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
    _render_charts_section(df_computed)
    st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)
    _render_driver_summary(oc)

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
