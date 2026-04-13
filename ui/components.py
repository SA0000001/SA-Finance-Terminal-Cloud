"""
SA Finance Alpha Terminal — Component System
Reusable, typed render functions.  No CSS here — CSS lives in ui/theme.py.
"""
import html as _html

import streamlit as st

PLACEHOLDER = "-"
REPLACEMENTS = {
    "\u00e2\u0080\u0093": "-",
    "\u00c2\u00b7": " | ",
    "\u25b2": "+",
    "\u25bc": "-",
}


# ─── UTILITIES ───────────────────────────────────────────────────────────────

def clean_text(value) -> str:
    if value is None:
        return PLACEHOLDER
    text = str(value)
    for src, tgt in REPLACEMENTS.items():
        text = text.replace(src, tgt)
    return text


def bi_label(english: str, turkish: str = "") -> str:
    e = clean_text(english)
    t = clean_text(turkish)
    return f"{e} ({t})" if t and t != PLACEHOLDER else e


def is_missing(value) -> bool:
    return clean_text(value).strip() in {PLACEHOLDER, "", "None"}


def display_value(value, fallback: str = "—") -> str:
    return fallback if is_missing(value) else clean_text(value)


def esc(value) -> str:
    return _html.escape(clean_text(value))


def delta_css(delta: str) -> str:
    cleaned = clean_text(delta).strip()
    if cleaned in {PLACEHOLDER, "", "None"}:
        return "dc-neu"
    try:
        raw = float(cleaned.replace("%", "").replace(",", ".").strip())
    except ValueError:
        return "dc-neu"
    return "dc-pos" if raw > 0 else "dc-neg" if raw < 0 else "dc-neu"


# ─── METRIC CARD ─────────────────────────────────────────────────────────────

def metric_card_html(label: str, value: str, delta: str = "", compact: bool = False) -> str:
    missing = is_missing(value)
    val_text = display_value(value)
    val_class = "mc-value mc-value-missing" if missing else "mc-value"

    if delta and delta not in (PLACEHOLDER, ""):
        try:
            raw = float(clean_text(delta).replace("%", "").replace(",", ".").strip())
            arrow = "+" if raw >= 0 else ""
            cls = "mc-delta-pos" if raw >= 0 else "mc-delta-neg"
            delta_html = f'<div class="{cls}">{arrow}{esc(delta)}</div>'
        except ValueError:
            delta_html = f'<div class="mc-delta-neu">{esc(delta)}</div>'
    else:
        delta_html = ""

    return (
        f'<div class="metric-card">'
        f'<div class="mc-label">{esc(label)}</div>'
        f'<div class="{val_class}">{esc(val_text)}</div>'
        f'{delta_html}'
        f'</div>'
    )


def render_cards(items, cols: int = 4, compact: bool = False):
    columns = st.columns(cols)
    for i, item in enumerate(items):
        label = item[0]
        value = item[1] if len(item) > 1 else PLACEHOLDER
        delta = item[2] if len(item) > 2 else ""
        with columns[i % cols]:
            st.markdown(metric_card_html(label, value, delta, compact), unsafe_allow_html=True)


# ─── COMPACT STRIP ───────────────────────────────────────────────────────────

