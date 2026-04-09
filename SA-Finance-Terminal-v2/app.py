"""
SA Finance Alpha Terminal — v20
Main entry point.  Presentation only; business logic lives in domain/ and services/.
"""
import html
import os

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from dotenv import load_dotenv
from openai import APIConnectionError, APIError, APITimeoutError, RateLimitError

from domain.analytics import (
    DEFAULT_PINNED_METRICS,
    METRIC_LABELS,
    build_alerts,
    build_analytics_payload,
    build_daily_summary_markdown,
    markdown_to_basic_pdf_bytes,
)
from domain.market_brief import build_market_brief
from services.ai_service import (
    _fallback_terminal_report,
    _fallback_x_lead,
    _fallback_x_thread,
    build_openrouter_client,
    generate_strategy_report,
)
from services.health import build_health_summary, merge_source_health
from services.market_data import load_terminal_data
from services.preferences import load_preferences, save_preferences
from ui.components import (
    bi_label,
    cat,
    clean_text,
    display_value,
    esc,
    render_compact_metric_strip,
    render_cards,
    render_data_table_card,
    render_health_bar,
    render_info_panel,
    render_market_brief,
)
from ui.layout import normalize_health_cell, render_page_header, render_sidebar, render_status_hub
from ui.theme import TERMINAL_CSS

load_dotenv()
FRED_API_KEY        = os.getenv("FRED_API_KEY", "")
OPENROUTER_API_KEY  = os.getenv("OPENROUTER_API_KEY", "")
AGGR_PANEL_URL      = "https://aggr.trade/brutalbtc-copy-1"

st.set_page_config(
    page_title="SA Finance Alpha Terminal",
    page_icon="⬡",
    layout="wide",
    initial_sidebar_state="expanded",
)
st.markdown(TERMINAL_CSS, unsafe_allow_html=True)

# ─── DATA SECTION CONFIGS ────────────────────────────────────────────────────

MACRO_MARKET_SECTIONS = [
    {"title": "US Endeksleri",      "kicker": "Americas",      "caption": "", "rows": [("S&P 500","SP500"),("NASDAQ","NASDAQ"),("Dow Jones","DOW")]},
    {"title": "Avrupa Endeksleri",  "kicker": "Europe",        "caption": "", "rows": [("DAX","DAX"),("FTSE 100","FTSE"),("BIST 100","BIST100")]},
    {"title": "Asya Endeksleri",    "kicker": "Asia / Vol",    "caption": "", "rows": [("Nikkei 225","NIKKEI"),("Hang Seng","HSI"),("VIX","VIX")]},
    {"title": "Metaller",           "kicker": "Commodities",   "caption": "", "rows": [("Altın / oz","GOLD"),("Gümüş / oz","SILVER"),("Bakır","COPPER")]},
    {"title": "Enerji & Tarım",     "kicker": "Energy & Agri", "caption": "", "rows": [("Ham Petrol WTI","OIL"),("Doğalgaz","NATGAS"),("Buğday","WHEAT")]},
    {"title": "Majors FX",          "kicker": "FX Majors",     "caption": "", "rows": [("EUR/USD","EURUSD"),("GBP/USD","GBPUSD"),("USD/JPY","USDJPY")]},
    {"title": "Crosses & TRY",      "kicker": "FX Crosses",    "caption": "", "rows": [("USD/CHF","USDCHF"),("AUD/USD","AUDUSD"),("USD/TRY","USDTRY")]},
    {"title": "Policy & Liquidity", "kicker": "Core Macro",    "caption": "", "rows": [("FED Faizi","FED"),("M2 YoY","M2"),("ABD 10Y","US10Y"),("DXY","DXY"),("BTC↔SP500","Corr_SP500"),("BTC↔Altın","Corr_Gold")]},
]

FLOW_RISK_SECTIONS = [
    {"title": "Türev & Sentiment",      "kicker": "Positioning",       "caption": "", "rows": [("Open Interest","OI"),("Funding Rate","FR"),("Taker B/S","Taker"),("L/S Oranı","LS_Ratio"),("Long %","Long_Pct"),("Short %","Short_Pct"),("L/S Sinyal","LS_Signal"),("Korku/Açgözlülük","FNG"),("FNG Dün","FNG_PREV")]},
    {"title": "Order Book & ETF",        "kicker": "Execution Levels",  "caption": "", "rows": [("Destek Duvarı","Sup_Wall"),("Destek Hacmi","Sup_Vol"),("Direnç Duvarı","Res_Wall"),("Direnç Hacmi","Res_Vol"),("Tahta Durumu","Wall_Status"),("Birleşik Sinyal","ORDERBOOK_SIGNAL"),("Birleşik Detay","ORDERBOOK_SIGNAL_DETAIL"),("ETF Netflow","ETF_FLOW_TOTAL"),("ETF Tarih","ETF_FLOW_DATE"),("Kaynaklar","ORDERBOOK_SOURCES")]},
    {"title": "Stablecoin & On-Chain",   "kicker": "Liquidity Plumbing","caption": "", "rows": [("Toplam Stable","Total_Stable"),("USDT","USDT_MCap"),("USDC","USDC_MCap"),("DAI","DAI_MCap"),("Stable.C.D","STABLE_C_D"),("USDT.D","USDT_D"),("USDT Dom Stable","USDT_Dom_Stable"),("Hashrate","Hash"),("Aktif Adres","Active")]},
    {"title": "Crypto Participation",    "kicker": "Breadth Layers",    "caption": "", "rows": [("TOTAL","TOTAL_CAP"),("TOTAL2","TOTAL2_CAP"),("TOTAL3","TOTAL3_CAP"),("OTHERS","OTHERS_CAP"),("BTC Dom","Dom"),("ETH Dom","ETH_Dom")]},
    {"title": "Macro Participation",     "kicker": "ETF Breadth",       "caption": "", "rows": [("SPY","SPY_C"),("RSP","RSP_C"),("QQQ","QQQ_C"),("IWM","IWM_C"),("XLK","XLK_C"),("XLF","XLF_C"),("XLI","XLI_C"),("XLE","XLE_C"),("XLY","XLY_C")]},
]

