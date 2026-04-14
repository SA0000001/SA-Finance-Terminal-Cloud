"""
SA Finance Alpha Terminal — Layout Module
Page header, Status Hub, sidebar. No business logic here.
"""
import html as _html
import re

import pandas as pd
import streamlit as st

from domain.analytics import DEFAULT_PINNED_METRICS, METRIC_LABELS
from services.health import normalize_health_display_text
from services.preferences import save_preferences
from ui.components import bi_label, clean_text, display_value, esc, render_health_bar


def normalize_health_cell(value) -> str:
    return clean_text(normalize_health_display_text(value))


# ─── KULLANICI DOSTU HATA MESAJLARI ──────────────────────────────────────────

_ERROR_PATTERNS: list[tuple[str, str]] = [
    (r"HTTP 4(0[13]|29)",   "Veri kaynağı erişim reddetti — yakında otomatik yeniden denenecek."),
    (r"HTTP 404",           "Veri kaynağı adresi değişmiş olabilir — geçici olarak atlanıyor."),
    (r"HTTP 5\d\d",         "Veri kaynağı sunucu tarafında hata verdi — genellikle kısa sürede düzelir."),
    (r"timeout|Timeout|timed out", "Veri kaynağına bağlanılamadı (zaman aşımı) — otomatik yeniden denenecek."),
    (r"Connection|connection refused", "Veri kaynağına bağlantı kurulamadı — internet bağlantısını kontrol et."),
    (r"JSONDecodeError|json|JSON",     "Veri kaynağından beklenmedik yanıt geldi — geçici olarak atlanıyor."),
    (r"KeyError|IndexError|TypeError", "Veri formatı değişmiş olabilir — kaynak güncelleniyor."),
    (r"Rate limit|rate limit|429",     "Veri kaynağı sorgu limitine ulaşıldı — biraz bekle, otomatik devam edecek."),
    (r"SSL|ssl|certificate",           "Güvenli bağlantı hatası — veri kaynağı geçici olarak erişilemez."),
    (r"No data|empty|boş",             "Bu kaynaktan şu an veri gelmiyor — bir sonraki güncellemeye kadar bekleniyor."),
]
_ERROR_FALLBACK = "Veri kaynağında geçici bir sorun var — otomatik olarak yeniden denenecek."


def friendly_error(raw: str) -> str:
    """Teknik hata metnini kullanıcı dostu Türkçeye çevirir."""
    if not raw or raw in ("-", ""):
        return _ERROR_FALLBACK
    for pattern, message in _ERROR_PATTERNS:
        if re.search(pattern, raw, re.IGNORECASE):
            return message
    return _ERROR_FALLBACK


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
        with st.expander(f"Veri kaynağı sorunları ({issue_count})", expanded=False):
            for row in issue_rows[:6]:
                source       = normalize_health_cell(row.get("Kaynak"))
                raw_error    = normalize_health_cell(row.get("Hata"))
                error        = friendly_error(raw_error)
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

def _render_sidebar_preferences():
    """Sidebar'da kalıcı Görünüm ve Uyarılar paneli."""
    prefs = st.session_state.get("preferences", {})
    thresholds = prefs.get("thresholds", {})

    with st.expander("Görünüm ve Uyarılar", expanded=False):
        view_mode = st.radio(
            "Görünüm modu",
            ["Basit", "Pro"],
            index=0 if prefs.get("view_mode") == "Basit" else 1,
            key="sidebar_pref_view_mode",
        )
        report_depth = st.selectbox(
            "Rapor seviyesi",
            ["Kısa", "Orta", "Derin"],
            index=["Kısa", "Orta", "Derin"].index(prefs.get("report_depth", "Orta")),
            key="sidebar_pref_report_depth",
        )
        pinned_metrics = st.multiselect(
            "Pinli metrikler",
            options=list(METRIC_LABELS),
            default=prefs.get("pinned_metrics", DEFAULT_PINNED_METRICS),
            format_func=lambda key: METRIC_LABELS.get(key, key),
            key="sidebar_pref_pinned",
        )
        st.markdown(
            "<div style='font-size:0.72rem;color:var(--text-muted);margin:8px 0 4px;"
            "font-family:var(--font-mono);letter-spacing:0.1em;text-transform:uppercase'>Alarm eşikleri</div>",
            unsafe_allow_html=True,
        )
        funding_above = st.number_input("Funding > X",     value=float(thresholds.get("funding_above", 0.01)), step=0.005, format="%.4f", key="sidebar_thr_funding")
        vix_above     = st.number_input("VIX > Y",         value=float(thresholds.get("vix_above", 25.0)),     step=0.5,   format="%.2f", key="sidebar_thr_vix")
        etf_flow      = st.number_input("ETF netflow < Z", value=float(thresholds.get("etf_flow_below", 0.0)), step=10.0,  format="%.1f", key="sidebar_thr_etf")
        dxy_above     = st.number_input("DXY > W",         value=float(thresholds.get("dxy_above", 105.0)),    step=0.5,   format="%.2f", key="sidebar_thr_dxy")

        if st.button("Ayarları Kaydet", key="sidebar_pref_save", use_container_width=True):
            prefs["view_mode"]      = view_mode
            prefs["report_depth"]   = report_depth
            prefs["pinned_metrics"] = pinned_metrics[:8]
            prefs["thresholds"] = {
                "funding_above":  funding_above,
                "vix_above":      vix_above,
                "etf_flow_below": etf_flow,
                "dxy_above":      dxy_above,
            }
            save_preferences(prefs)
            st.session_state["preferences"] = prefs
            st.success("Ayarlar kaydedildi.")