def render_compact_metric_strip(items, cols: int = 5):
    columns = st.columns(cols)
    for i, item in enumerate(items):
        label = item[0]
        value = item[1] if len(item) > 1 else PLACEHOLDER
        tone  = item[2] if len(item) > 2 else ""
        with columns[i % cols]:
            st.markdown(
                f'<div class="compact-strip">'
                f'<div class="cs-strip-label">{esc(label)}</div>'
                f'<div class="cs-strip-value">{esc(display_value(value))}</div>'
                f'<div class="cs-strip-tone">{esc(tone) if tone else "&nbsp;"}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )


# ─── SECTION HEADING ─────────────────────────────────────────────────────────

def cat(title: str, icon: str = ""):
    prefix = f"{esc(icon)}&nbsp;" if icon else ""
    st.markdown(f'<div class="s-kicker">{prefix}{esc(title)}</div>', unsafe_allow_html=True)


# ─── INFO PANEL ──────────────────────────────────────────────────────────────

def render_info_panel(kicker: str, title: str, rows, badge_text: str = "", badge_kind: str = "sig-neutral", copy: str = ""):
    rows_html = "".join(
        f"<div class='panel-row'><span>{esc(label)}</span><strong>{esc(display_value(val))}</strong></div>"
        for label, val in rows
    )
    copy_html  = f"<div class='s-subtitle' style='margin-top:8px'>{esc(display_value(copy))}</div>" if copy else ""
    badge_html = f"<div style='margin-top:14px'><span class='{badge_kind}'>{esc(badge_text)}</span></div>" if badge_text else ""
    st.markdown(
        f'<div class="surface surface-sm">'
        f'<div class="s-kicker">{esc(kicker)}</div>'
        f'<div class="s-title" style="font-size:1.05rem">{esc(title)}</div>'
        f'{copy_html}'
        f'<div style="margin-top:10px">{rows_html}</div>'
        f'{badge_html}'
        f'</div>',
        unsafe_allow_html=True,
    )


# ─── MARKET BRIEF CARDS ──────────────────────────────────────────────────────

def render_market_brief(brief):
    cols = st.columns(2)
    for col, card in zip(cols * 2, brief.values()):
        why_html = "".join(
            f"<div style='padding-top:7px;border-top:1px solid rgba(100,140,185,0.1);font-size:0.8rem;color:var(--text-muted);line-height:1.55'>{esc(r)}</div>"
            for r in card.get("why", [])
        )
        with col:
            st.markdown(
                f'<div class="surface surface-sm">'
                f'<div class="mc-label">{esc(card["label"])}</div>'
                f'<div class="mc-value" style="font-size:1.15rem;margin-top:7px">{esc(display_value(card["title"]))}</div>'
                f'<div class="s-subtitle">{esc(display_value(card["detail"]))}</div>'
                f'<div style="margin-top:12px"><span class="{card["class"]}">{esc(card["badge"])}</span></div>'
                f'<div style="display:grid;gap:6px;margin-top:12px">{why_html}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )


# ─── HEALTH BAR ──────────────────────────────────────────────────────────────

def render_health_bar(health_summary: dict):
    ok    = health_summary.get("healthy_sources", 0)
    fail  = len(health_summary.get("failed_sources", []))
    stale = len(health_summary.get("stale_sources", []))
    st.markdown(
        f'<div class="health-rail">'
        f'<span class="h-pill h-ok"><span class="h-dot h-dot-ok"></span>OK {ok}</span>'
        f'<span class="h-pill h-fail"><span class="h-dot h-dot-fail"></span>Fail {fail}</span>'
        f'<span class="h-pill h-stale"><span class="h-dot h-dot-stale"></span>Stale {stale}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )


# ─── DATA TABLE CARD ─────────────────────────────────────────────────────────

def build_data_table_card_html(title: str, rows, kicker: str = "", caption: str = "", show_delta: bool = False, metric_context: dict | None = None) -> str:
    kicker_html  = f"<div class='dc-kicker'>{esc(kicker)}</div>" if kicker else ""
    caption_html = f"<div class='dc-caption'>{esc(caption)}</div>" if caption else ""

    def _context_html(label: str) -> str:
        if not metric_context:
            return ""
        ctx = metric_context.get(label, "")
        if not ctx:
            return ""
        return (
            f"<div style='font-size:0.66rem;color:var(--text-muted);opacity:0.7;"
            f"margin-top:2px;line-height:1.4;padding-left:2px'>{esc(ctx)}</div>"
        )

    if show_delta:
        head = "<div class='dc-grid-head dc-grid-head-delta'><span>Metrik</span><span>Deger</span><span>Gunluk %</span></div>"
        body = "".join(
            f"<div class='dc-row dc-row-delta'>"
            f"<div class='dc-key'>{esc(label)}{_context_html(label)}</div>"
            f"<div class='dc-value'>{esc(display_value(val))}</div>"
            f"<div class='dc-delta {delta_css(delta)}'>{esc(clean_text(delta))}</div>"
            f"</div>"
            for label, val, delta in rows
        )
    else:
        head = "<div class='dc-grid-head'><span>Metrik</span><span>Deger</span></div>"
        body = "".join(
            f"<div class='dc-row'>"
            f"<div class='dc-key'>{esc(label)}{_context_html(label)}</div>"
            f"<div class='dc-value'>{esc(display_value(val))}</div>"
            f"</div>"
            for label, val in rows
        )

    return (
        f"<div class='data-card'>"
        f"<div class='dc-head'>{kicker_html}<div class='dc-title'>{esc(title)}</div>{caption_html}</div>"
        f"{head}"
        f"<div class='dc-rows'>{body}</div>"
        f"</div>"
    )


def render_data_table_card(title: str, rows, kicker: str = "", caption: str = "", show_delta: bool = False, metric_context: dict | None = None):
    st.markdown(
        build_data_table_card_html(title, rows, kicker=kicker, caption=caption, show_delta=show_delta, metric_context=metric_context),
        unsafe_allow_html=True,
    )