DATA_ATLAS_SECTIONS = [
    {"title": "BTC & Kripto",         "rows": [("BTC Fiyatı","BTC_P"),("BTC 24s","BTC_C"),("BTC 7g","BTC_7D"),("BTC MCap","BTC_MCap"),("24s Hacim","Vol_24h"),("BTC Dom","Dom"),("ETH Dom","ETH_Dom"),("Total MCap","TOTAL_CAP"),("Total Hacim","Total_Vol")]},
    {"title": "Türev & Sentiment",    "rows": [("OI","OI"),("Funding Rate","FR"),("Taker B/S","Taker"),("L/S Oranı","LS_Ratio"),("Long %","Long_Pct"),("Short %","Short_Pct"),("L/S Sinyal","LS_Signal"),("Fear&Greed","FNG"),("FNG Dün","FNG_PREV")]},
    {"title": "Order Book & ETF",     "rows": [("Destek Duvarı","Sup_Wall"),("Destek Hacmi","Sup_Vol"),("Direnç Duvarı","Res_Wall"),("Direnç Hacmi","Res_Vol"),("Tahta","Wall_Status"),("Sinyal","ORDERBOOK_SIGNAL"),("Detay","ORDERBOOK_SIGNAL_DETAIL"),("Kaynaklar","ORDERBOOK_SOURCES"),("ETF Netflow","ETF_FLOW_TOTAL"),("ETF Tarih","ETF_FLOW_DATE")]},
    {"title": "Crypto Participation", "rows": [("TOTAL","TOTAL_CAP"),("TOTAL2","TOTAL2_CAP"),("TOTAL3","TOTAL3_CAP"),("OTHERS","OTHERS_CAP"),("BTC Dom","Dom"),("ETH Dom","ETH_Dom")]},
    {"title": "Stablecoin & On-Chain","rows": [("Toplam Stable","Total_Stable"),("USDT","USDT_MCap"),("USDC","USDC_MCap"),("DAI","DAI_MCap"),("Stable.C.D","STABLE_C_D"),("USDT.D","USDT_D"),("USDT Dom Stable","USDT_Dom_Stable"),("Hashrate","Hash"),("Aktif Adres","Active")]},
    {"title": "Policy & Liquidity",   "rows": [("FED Faizi","FED"),("M2 YoY","M2"),("ABD 10Y","US10Y"),("DXY","DXY"),("VIX","VIX"),("BTC↔SP500","Corr_SP500"),("BTC↔Altın","Corr_Gold")]},
    {"title": "Endeksler & Emtia",    "rows": [("S&P 500","SP500"),("NASDAQ","NASDAQ"),("DAX","DAX"),("NIKKEI","NIKKEI"),("BIST100","BIST100"),("Altın","GOLD"),("Gümüş","SILVER"),("Petrol","OIL"),("Doğalgaz","NATGAS"),("Bakır","COPPER")]},
    {"title": "Macro ETF Breadth",    "rows": [("SPY","SPY_C"),("RSP","RSP_C"),("QQQ","QQQ_C"),("IWM","IWM_C"),("XLK","XLK_C"),("XLF","XLF_C"),("XLI","XLI_C"),("XLE","XLE_C"),("XLY","XLY_C")]},
    {"title": "Forex",                "rows": [("EUR/USD","EURUSD"),("GBP/USD","GBPUSD"),("USD/JPY","USDJPY"),("USD/TRY","USDTRY"),("USD/CHF","USDCHF"),("AUD/USD","AUDUSD")]},
]

CRYPTO_RADAR_ASSETS = [
    ("Bitcoin",   "BTC",  "BTC_P",  "BTC_C",  "BTC_7D"),
    ("Ethereum",  "ETH",  "ETH_P",  "ETH_C",  "ETH_7D"),
    ("Solana",    "SOL",  "SOL_P",  "SOL_C",  "SOL_7D"),
    ("BNB Chain", "BNB",  "BNB_P",  "BNB_C",  "BNB_7D"),
    ("Ripple",    "XRP",  "XRP_P",  "XRP_C",  "XRP_7D"),
    ("Cardano",   "ADA",  "ADA_P",  "ADA_C",  "ADA_7D"),
    ("Avalanche", "AVAX", "AVAX_P", "AVAX_C", "AVAX_7D"),
    ("Polkadot",  "DOT",  "DOT_P",  "DOT_C",  "DOT_7D"),
    ("Chainlink", "LINK", "LINK_P", "LINK_C", "LINK_7D"),
]

# ─── HELPERS ─────────────────────────────────────────────────────────────────

def data_rows(data: dict, items, *, include_change: bool = False):
    if include_change:
        return [(label, data.get(key, "-"), data.get(f"{key}_C", "-")) for label, key in items]
    return [(label, data.get(key, "-")) for label, key in items]


def section_variant(section: dict, **overrides) -> dict:
    return {**section, **overrides}


def render_table_row(data: dict, sections: list[dict], cols: int, *, include_change: bool = False):
    columns = st.columns(cols)
    for column, section in zip(columns, sections):
        with column:
            render_data_table_card(
                section["title"],
                data_rows(data, section["rows"], include_change=include_change),
                kicker=section.get("kicker", ""),
                caption=section.get("caption", ""),
                show_delta=include_change,
            )


def parse_percent_value(value) -> float | None:
    if value in (None, "", "-"):
        return None
    try:
        return float(str(value).replace("%", "").replace(",", "").strip())
    except ValueError:
        return None


def relative_to_btc_tone(asset_move, btc_move) -> str:
    a = parse_percent_value(asset_move)
    b = parse_percent_value(btc_move)
    if a is None or b is None:
        return "BTC referansı yok"
    diff = a - b
    if diff > 0.35:  return "BTC'den güçlü"
    if diff < -0.35: return "BTC'den zayıf"
    return "BTC'ye yakın"


def participation_alignment_label(macro: int, crypto: int) -> str:
    gap = abs(macro - crypto)
    if gap <= 8:  return "Aligned"
    if gap <= 18: return "Mixed"
    return "Diverging"


def breadth_quality_label(factor: dict) -> str:
    s = factor["score"]
    if s >= 72: return "Broadening"
    if s >= 58: return "Supported"
    if s >= 42: return "Selective"
    return "Narrow"


def score_delta_meta(delta_7d: int) -> tuple[str, str]:
    if delta_7d > 1:  return f"7g +{delta_7d}", "fc-delta-up"
    if delta_7d < -1: return f"7g {delta_7d}", "fc-delta-down"
    return "7g 0", "fc-delta-flat"


def build_positioning_emphasis(factor: dict, brief: dict) -> tuple[str, str]:
    crowded = {"Longlar Kalabalık", "Short Baskısı"}
    if factor["score"] <= 45 or brief["positioning"]["title"] in crowded:
        return "Crowding riski yüksek; yeni agresyon için participation teyidi gerekli.", "risk"
    if factor["score"] <= 60:
        return "Akış seçici ama kırılgan olabilir; funding ve L/S dengesini izle.", "warn"
    return "Pozisyonlanma şu an rejimi bozacak kadar tek tarafa yığılmıyor.", "ok"


def build_execution_bridge(scores: dict, brief: dict) -> tuple[str, list[tuple[str, str]], str, str]:
    overall      = scores["overall"]
    fragility    = scores["fragility"]["score"]
    participation = scores["participation"]["score"]
    if overall >= 60 and fragility <= 55:
        return (
            "Destekten gelen teyitli devam hareketleri, geç kalınmış breakout kovalamaktan daha temiz davranış sunar.",
            [("Preferred", "Support-led continuation"), ("Aggressive If", "Participation aligned"), ("Defensive While", "VIX keeps rising")],
            brief["focus"]["badge"], "ok",
        )
    if fragility >= 65 or participation < 55:
        return (
            "Execution daha taktik olmalı; seviyeler çalışsa bile participation teyidi olmadan agresyon pahalıya mal olabilir.",
            [("Preferred", "Fade extremes, respect walls"), ("Aggressive If", "Breadth & funding improve"), ("Defensive While", "Fragility elevated")],
            "WATCH", "warn",
        )
    return (
        "Rejim yapıcı ama kusursuz değil; sadece teyitli bölgelerde ağırlık artırmak daha sağlıklı.",
        [("Preferred", "Selective continuation"), ("Aggressive If", "Support holds + calmer positioning"), ("Defensive While", "Participation diverges")],
        brief["focus"]["badge"], "warn",
    )


