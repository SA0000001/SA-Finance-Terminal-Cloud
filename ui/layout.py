"""
SA Finance Alpha Terminal — Layout Module
Page header, Status Hub, sidebar. No business logic here.
"""
import html as _html

import pandas as pd
import streamlit as st

from services.health import normalize_health_display_text
from ui.components import bi_label, clean_text, display_value, esc, render_health_bar


def normalize_health_cell(value) -> str:
    return clean_text(normalize_health_display_text(value))


# ─── PAGE HEADER ─────────────────────────────────────────────────────────────

def render_page_header(last_updated: str, health_summary: dict, brief: dict, preferences: dict, analytics: dict):
    scores = analytics["scores"]

    chips_html = "".join(
        f'<div class="t-chip">'
        f'<span class="t-chip-label">{esc(label)}</span>'
        f'<span class="t-chip-value">{esc(value)}</span>'
        f'</div>'
        for label, value in [
            (bi_label("Market State", "Piyasa Durumu"), scores["overlay"]),
            (bi_label("Regime Score", "Rejim Skoru"),   f"{scores['overall']}/100"),
            (bi_label("Fragility",    "Kirilganlik"),   scores["fragility"]["label"]),
            (bi_label("Confidence",   "Guven"),         f"{scores['confidence']}/100 · {scores['confidence_label']}"),
        ]
    )

    st.markdown(
        f'''
        <div class="t-header">
            <div class="t-header-left">
                <div class="t-kicker">Digital Asset Intelligence</div>
                <div class="t-wordmark">SA Finance Alpha Terminal</div>
                <div class="t-tagline">
                    Makro rejim, risk akis ve alpha teyitlerini tek karar akisina indirger.
                    Rejim merkezi, katmanlar detay.
                </div>
                <div class="t-state-chips">{chips_html}</div>
            </div>
            <div class="t-header-right">
                <div class="t-pill-row">
                    <span class="t-pill">Canli veri</span>
                    <span class="t-pill">Mod · {esc(preferences.get("view_mode", "Basit"))}</span>
                    <span class="t-badge">v20.0</span>
                </div>
                <div class="t-meta">
                    Istanbul · {esc(last_updated)}<br/>
                    Bias · {esc(scores["bias"])}
                </div>
            </div>
        </div>
        ''',
        unsafe_allow_html=True,
    )
    render_health_bar(health_summary)
    st.markdown(
        "<div class='section-notice'>Rejim merkezi → sekme detayları → atlas. Üst yüzey karar verir, alt yüzeyler teyit eder.</div>",
        unsafe_allow_html=True,
    )


# ─── STATUS HUB ──────────────────────────────────────────────────────────────

def render_status_hub(last_updated: str, health_summary: dict, alerts: list[dict], analytics: dict):
    issue_rows  = [r for r in health_summary.get("rows", []) if r.get("Durum") != "OK"]
    scores      = analytics["scores"]
    issue_count = len(issue_rows)
    alert_count = len(alerts)

    summary_copy = (
        f"{issue_count} kaynak dikkat istiyor — detaylar aşağıda."
        if issue_count
        else "Kritik veri sorunu yok. Health detayı gerektiğinde açılır."
    )

    stats_html = "".join(
        f'<div class="sh-stat">'
        f'<span class="sh-stat-label">{esc(label)}</span>'
        f'<span class="sh-stat-value">{esc(value)}</span>'
        f'</div>'
        for label, value in [
            ("Updated",    last_updated),
            ("Alerts",     str(alert_count)),
            ("Issues",     str(issue_count)),
            ("Confidence", f"{scores['confidence']}/100"),
        ]
    )

    st.markdown(
        f'''
        <div class="status-hub">
            <div class="sh-left">
                <div class="sh-title">Operasyon Merkezi</div>
                <div class="sh-copy">{esc(summary_copy)}</div>
            </div>
            <div class="sh-stats">{stats_html}</div>
        </div>
        ''',
        unsafe_allow_html=True,
    )

    if issue_rows:
        with st.expander("Source health details", expanded=False):
            for row in issue_rows[:6]:
                source       = normalize_health_cell(row.get("Kaynak"))
                error        = normalize_health_cell(row.get("Hata"))
                status       = normalize_health_cell(row.get("Durum"))
                last_success = normalize_health_cell(row.get("Son basarili"))
                left, right  = st.columns([5, 1.2], vertical_alignment="top")
                with left:
                    st.markdown(
                        f"<div style='font-weight:600;font-size:0.86rem'>{_html.escape(source)}</div>"
                        f"<div style='color:var(--text-muted);font-size:0.8rem;margin-top:3px'>{_html.escape(error)}</div>",
                        unsafe_allow_html=True,
                    )
                with right:
                    cls = status.lower()
                    st.markdown(
                        f"<div style='text-align:right'>"
                        f"<span class='h-pill h-{cls}' style='font-size:0.64rem'>{_html.escape(status)}</span><br/>"
                        f"<span style='color:var(--text-muted);font-size:0.72rem'>{_html.escape(last_success)}</span>"
                        f"</div>",
                        unsafe_allow_html=True,
                    )
                st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)


def render_health_panel(health_summary: dict):
    rows = health_summary.get("rows", [])
    if not rows:
        st.info("Veri sağlığı bilgisi henüz oluşmadı.")
        return
    c1, c2, c3 = st.columns(3)
    c1.metric("Sağlıklı",   health_summary.get("healthy_sources", 0))
    c2.metric("Başarısız",  len(health_summary.get("failed_sources", [])))
    c3.metric("Stale",      len(health_summary.get("stale_sources", [])))
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


# ─── SIDEBAR ─────────────────────────────────────────────────────────────────

def render_sidebar(data, brief, last_updated: str, health_summary: dict, preferences: dict, alerts: list[dict]):
    with st.sidebar:
        st.markdown(
            '<div class="s-kicker" style="margin-bottom:6px">SA Finance Terminal</div>'
            '<div style="font-size:0.92rem;font-weight:700;color:var(--text-primary);margin-bottom:4px">Control Rail</div>'
            f'<div style="font-size:0.74rem;color:var(--text-muted);margin-bottom:14px">{esc(last_updated)}</div>',
            unsafe_allow_html=True,
        )
        st.divider()

        if st.button("Verileri Yenile", key="sidebar_refresh", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

        export_df = pd.DataFrame(
            [(k, v) for k, v in data.items() if k not in {"NEWS", "_health"}],
            columns=["Metrik", "Deger"],
        )
        st.download_button(
            "CSV İndir",
            export_df.to_csv(index=False, sep=";").encode("utf-8-sig"),
            file_name=f"AlphaTerminal_{pd.Timestamp.now().strftime('%Y%m%d_%H%M')}.csv",
            mime="text/csv",
            key="sidebar_csv_download",
            use_container_width=True,
        )

        st.divider()
        st.markdown(
            '<div class="sidebar-note">'
            'Sidebar yalnızca operasyon için ayrıldı: yenileme, dışa aktarma, sistem bilgisi. '
            'Health ve canlı durum detayları ana yüzeydeki Status Hub\'a taşındı.'
            '</div>',
            unsafe_allow_html=True,
        )
        st.divider()
        st.markdown(
            """**Veri Kaynakları**
`Coinpaprika` · `Kraken` · `OKX` · `KuCoin` · `Gate.io` · `Coinbase`
`DeFiLlama` · `yFinance` · `TradingView` · `FRED` · `CoinDesk`

**Model**
`Gemini 2.5 Flash`""",
        )