def render_sidebar(data, brief, last_updated: str, health_summary: dict, preferences: dict, alerts: list[dict], analytics: dict | None = None):
    with st.sidebar:
        # ── Başlık + zaman ────────────────────────────────────────────────────
        st.markdown(
            '<div class="s-kicker" style="margin-bottom:4px">SA Finance Terminal</div>'
            f'<div style="font-size:0.74rem;color:var(--text-muted);margin-bottom:4px">{esc(last_updated)}</div>',
            unsafe_allow_html=True,
        )

        # ── Operasyon butonları ───────────────────────────────────────────────
        b1, b2 = st.columns(2)
        with b1:
            if st.button("Verileri Yenile", key="sidebar_refresh", use_container_width=True):
                st.cache_data.clear()
                st.rerun()
        with b2:
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

        # ── Operasyon Merkezi (status hub) ────────────────────────────────────
        scores      = (analytics or {}).get("scores", {})
        confidence  = scores.get("confidence", "-") if scores else "-"
        issue_rows  = [r for r in health_summary.get("rows", []) if r.get("Durum") != "OK"]
        issue_count = len(issue_rows)
        alert_count = len(alerts)

        st.markdown(
            f'<div style="font-size:0.78rem;font-weight:600;color:var(--text-primary);margin-bottom:4px">Operasyon Merkezi</div>'
            f'<div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:6px">'
            f'<span style="font-size:0.7rem;color:var(--text-muted)">Alarmlar <strong style="color:var(--text-primary)">{alert_count}</strong></span>'
            f'<span style="font-size:0.7rem;color:var(--text-muted)">Sorunlar <strong style="color:{"var(--negative)" if issue_count else "var(--positive)"}">{issue_count}</strong></span>'
            f'<span style="font-size:0.7rem;color:var(--text-muted)">Güven <strong style="color:var(--text-primary)">{confidence}/100</strong></span>'
            f'</div>',
            unsafe_allow_html=True,
        )

        if issue_rows:
            with st.expander(f"Veri kaynağı sorunları ({issue_count})", expanded=False):
                for row in issue_rows[:6]:
                    source    = normalize_health_cell(row.get("Kaynak"))
                    raw_error = normalize_health_cell(row.get("Hata"))
                    error     = friendly_error(raw_error)
                    st.markdown(
                        f"<div style='font-size:0.78rem;font-weight:600;margin-bottom:1px'>{_html.escape(source)}</div>"
                        f"<div style='font-size:0.72rem;color:var(--text-muted);margin-bottom:6px'>{_html.escape(error)}</div>",
                        unsafe_allow_html=True,
                    )
        else:
            st.markdown(
                '<div style="font-size:0.72rem;color:var(--text-muted);margin-bottom:4px">Veri sorunu yok.</div>',
                unsafe_allow_html=True,
            )

        st.divider()

        # ── AGGR linki ────────────────────────────────────────────────────────
        st.link_button(
            "⬡ AGGR · Canlı Orderflow",
            "https://aggr.trade/brutalbtc-copy-1",
            use_container_width=True,
        )

        st.divider()

        # ── Görünüm ve Uyarılar ───────────────────────────────────────────────
        _render_sidebar_preferences()

        st.divider()
        st.markdown(
            """**Veri Kaynakları**
`Coinpaprika` · `Kraken` · `OKX` · `KuCoin` · `Gate.io` · `Coinbase`
`DeFiLlama` · `yFinance` · `TradingView` · `FRED` · `CoinDesk`

**Model**
`Gemini 2.5 Flash`""",
        )