# ─── PREFERENCES ─────────────────────────────────────────────────────────────

def init_preferences():
    if "preferences" not in st.session_state:
        st.session_state["preferences"] = load_preferences()


def init_ui_state():
    if "control_rail_open" not in st.session_state:
        st.session_state["control_rail_open"] = True
    if "macro_bulten_report" not in st.session_state:
        st.session_state["macro_bulten_report"] = None


def render_preferences_panel(host, key_prefix: str = "prefs", *, expanded: bool = False):
    preferences = st.session_state["preferences"]
    with host.expander("Görünüm ve Uyarılar", expanded=expanded):
        view_mode = host.radio(
            "Görünüm modu",
            ["Basit", "Pro"],
            index=0 if preferences.get("view_mode") == "Basit" else 1,
            key=f"{key_prefix}_view_mode",
        )
        report_depth = host.selectbox(
            "Rapor seviyesi",
            ["Kısa", "Orta", "Derin"],
            index=["Kısa", "Orta", "Derin"].index(preferences.get("report_depth", "Orta")),
            key=f"{key_prefix}_report_depth",
        )
        pinned_metrics = host.multiselect(
            "Pinli metrikler",
            options=list(METRIC_LABELS),
            default=preferences.get("pinned_metrics", DEFAULT_PINNED_METRICS),
            format_func=lambda key: METRIC_LABELS.get(key, key),
            key=f"{key_prefix}_pinned_metrics",
        )
        funding_above = host.number_input("Funding > X",    value=float(preferences["thresholds"].get("funding_above", 0.01)), step=0.005, format="%.4f", key=f"{key_prefix}_funding_above")
        vix_above     = host.number_input("VIX > Y",        value=float(preferences["thresholds"].get("vix_above", 25.0)),     step=0.5,   format="%.2f", key=f"{key_prefix}_vix_above")
        etf_flow      = host.number_input("ETF netflow < Z", value=float(preferences["thresholds"].get("etf_flow_below", 0.0)), step=10.0,  format="%.1f", key=f"{key_prefix}_etf_flow_below")
        if host.button("Ayarları Kaydet", key=f"{key_prefix}_save", use_container_width=True):
            preferences["view_mode"]    = view_mode
            preferences["report_depth"] = report_depth
            preferences["pinned_metrics"] = pinned_metrics[:8]
            preferences["thresholds"] = {"funding_above": funding_above, "vix_above": vix_above, "etf_flow_below": etf_flow}
            save_preferences(preferences)
            st.session_state["preferences"] = preferences
            host.success("Ayarlar kaydedildi.")


# ─── CONTROL RAIL ────────────────────────────────────────────────────────────

def render_control_rail(data: dict, brief: dict, last_updated: str, health_summary: dict, alerts: list[dict]):
    rail_open = st.session_state.get("control_rail_open", True)
    tb_left, tb_mid, tb_right = st.columns([1.0, 0.9, 2.6])
    with tb_left:
        if st.button("Paneli gizle" if rail_open else "Paneli göster", key="toggle_control_rail", use_container_width=True):
            st.session_state["control_rail_open"] = not rail_open
            st.rerun()
    with tb_mid:
        if st.button("Verileri yenile", key="refresh_main_control", use_container_width=True):
            st.cache_data.clear()
            st.rerun()
    with tb_right:
        st.markdown(
            f'<div style="font-size:0.8rem;color:var(--text-muted);padding-top:8px">'
            f'Operasyon paneli · Son güncelleme: {esc(last_updated)} · Odak: {esc(brief["focus"]["detail"])}'
            f'</div>',
            unsafe_allow_html=True,
        )

    if not st.session_state.get("control_rail_open", True):
        st.markdown(
            "<div class='section-notice'>Operasyon paneli gizli. Yukarıdaki buton ile tekrar açabilirsin.</div>",
            unsafe_allow_html=True,
        )
        return

    col_ops, col_prefs = st.columns([1.0, 1.1])
    with col_ops:
        st.markdown(
            '<div class="s-kicker" style="margin-bottom:8px">Operasyon</div>',
            unsafe_allow_html=True,
        )
        export_df = pd.DataFrame(
            [(k, v) for k, v in data.items() if k not in {"NEWS", "_health"}],
            columns=["Metrik", "Deger"],
        )
        st.download_button(
            "CSV İndir",
            export_df.to_csv(index=False, sep=";").encode("utf-8-sig"),
            file_name=f"AlphaTerminal_{pd.Timestamp.now().strftime('%Y%m%d_%H%M')}.csv",
            mime="text/csv",
            key="download_main_control",
            use_container_width=True,
        )
        st.markdown(
            f'<div class="alert-item" style="margin-top:10px">'
            f'<strong>Özet</strong>'
            f'<span>Rejim: {esc(brief["regime"]["title"])} · Aktif alarm: {len(alerts)}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )
    with col_prefs:
        render_preferences_panel(st, key_prefix="main_control", expanded=True)


# ─── SIGNAL DECK ─────────────────────────────────────────────────────────────

def render_signal_deck(
    kicker: str, title: str, copy: str, rows: list[tuple[str, object]],
    *, score_value: str, score_label: str,
    chips: list[str] | None = None,
    context_rows: list[tuple[str, object]] | None = None,
    emphasis: str = "", emphasis_kind: str = "warn",
):
    chip_html = "".join(
        f"<span class='sd-chip'>{esc(c)}</span>"
        for c in (chips or []) if c
    )
    ctx_html = "".join(
        f"<div class='sd-ctx-item'>"
        f"<span class='sd-ctx-label'>{esc(lbl)}</span>"
        f"<span class='sd-ctx-value'>{esc(display_value(val))}</span>"
        f"</div>"
        for lbl, val in (context_rows or [])
    )
    rows_html = "".join(
        f"<div class='sd-row'><span class='sd-row-key'>{esc(lbl)}</span><span class='sd-row-val'>{esc(display_value(val))}</span></div>"
        for lbl, val in rows
    )
    band_html = (
        f"<div class='sd-band sd-band-{esc(emphasis_kind)}'>{esc(emphasis)}</div>"
        if emphasis else ""
    )
    chip_block = f"<div class='sd-chips'>{chip_html}</div>" if chip_html else ""
    ctx_block  = f"<div class='sd-ctx-grid'>{ctx_html}</div>" if ctx_html else ""

    st.markdown(
        f"<div class='signal-deck'>"
        f"<div class='s-kicker'>{esc(kicker)}</div>"
        f"<div class='sd-top'>"
        f"<div class='sd-title'>{esc(title)}</div>"
        f"<div class='sd-score-block'>"
        f"<span class='sd-score-num'>{esc(score_value)}</span>"
        f"<span class='sd-score-label'>{esc(score_label)}</span>"
        f"</div>"
        f"</div>"
        f"<div class='sd-copy'>{esc(copy)}</div>"
        f"{band_html}{chip_block}{ctx_block}"
        f"<div class='sd-rows'>{rows_html}</div>"
        f"</div>",
        unsafe_allow_html=True,
    )


def render_breadth_surface(title: str, factor: dict, rows, *, kicker: str, note: str = ""):
    delta_text, _ = score_delta_meta(factor["delta_7d"])
    chips = [
        factor["state"],
        f"Weight {int(round(factor['weight'] * 100))}%",
        delta_text,
        factor.get("primary_support", ""),
        "proxy-based" if factor.get("proxy_note") else "",
    ]
    render_signal_deck(
        kicker, title, note or factor["summary"], rows,
        score_value=f"{factor['score']}/100",
        score_label=factor.get("confidence_label", ""),
        chips=[c for c in chips if c],
        context_rows=[
            ("Quality",  breadth_quality_label(factor)),
            ("Driver",   factor.get("primary_support", "-")),
            ("Weakest",  factor.get("primary_risk", "-")),
        ],
    )


# ─── REGIME / SCORE PANEL ────────────────────────────────────────────────────

def render_score_panel(analytics: dict):
    scores = analytics["scores"]

    # Contribution bars
    contrib_html = "".join(
        f'<div class="contrib-row">'
        f'<div class="contrib-label">{esc(f["label"])}</div>'
        f'<div class="contrib-bar-track"><div class="contrib-bar-fill" style="width:{f["score"]}%"></div></div>'
        f'<div class="contrib-pts">{f["contribution"]:.1f} pt</div>'
        f'</div>'
        for f in sorted(scores["factors"], key=lambda x: x["contribution"], reverse=True)
    )

    # Fragility flags
    frag_flags = "".join(
        f"<div class='frag-flag'>{esc(flag)}</div>"
        for flag in scores["fragility"]["flags"]
    )

    # Cue chips
    cues_html = "".join(
        f"<div class='cue-chip'><span>{esc(lbl)}</span><strong>{esc(val)}</strong></div>"
        for lbl, val in [
            ("Dominant Driver", scores["dominant_driver"]),
            ("Weakest Link",    scores["weakest_driver"]),
            ("Confidence",      f"{scores['confidence']}/100"),
        ]
    )

    # Factor cards
    factor_cards = ""
    for f in scores["factors"]:
        delta_text, delta_cls = score_delta_meta(f["delta_7d"])
        drivers_html = "".join(f"<div class='fc-driver'>{esc(d)}</div>" for d in f["drivers"])
        factor_cards += (
            f'<div class="factor-card">'
            f'<div class="fc-head"><span class="fc-name">{esc(f["label"])}</span><span class="fc-weight">Weight {f["weight_pct"]}%</span></div>'
            f'<div class="fc-score-row">'
            f'<div class="fc-score">{f["score"]}/100</div>'
            f'<div class="fc-delta {delta_cls}">{delta_text}</div>'
            f'</div>'
            f'<div class="fc-copy">{esc(f["summary"])}</div>'
            f'<div class="fc-meta"><span>Katkı {f["contribution"]:.1f} pt</span><span>{esc(f["trend_text"])}</span></div>'
            f'<div class="fc-drivers">{drivers_html}</div>'
            f'</div>'
        )

    left_col, right_col = st.columns([1.38, 0.62])

    with left_col:
        st.markdown(
            f'<div class="regime-hero">'
            f'<div class="s-kicker">Risk Engine · Rejim Haritası</div>'
            f'<div style="display:flex;justify-content:space-between;align-items:flex-start;gap:12px;margin-top:4px">'
            f'<div>'
            f'<div class="s-title" style="font-size:0.86rem;font-weight:500;color:var(--text-muted)">Overall Regime Score</div>'
            f'<div class="regime-score-num">{scores["overall"]}/100</div>'
            f'</div>'
            f'<div class="regime-overlay-badge">{esc(scores["overlay"])}</div>'
            f'</div>'
            f'<div class="regime-band-copy">{esc(scores["regime_band"])}. Dominant sürücü {esc(scores["dominant_driver"])}; en zayıf halka {esc(scores["weakest_driver"])}.</div>'
            f'<div class="cue-row">{cues_html}</div>'
            f'<div class="regime-stats-row">'
            f'<div class="rstat"><span class="rstat-label">Base Score</span><span class="rstat-value">{scores["base_score"]}/100</span></div>'
            f'<div class="rstat"><span class="rstat-label">Fragility Penalty</span><span class="rstat-value">−{scores["penalty"]}</span></div>'
            f'<div class="rstat"><span class="rstat-label">Confidence</span><span class="rstat-value">{scores["confidence"]}/100 · {esc(scores["confidence_label"])}</span></div>'
            f'</div>'
            f'<div class="contrib-list">{contrib_html}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    with right_col:
        st.markdown(
            f'<div class="frag-panel">'
            f'<div class="s-kicker">Fragility Overlay</div>'
            f'<div class="frag-score">{scores["fragility"]["score"]}/100</div>'
            f'<div class="frag-label">{esc(scores["fragility"]["label"])}</div>'
            f'<div class="s-subtitle" style="margin-top:10px">Rejim skoru yüksek olsa da fragility ayrı okunur. Yüksek fragility, geniş tabanlı sağlıklı ortam garantisi değildir.</div>'
            f'<div class="frag-flags">{frag_flags}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
    st.markdown(
        f'<div class="factor-grid-2">{factor_cards}</div>',
        unsafe_allow_html=True,
    )


# ─── COMMAND SURFACE ─────────────────────────────────────────────────────────

def render_command_surface(data: dict, brief: dict, analytics: dict, alerts: list[dict], health_summary: dict):
    scores = analytics["scores"]
    what_matters = (
        brief["regime"].get("why", [])[:1]
        + brief["liquidity"].get("why", [])[:1]
        + brief["positioning"].get("why", [])[:1]
    )
    invalidate_items = scores.get("invalidate_conditions", [])[:3]
    watch_items      = scores.get("watch_next", [])[:3]

    stat_html = "".join(
        f'<div class="cs-stat"><span class="cs-stat-label">{esc(lbl)}</span><span class="cs-stat-value">{esc(val)}</span></div>'
        for lbl, val in [
            ("Current Bias",     scores["bias"]),
            ("Focus Level",      brief["focus"]["title"]),
            ("Dominant Driver",  scores["dominant_driver"]),
            ("Weakest Link",     scores["weakest_driver"]),
        ]
    )
    matters_html    = "".join(f"<div class='cs-item'>{esc(i)}</div>" for i in what_matters)
    invalidate_html = "".join(f"<div class='cs-item'>{esc(i)}</div>" for i in invalidate_items)
    watch_html      = "".join(f"<div class='cs-item'>{esc(i)}</div>" for i in watch_items)

    st.markdown(
        f'<div class="command-surface">'
        f'<div>'
        f'<div class="s-kicker">Decision Layer · Komuta Yüzeyi</div>'
        f'<div class="cs-title">{esc(scores["overlay"])}</div>'
        f'<div class="cs-copy">{esc(scores["summary"])} Bugünün tezi: {esc(brief["regime"]["title"])}, {esc(brief["liquidity"]["title"])}, {esc(brief["positioning"]["title"])} birlikte okunmalı.</div>'
        f'</div>'
        f'<div class="cs-stat-grid">{stat_html}</div>'
        f'<div class="cs-cols">'
        f'<div class="cs-block"><div class="cs-block-title">What Matters Now</div><div class="cs-list">{matters_html}</div></div>'
        f'<div class="cs-block"><div class="cs-block-title">Invalidate If</div><div class="cs-list">{invalidate_html}</div></div>'
        f'</div>'
        f'<div class="cs-block"><div class="cs-block-title">Watch Next</div><div class="cs-list">{watch_html}</div></div>'
        f'</div>',
        unsafe_allow_html=True,
    )


# ─── SCENARIO MATRIX ─────────────────────────────────────────────────────────

def render_scenario_matrix(analytics: dict):
    rows_html = "".join(
        f'<tr><td>{esc(r["Scenario"])}</td><td>{esc(r["Trigger"])}</td><td>{esc(r["Follow-through"])}</td></tr>'
        for r in analytics["scenarios"]
    )
    st.markdown(
        f'<div class="surface surface-sm">'
        f'<div class="s-kicker">Execution Map · Senaryo Matrisi</div>'
        f'<div class="s-title" style="font-size:1rem">Trigger → Follow-through</div>'
        f'<div class="s-subtitle">Sonraki hareketin hangi koşullarda teyit edildiğini gösterir.</div>'
        f'<table class="matrix-table"><thead><tr><th>Senaryo</th><th>Trigger</th><th>Takip Sinyali</th></tr></thead>'
        f'<tbody>{rows_html}</tbody></table>'
        f'</div>',
        unsafe_allow_html=True,
    )


# ─── CATALYST STREAM ─────────────────────────────────────────────────────────

def get_source_health_rows(health_summary: dict, sources: list[str] | None = None, *, include_ok: bool = False):
    rows = list(health_summary.get("rows", []))
    if sources:
        source_set = set(sources)
        rows = [r for r in rows if r.get("Kaynak") in source_set]
    if not include_ok:
        rows = [r for r in rows if r.get("Durum") != "OK"]
    return rows


def render_catalyst_stream(data: dict, analytics: dict, alerts: list[dict], health_summary: dict):
    scores     = analytics["scores"]
    issue_rows = get_source_health_rows(health_summary, include_ok=False)[:3]
    alert_rows = alerts[:3] or [{"title": "Aktif alarm yok", "detail": "Eşik bazlı alarm akışı şu an sessiz."}]

    alert_html = "".join(
        f'<div class="cs-item"><strong style="color:var(--text-primary)">{esc(a["title"])}</strong> — {esc(a["detail"])}</div>'
        for a in alert_rows
    )
    watch_items = list(scores.get("watch_next", [])[:2]) + [f"Veri sorunları: {len(issue_rows)}"]
    watch_html  = "".join(f"<div class='cs-item'>{esc(i)}</div>" for i in watch_items)

    st.markdown(
        f'<div class="catalyst-stream">'
        f'<div class="s-kicker">Catalyst Stream · Katalizör Akışı</div>'
        f'<div class="s-title" style="font-size:1rem">Bugün neyi izliyoruz?</div>'
        f'<div class="s-subtitle">Tetikleyiciler ve data sağlığı özeti. Detaylı health → Status Hub.</div>'
        f'<div class="cs-stream-cols">'
        f'<div class="cs-block"><div class="cs-block-title">Active Alerts</div><div class="cs-list">{alert_html}</div></div>'
        f'<div class="cs-block"><div class="cs-block-title">Next Checkpoints</div><div class="cs-list">{watch_html}</div></div>'
        f'</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


# ─── DOWNLOADS ───────────────────────────────────────────────────────────────

def render_downloads(data: dict, brief: dict, analytics: dict, alerts: list[dict], health_summary: dict):
    summary_md  = build_daily_summary_markdown(data, brief, analytics, alerts, health_summary)
    summary_pdf = markdown_to_basic_pdf_bytes(summary_md)
    c1, c2 = st.columns(2)
    c1.download_button("Günlük Özet (Markdown)", summary_md, file_name="gunluk_ozet.md", mime="text/markdown", use_container_width=True)
    c2.download_button("Günlük Özet (PDF)",      summary_pdf, file_name="gunluk_ozet.pdf", mime="application/pdf", use_container_width=True)


# ─── REPORT PANEL ────────────────────────────────────────────────────────────

def _format_report_body_html(body: str) -> str:
    lines = str(body or "Veri bekleniyor").splitlines()
    parts = []
    for raw in lines:
        line = raw.strip()
        if not line:
            parts.append('<div class="rb-spacer"></div>')
            continue
        safe = html.escape(line)
        if line.startswith("### "):
            parts.append(f'<div class="rb-section-title">{html.escape(line[4:].strip())}</div>')
        else:
            extra = " rb-line-thread" if "/" in line[:4] else ""
            parts.append(f'<div class="rb-line{extra}">{safe}</div>')
    return "".join(parts)


def render_report_panel(kicker: str, title: str, body: str):
    st.markdown(
        f'<div class="report-box">'
        f'<div class="rb-kicker">{esc(kicker)}</div>'
        f'<div class="rb-title">{esc(title)}</div>'
        f'<div class="rb-body">{_format_report_body_html(body)}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


# ─── AI REPORT ───────────────────────────────────────────────────────────────

def _fallback_bulten_payload(data: dict, analytics: dict, terminal_report: str = "") -> dict:
    fallback = terminal_report or _fallback_terminal_report(data, {}, analytics)
    return {
        "terminal_report": fallback,
        "x_lead": _fallback_x_lead(data, analytics),
        "x_thread": _fallback_x_thread(data, analytics),
        "raw": str(terminal_report or "").strip(),
    }


def _normalize_bulten_result(result, data: dict, analytics: dict) -> dict:
    fb = _fallback_bulten_payload(data, analytics)
    if isinstance(result, dict):
        return {
            "terminal_report": str(result.get("terminal_report") or fb["terminal_report"]),
            "x_lead":   str(result.get("x_lead")   or fb["x_lead"]),
            "x_thread": str(result.get("x_thread") or fb["x_thread"]),
            "raw":      str(result.get("raw") or ""),
        }
    return _fallback_bulten_payload(data, analytics, terminal_report=str(result or ""))


def _call_strategy_report(client, data, brief, analytics, alerts, health_summary, report_depth):
    try:
        return generate_strategy_report(client, data, brief, analytics, alerts, health_summary, depth=report_depth)
    except TypeError:
        return generate_strategy_report(client, data, depth=report_depth)


def render_ai_report(client, data, brief, analytics, alerts, health_summary, report_depth):
    st.markdown(
        '<div class="s-kicker">Intelligence Desk · Makro Bülten</div>',
        unsafe_allow_html=True,
    )
    st.caption(f"Derinlik: {report_depth} · Veri, yorum ve kritik seviyelerle research-note formatında bülten üretilir.")

    if not client:
        st.info("OPENROUTER_API_KEY yok — AI raporu pasif.")
        return

    if st.button("Makro Bülten Oluştur", use_container_width=True):
        with st.spinner("AI raporu hazırlanıyor…"):
            try:
                report = _call_strategy_report(client, data, brief, analytics, alerts, health_summary, report_depth)
                st.session_state["macro_bulten_report"] = _normalize_bulten_result(report, data, analytics)
            except TypeError:
                st.session_state["macro_bulten_report"] = _fallback_bulten_payload(data, analytics)
                st.warning("AI servis sözleşmesi uyumsuz; fallback bülten gösteriliyor.")
            except (APIConnectionError, APITimeoutError, RateLimitError, APIError, ValueError) as exc:
                st.error(f"AI hatası: {exc}")
                return

    report = st.session_state.get("macro_bulten_report")
    if not report:
        st.info("Oluşturulduğunda Makro Bülten ve X paylaşım paketleri burada görünecek.")
        return

    render_report_panel("Macro Bulletin", "Makro Bülten", report.get("terminal_report", ""))
    st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
    lead_col, thread_col = st.columns([0.9, 1.1])
    with lead_col:
        render_report_panel("X Lead", "Tek Post Özet", report.get("x_lead", ""))
    with thread_col:
        render_report_panel("X Thread", "5 Maddelik Taslak", report.get("x_thread", ""))


# ─── TAB: TERMINAL (OVERVIEW) ─────────────────────────────────────────────────

def render_overview_tab(data, brief, analytics, alerts, health_summary):
    scores   = analytics["scores"]
    factors  = {f["key"]: f for f in scores["factors"]}
    part     = scores["participation"]
    m_bread  = part["subfactors"]["macro"]
    c_bread  = part["subfactors"]["crypto"]
    p_gap    = abs(m_bread["score"] - c_bread["score"])
    pos_band, pos_kind = build_positioning_emphasis(factors["positioning"], brief)
    ex_copy, ex_ctx, ex_badge, ex_kind = build_execution_bridge(scores, brief)

    # Hero zone: two columns — regime + command
    left, right = st.columns([1.15, 0.85])
    with left:
        render_score_panel(analytics)
    with right:
        render_command_surface(data, brief, analytics, alerts, health_summary)

    st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)

    # 4-deck strip
    d1, d2, d3, d4 = st.columns(4)
    with d1:
        f = factors["liquidity"]
        dt, _ = score_delta_meta(f["delta_7d"])
        render_signal_deck(
            "Liquidity Deck", brief["liquidity"]["title"], f["summary"],
            [("ETF Flow", data.get("ETF_FLOW_TOTAL","-")), ("DXY", data.get("DXY","-")), ("USDT.D", data.get("USDT_D","-"))],
            score_value=f"{f['score']}/100", score_label=f["confidence_label"],
            chips=[f["state"], f"Weight {f['weight_pct']}%", dt, f["primary_risk"]],
            context_rows=[("Driver", f["primary_support"]), ("Weakest", f["primary_risk"]), ("Confidence", f["confidence_label"])],
        )
    with d2:
        f = factors["positioning"]
        dt, _ = score_delta_meta(f["delta_7d"])
        render_signal_deck(
            "Positioning Deck", brief["positioning"]["title"], f["summary"],
            [("Funding", data.get("FR","-")), ("L/S", data.get("LS_Ratio","-")), ("Taker", data.get("Taker","-"))],
            score_value=f"{f['score']}/100", score_label=f["confidence_label"],
            chips=[f["state"], f"Weight {f['weight_pct']}%", dt, f["primary_risk"]],
            context_rows=[("Crowding", f["state"]), ("Driver", f["primary_support"]), ("Weakest", f["primary_risk"])],
            emphasis=pos_band, emphasis_kind=pos_kind,
        )
    with d3:
        f = factors["participation"]
        dt, _ = score_delta_meta(f["delta_7d"])
        render_signal_deck(
            "Participation Deck", "Cross-Asset Participation", f["summary"],
            [("Macro Breadth", f"{m_bread['score']}/100"), ("Crypto Breadth", f"{c_bread['score']}/100"), ("Gap", f"{p_gap} pts")],
            score_value=f"{f['score']}/100", score_label=f["confidence_label"],
            chips=[f["state"], f"Weight {f['weight_pct']}%", dt, f["primary_risk"]],
            context_rows=[("Macro Wt", "45%"), ("Crypto Wt", "55%"), ("Alignment", participation_alignment_label(m_bread["score"], c_bread["score"]))],
            emphasis="Composite skor macro ve crypto katılımın birlikte teyit verip vermediğini ölçer; gap büyüyse rejim daha kırılgan okunur.",
            emphasis_kind="warn" if p_gap > 12 else "ok",
        )
    with d4:
        render_signal_deck(
            "Execution Deck", brief["focus"]["title"], ex_copy,
            [("Support", data.get("Sup_Wall","-")), ("Resistance", data.get("Res_Wall","-")), ("Signal", data.get("ORDERBOOK_SIGNAL","-"))],
            score_value=display_value(data.get("BTC_P","-")),
            score_label=ex_badge,
            chips=[brief["regime"]["title"], brief["focus"]["badge"], brief["focus"]["class"].replace("signal-","")],
            context_rows=ex_ctx,
            emphasis=f"This regime: {brief['focus']['detail']}",
            emphasis_kind=ex_kind,
        )

    st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)

    # Breadth strip
    b_left, b_right = st.columns(2)
    with b_left:
        render_breadth_surface(
            "Macro Breadth", m_bread,
            [("RSP vs SPY", f"{display_value(data.get('RSP_C'))} vs {display_value(data.get('SPY_C'))}"),
             ("IWM vs SPY", f"{display_value(data.get('IWM_C'))} vs {display_value(data.get('SPY_C'))}"),
             ("Sectors", "XLK · XLF · XLI · XLE · XLY")],
            kicker="Participation Layer",
            note="Macro breadth genel risk katılımının mega-cap dışına, small-cap ve sektör ETF'lere yayılıp yayılmadığını ölçer.",
        )
    with b_right:
        render_breadth_surface(
            "Crypto Breadth", c_bread,
            [("TOTAL2", data.get("TOTAL2_CAP","-")), ("TOTAL3", data.get("TOTAL3_CAP","-")),
             ("OTHERS / BTC Dom", f"{display_value(data.get('OTHERS_CAP'))} · {display_value(data.get('Dom'))}")],
            kicker="Participation Layer",
            note="Crypto breadth BTC dışı katılım, alt katman yayılımı ve dominance konsantrasyonunu birlikte okur.",
        )

    st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)

    # Scenario + catalyst
    s_left, s_right = st.columns([1.1, 0.9])
    with s_left:
        render_scenario_matrix(analytics)
    with s_right:
        render_catalyst_stream(data, analytics, alerts, health_summary)


# ─── TAB: MACRO ──────────────────────────────────────────────────────────────

def render_macro_tab(data: dict):
    st.markdown(
        '<div class="s-kicker">Macro Intelligence</div>'
        '<div class="s-title">Makro & Piyasalar</div>'
        '<div class="s-subtitle">Makro risk context ve cross-asset okuyuşu. Terminal özetini tekrar etmez; hammaddeyi taşır.</div>',
        unsafe_allow_html=True,
    )
    st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)

    st.markdown('<div style="font-size:0.72rem;font-family:var(--font-mono);letter-spacing:0.12em;text-transform:uppercase;color:var(--text-muted);margin-bottom:8px">Risk Core</div>', unsafe_allow_html=True)
    render_table_row(data, [section_variant(MACRO_MARKET_SECTIONS[0]), section_variant(MACRO_MARKET_SECTIONS[2]), section_variant(MACRO_MARKET_SECTIONS[7])], 3, include_change=True)
    st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)

    st.markdown('<div style="font-size:0.72rem;font-family:var(--font-mono);letter-spacing:0.12em;text-transform:uppercase;color:var(--text-muted);margin-bottom:8px">Cross-Asset & Commodities</div>', unsafe_allow_html=True)
    render_table_row(data, [section_variant(MACRO_MARKET_SECTIONS[1]), section_variant(MACRO_MARKET_SECTIONS[3]), section_variant(MACRO_MARKET_SECTIONS[4])], 3, include_change=True)
    st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)

    st.markdown('<div style="font-size:0.72rem;font-family:var(--font-mono);letter-spacing:0.12em;text-transform:uppercase;color:var(--text-muted);margin-bottom:8px">FX & Local Context</div>', unsafe_allow_html=True)
    render_table_row(data, [section_variant(MACRO_MARKET_SECTIONS[5]), section_variant(MACRO_MARKET_SECTIONS[6])], 2, include_change=True)


# ─── TAB: CRYPTO ─────────────────────────────────────────────────────────────

def render_crypto_tab(data: dict):
    st.markdown(
        '<div class="s-kicker">Crypto Intelligence</div>'
        '<div class="s-title">Kripto Radar</div>'
        '<div class="s-subtitle">Fiyat akisi, 7 gunluk relatif performans ve BTC bazli guc/zayiflik okumasi.</div>',
        unsafe_allow_html=True,
    )
    st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)

    price_cards = [
        (f"{name} ({symbol})", data.get(pk, "-"), data.get(ck, "-"))
        for name, symbol, pk, ck, _ in CRYPTO_RADAR_ASSETS
    ]
    btc_week = data.get("BTC_7D", "-")
    weekly_cards = [
        (f"{symbol} · 24h {display_value(data.get(ck,'-'))}", data.get(wk, "-"), relative_to_btc_tone(data.get(wk), btc_week))
        for _, symbol, _, ck, wk in CRYPTO_RADAR_ASSETS
    ]

    cat("Price Snapshot", "●")
    render_cards(price_cards, cols=4, compact=True)
    st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
    cat("Relative Performance vs BTC", "◨")
    render_compact_metric_strip(weekly_cards, cols=3)


# ─── TAB: FLOW ───────────────────────────────────────────────────────────────

def render_flow_risk_tab(data: dict, health_summary: dict):
    st.markdown(
        '<div class="s-kicker">Flow & Risk Surfaces</div>'
        '<div class="s-title">Akış & Risk Katmanları</div>'
        '<div class="s-subtitle">Terminal özetini tekrar etmez; sinyalin hammaddesini ve takibini taşır.</div>',
        unsafe_allow_html=True,
    )
    scores   = build_analytics_payload(data)["scores"]
    factors  = {f["key"]: f for f in scores["factors"]}
    part     = scores["participation"]
    m_bread  = part["subfactors"]["macro"]
    c_bread  = part["subfactors"]["crypto"]

    summary_cards = [
        ("Positioning", f"{factors['positioning']['score']}/100", factors["positioning"]["state"]),
        ("Liquidity",   f"{factors['liquidity']['score']}/100",   factors["liquidity"]["primary_support"]),
        ("Participation",f"{part['score']}/100",                  participation_alignment_label(m_bread["score"], c_bread["score"])),
        ("Execution",   display_value(data.get("BTC_P","-")),     display_value(data.get("ORDERBOOK_SIGNAL","-"))),
    ]
    render_cards(summary_cards, cols=4, compact=True)
    st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)

    with st.expander("Derivatives & Sentiment", expanded=True):
        render_table_row(data, [section_variant(FLOW_RISK_SECTIONS[0]), section_variant(FLOW_RISK_SECTIONS[1])], 2)
    with st.expander("Liquidity Plumbing", expanded=False):
        render_table_row(data, [section_variant(FLOW_RISK_SECTIONS[2])], 1)
    with st.expander("Breadth Inputs & Rotation", expanded=False):
        render_table_row(data, [section_variant(FLOW_RISK_SECTIONS[3]), section_variant(FLOW_RISK_SECTIONS[4])], 2)


# ─── TAB: AGGR ───────────────────────────────────────────────────────────────

def render_aggr_tab():
    st.markdown(
        '<div class="s-kicker">Live Orderflow</div>'
        '<div class="s-title">AGGR · Canlı Tape</div>'
        '<div class="s-subtitle">Terminal içine gömülü panel değil, AGGR yüzeyine temiz bir geçit.</div>',
        unsafe_allow_html=True,
    )
    st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)

    left, right = st.columns([0.3, 0.7])
    with left:
        st.link_button("AGGR'ı Yeni Sekmede Aç", AGGR_PANEL_URL, use_container_width=True)
    with right:
        st.markdown(
            '<div class="surface surface-sm">'
            '<div class="s-kicker">Neden harici açılıyor?</div>'
            '<div class="s-subtitle">AGGR kendi güvenlik politikasıyla iframe açılışını reddediyor. En temiz deneyim, boş panel yerine doğrudan dış aracı açmak.</div>'
            '</div>',
            unsafe_allow_html=True,
        )


# ─── TAB: REPORTS ────────────────────────────────────────────────────────────

def _render_cached_report_panel(cached: dict) -> None:
    """Diskten okunan bir raporu ekrana basar."""
    rep     = cached.get("report", {})
    market  = cached.get("market", {})
    regime  = cached.get("regime", {})
    ts      = cached.get("timestamp", "")
    slot    = cached.get("time_label", "-")

    # Üst bilgi şeridi
    st.markdown(
        f'<div class="section-notice">'
        f'Slot <strong>{esc(slot)}</strong> · '
        f'Uretilme: <strong>{esc(ts[:16].replace("T", " "))}</strong> · '
        f'Rejim: <strong>{esc(regime.get("overlay", "-"))}</strong> '
        f'({esc(regime.get("score", "-"))}/100) · '
        f'BTC: <strong>{esc(market.get("btc_price", "-"))}</strong> '
        f'{esc(market.get("btc_change", ""))}'
        f'</div>',
        unsafe_allow_html=True,
    )

    terminal_report = rep.get("terminal_report", "")
    x_lead          = rep.get("x_lead", "")
    x_thread        = rep.get("x_thread", "")

    if terminal_report:
        render_report_panel("Macro Bulletin", "Makro Bulten", terminal_report)
    else:
        st.info("Bu slot icin rapor icerigi bulunamadi.")
        return

    if x_lead or x_thread:
        st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
        lc, tc = st.columns([0.9, 1.1])
        with lc:
            if x_lead:
                render_report_panel("X Lead", "Tek Post Ozet", x_lead)
        with tc:
            if x_thread:
                render_report_panel("X Thread", "5 Maddelik Taslak", x_thread)


def render_report_tab(client, data, brief, analytics, alerts, health_summary, report_depth):
    from notify import load_latest_report, list_archive_reports

    st.markdown(
        '<div class="s-kicker">Intelligence Desk</div>'
        '<div class="s-title">Raporlar & Kataliz\u00f6rler</div>'
        '<div class="s-subtitle">Sabah ve aksam bulten slotlari. Arşiv altta.</div>',
        unsafe_allow_html=True,
    )
    st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)

    # ── Slot toggle ──────────────────────────────────────────────────────────
    slot_col, right_col = st.columns([0.5, 0.5])
    with slot_col:
        slot_choice = st.radio(
            "Bulten slotu",
            options=["16:30 Bulteni", "22:45 Bulteni"],
            index=1,
            horizontal=True,
            label_visibility="collapsed",
        )
    slot_key = "1630" if slot_choice == "16:30 Bulteni" else "2245"

    # ── Cached rapor yoksa AI raporu, varsa diskten oku ─────────────────────
    cached = load_latest_report(slot_key)

    main_left, main_right = st.columns([1.35, 0.65])
    with main_left:
        if cached:
            _render_cached_report_panel(cached)
            st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
            with st.expander("Manuel yenile (AI ile yeniden uret)", expanded=False):
                render_ai_report(client, data, brief, analytics, alerts, health_summary, report_depth)
        else:
            st.markdown(
                '<div class="section-notice">'
                'Bu slot icin henuz hazir rapor yok. '
                'GitHub Actions ilk calistirdiginda otomatik olusacak. '
                'Su an manuel uretebilirsin.'
                '</div>',
                unsafe_allow_html=True,
            )
            render_ai_report(client, data, brief, analytics, alerts, health_summary, report_depth)

    with main_right:
        render_catalyst_stream(data, analytics, alerts, health_summary)
        st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
        render_scenario_matrix(analytics)

    # ── Export ───────────────────────────────────────────────────────────────
    st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
    render_downloads(data, brief, analytics, alerts, health_summary)

    # ── Gecmis Raporlar ──────────────────────────────────────────────────────
    st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)
    st.markdown(
        '<div class="s-kicker">Arsiv</div>'
        '<div class="s-title" style="font-size:1.05rem">Gecmis Raporlar</div>'
        '<div class="s-subtitle">Sadece 22:45 bultenleri arsivlenir. Tarih secip icerige ulasabilirsin.</div>',
        unsafe_allow_html=True,
    )

    archive = list_archive_reports()
    if not archive:
        st.info("Arsiv henuz bos. Ilk 22:45 bulteni GitHub Actions tarafindan olusturuldugunda burada gorunecek.")
    else:
        date_options = [
            f"{r['date']}  |  BTC {r['market'].get('btc_price', '-')}  |  {r['regime'].get('overlay', '-')}"
            for r in archive
        ]
        selected_idx = st.selectbox(
            "Tarih sec",
            options=range(len(date_options)),
            format_func=lambda i: date_options[i],
            label_visibility="collapsed",
        )
        selected = archive[selected_idx]
        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
        _render_cached_report_panel(selected)

    # ── Market Tools ─────────────────────────────────────────────────────────
    st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
    with st.expander("Market Tools", expanded=False):
        tool_tabs = st.tabs(["BTC Chart", "Economic Calendar"])
        with tool_tabs[0]:
            components.html(
                '<div style="height:420px">'
                '<div id="tv_mc" style="height:100%"></div>'
                '<script src="https://s3.tradingview.com/tv.js"></script>'
                '<script>new TradingView.widget({autosize:true,symbol:"BINANCE:BTCUSDT",interval:"D",'
                'theme:"dark",style:"1",locale:"tr",toolbar_bg:"#050d18",container_id:"tv_mc"});</script>'
                '</div>',
                height=440,
            )
        with tool_tabs[1]:
            components.html(
                '<div class="tradingview-widget-container">'
                '<div class="tradingview-widget-container__widget"></div>'
                '<script src="https://s3.tradingview.com/external-embedding/embed-widget-events.js" async>'
                '{"colorTheme":"dark","isTransparent":true,"width":"100%","height":"400","locale":"tr",'
                '"importanceFilter":"0,1","currencyFilter":"USD,EUR"}</script></div>',
                height=420,
            )

    with st.expander("News & Catalysts", expanded=False):
        news = data.get("NEWS", [])
        if news:
            for item in news[:6]:
                st.markdown(
                    f'<div class="news-card">'
                    f'<a href="{html.escape(str(item["url"]))}" target="_blank">{html.escape(str(item["title"]))}</a>'
                    f'<div class="news-meta">{html.escape(str(item["time"]))} · {html.escape(str(item["source"]))}</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
        else:
            st.info("Haber akisi su an yok.")


# ─── TAB: ATLAS ──────────────────────────────────────────────────────────────

def render_all_metrics_tab(data: dict):
    st.markdown(
        '<div class="s-kicker">Deep Reference Layer</div>'
        '<div class="s-title">Atlas · Tüm Metrikler</div>'
        '<div class="s-subtitle">Ham veri referansı. Gruplu ve arama odaklı çalışır — her şey aynı anda açılmaz.</div>',
        unsafe_allow_html=True,
    )
    st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)

    with st.expander("Core Market & Derivatives", expanded=True):
        render_table_row(data, DATA_ATLAS_SECTIONS[:3], 3)
    with st.expander("Participation & Liquidity", expanded=False):
        render_table_row(data, [DATA_ATLAS_SECTIONS[3], DATA_ATLAS_SECTIONS[4], DATA_ATLAS_SECTIONS[7]], 3)
    with st.expander("Macro, Commodities & FX", expanded=False):
        render_table_row(data, [DATA_ATLAS_SECTIONS[5], DATA_ATLAS_SECTIONS[6], DATA_ATLAS_SECTIONS[8]], 3)


# ─── MAIN ─────────────────────────────────────────────────────────────────────

init_preferences()
init_ui_state()
preferences = st.session_state["preferences"]
client      = build_openrouter_client(OPENROUTER_API_KEY) if OPENROUTER_API_KEY else None
last_updated = pd.Timestamp.now(tz="Europe/Istanbul").strftime("%d.%m.%Y %H:%M:%S")

with st.spinner("Piyasa verileri yükleniyor…"):
    data = load_terminal_data(FRED_API_KEY)
    current_health = merge_source_health(st.session_state.get("source_health"), data.pop("_health", {}))
    data["_health"] = current_health
    st.session_state["source_health"] = current_health

health_summary = build_health_summary(data.get("_health", {}))
brief          = build_market_brief(data)
analytics      = build_analytics_payload(data)
alerts         = build_alerts(data, preferences.get("thresholds", {}))

render_page_header(last_updated, health_summary, brief, preferences, analytics)
render_status_hub(last_updated, health_summary, alerts, analytics)
render_sidebar(data, brief, last_updated, health_summary, preferences, alerts)
render_control_rail(data, brief, last_updated, health_summary, alerts)

tabs = st.tabs(["Terminal", "Macro", "Crypto", "Flow", "AGGR", "Reports", "Atlas"])
with tabs[0]: render_overview_tab(data, brief, analytics, alerts, health_summary)
with tabs[1]: render_macro_tab(data)
with tabs[2]: render_crypto_tab(data)
with tabs[3]: render_flow_risk_tab(data, health_summary)
with tabs[4]: render_aggr_tab()
with tabs[5]: render_report_tab(client, data, brief, analytics, alerts, health_summary, preferences.get("report_depth", "Orta"))
with tabs[6]: render_all_metrics_tab(data)
