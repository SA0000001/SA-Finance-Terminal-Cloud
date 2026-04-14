"""
SA Finance Alpha Terminal — Design Token System
Single source of truth for all CSS variables, semantic colors, spacing, and typography.
Injected once at app startup; never duplicated in component files.
"""

TERMINAL_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600;700&family=Inter:wght@400;500;600;700;800;900&display=swap');

/* ─── DESIGN TOKENS ─────────────────────────────────────────────────────── */
:root {
    /* Surface hierarchy */
    --bg-base:        #050d18;
    --bg-raised:      #081422;
    --bg-elevated:    #0c1b2e;
    --bg-overlay:     #102238;

    /* Panel system */
    --panel:          rgba(9, 16, 28, 0.88);
    --panel-soft:     rgba(10, 19, 33, 0.72);
    --panel-strong:   rgba(8, 14, 24, 0.96);
    --panel-glass:    rgba(12, 22, 38, 0.78);

    /* Borders */
    --border:         rgba(100, 140, 185, 0.13);
    --border-soft:    rgba(100, 140, 185, 0.08);
    --border-strong:  rgba(100, 140, 185, 0.24);
    --border-accent:  rgba(82, 200, 255, 0.32);

    /* Accent — primary blue-cyan */
    --accent:         #52c8ff;
    --accent-dim:     rgba(82, 200, 255, 0.12);
    --accent-glow:    rgba(82, 200, 255, 0.22);
    --accent-line:    rgba(82, 200, 255, 0.36);

    /* Semantic colors */
    --positive:       #32d98c;
    --positive-dim:   rgba(50, 217, 140, 0.12);
    --negative:       #ff5f72;
    --negative-dim:   rgba(255, 95, 114, 0.12);
    --warning:        #f0c050;
    --warning-dim:    rgba(240, 192, 80, 0.12);
    --neutral:        #7a93b0;

    /* Typography */
    --text-primary:   #eef3fa;
    --text-secondary: #bfcedd;
    --text-muted:     #8aa0b8;
    --text-faint:     #607080;

    /* Type scale */
    --font-mono:  'IBM Plex Mono', 'Courier New', monospace;
    --font-sans:  'Inter', system-ui, -apple-system, sans-serif;

    /* Spacing scale */
    --sp-1:  4px;
    --sp-2:  8px;
    --sp-3:  12px;
    --sp-4:  16px;
    --sp-5:  20px;
    --sp-6:  24px;
    --sp-8:  32px;
    --sp-10: 40px;

    /* Radius */
    --r-xs:  8px;
    --r-sm:  12px;
    --r-md:  16px;
    --r-lg:  22px;
    --r-xl:  28px;
    --r-pill: 999px;

    /* Shadows */
    --shadow-sm:  0 4px 12px rgba(0,0,0,0.18);
    --shadow-md:  0 12px 32px rgba(0,0,0,0.22);
    --shadow-lg:  0 22px 56px rgba(0,0,0,0.28);

    /* Transitions */
    --transition: 140ms ease;
    --transition-slow: 220ms ease;
}

/* ─── GLOBAL RESET / BASE ───────────────────────────────────────────────── */
html, body,
[data-testid="stAppViewContainer"],
[data-testid="stAppViewContainer"] > section {
    background:
        radial-gradient(ellipse 80% 50% at 85% -10%, rgba(52, 130, 220, 0.07) 0%, transparent 55%),
        radial-gradient(ellipse 60% 40% at 10% 110%, rgba(82, 200, 255, 0.04) 0%, transparent 50%),
        linear-gradient(180deg, #050d18 0%, #060e1c 100%) !important;
    font-family: var(--font-sans) !important;
    color: var(--text-primary) !important;
    font-feature-settings: "kern" 1, "liga" 1, "calt" 1;
    -webkit-font-smoothing: antialiased;
}

/* ─── STREAMLIT CHROME OVERRIDES ────────────────────────────────────────── */
#MainMenu, footer, header { visibility: hidden; }

[data-testid="stSidebar"] {
    background: linear-gradient(180deg,
        rgba(6, 12, 22, 0.99) 0%,
        rgba(8, 16, 29, 0.99) 100%) !important;
    border-right: 1px solid var(--border) !important;
}

[data-testid="stSidebar"] [data-testid="stSidebarContent"] {
    padding-top: 1.4rem;
}

[data-testid="block-container"] {
    padding-top: 1.2rem !important;
    padding-bottom: 3rem !important;
    max-width: 1600px;
}

/* ─── TAB SYSTEM ────────────────────────────────────────────────────────── */
[data-testid="stTabs"] {
    margin-top: 10px;
}

[data-testid="stTabs"] [role="tablist"] {
    gap: 6px;
    border-bottom: 1px solid var(--border);
    padding-bottom: 0;
}

[data-testid="stTab"] {
    background: transparent !important;
    border: none !important;
    border-bottom: 2px solid transparent !important;
    border-radius: 0 !important;
    padding: 10px 16px 10px !important;
    margin-right: 2px !important;
    color: var(--text-muted) !important;
    font-weight: 500 !important;
    font-size: 0.85rem !important;
    letter-spacing: 0.01em !important;
    transition: color var(--transition), border-color var(--transition) !important;
}

[data-testid="stTab"]:hover {
    color: var(--text-secondary) !important;
}

[data-testid="stTab"][aria-selected="true"] {
    color: var(--accent) !important;
    border-bottom-color: var(--accent) !important;
    font-weight: 600 !important;
}

/* ─── BUTTON SYSTEM ─────────────────────────────────────────────────────── */
[data-testid="stButton"] > button,
[data-testid="stDownloadButton"] > button,
[data-testid="stLinkButton"] > a {
    border-radius: var(--r-sm) !important;
    border: 1px solid var(--border-strong) !important;
    background: rgba(12, 22, 38, 0.92) !important;
    color: var(--text-secondary) !important;
    font-weight: 600 !important;
    font-size: 0.82rem !important;
    letter-spacing: 0.01em !important;
    transition: all var(--transition) !important;
    min-height: 2.4rem !important;
}

[data-testid="stButton"] > button:hover,
[data-testid="stDownloadButton"] > button:hover {
    border-color: var(--border-accent) !important;
    color: var(--text-primary) !important;
    background: rgba(16, 28, 46, 0.96) !important;
}

/* ─── EXPANDER ──────────────────────────────────────────────────────────── */
[data-testid="stExpander"] {
    border: 1px solid var(--border) !important;
    border-radius: var(--r-md) !important;
    background: rgba(8, 15, 25, 0.82) !important;
    overflow: hidden;
}

[data-testid="stExpander"] details summary {
    padding: 0.3rem 0.5rem !important;
    font-size: 0.84rem;
    color: var(--text-muted);
    font-weight: 500;
}

[data-testid="stExpanderDetails"] {
    padding-top: 0.2rem !important;
}

/* ─── DATAFRAME ─────────────────────────────────────────────────────────── */
[data-testid="stDataFrame"] {
    border-radius: var(--r-md);
    overflow: hidden;
    border: 1px solid var(--border);
}

/* ─── TERMINAL HEADER ───────────────────────────────────────────────────── */
.t-header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    padding: 22px 26px;
    margin: 0 0 10px 0;
    border: 1px solid var(--border-strong);
    border-radius: var(--r-xl);
    background:
        radial-gradient(ellipse 50% 80% at 100% 0%, rgba(52, 130, 220, 0.10) 0%, transparent 55%),
        linear-gradient(135deg, rgba(8, 16, 29, 0.98) 0%, rgba(10, 22, 38, 0.98) 100%);
    box-shadow: var(--shadow-lg);
    gap: 20px;
}

.t-header-left { flex: 1; min-width: 0; }
.t-header-right {
    display: flex;
    flex-direction: column;
    align-items: flex-end;
    gap: 12px;
    min-width: 240px;
}

.t-kicker {
    font-family: var(--font-mono);
    font-size: 0.66rem;
    letter-spacing: 0.22em;
    text-transform: uppercase;
    color: var(--accent);
    margin-bottom: 10px;
}

.t-wordmark {
    font-family: var(--font-sans);
    font-size: 1.9rem;
    font-weight: 800;
    letter-spacing: -0.05em;
    color: var(--text-primary);
    line-height: 1.05;
}

.t-tagline {
    margin-top: 8px;
    font-size: 0.84rem;
    color: var(--text-muted);
    line-height: 1.6;
    max-width: 60ch;
}

.t-state-chips {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
    margin-top: 14px;
}

.t-chip {
    display: flex;
    flex-direction: column;
    min-width: 130px;
    padding: 10px 12px;
    border-radius: var(--r-sm);
    background: rgba(255,255,255,0.028);
    border: 1px solid var(--border);
}

.t-chip-label {
    font-family: var(--font-mono);
    font-size: 0.6rem;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: var(--text-muted);
    margin-bottom: 5px;
}

.t-chip-value {
    font-size: 0.88rem;
    font-weight: 700;
    color: var(--text-primary);
    line-height: 1.3;
}

.t-pill-row {
    display: flex;
    gap: 6px;
    flex-wrap: wrap;
    justify-content: flex-end;
}

.t-pill {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    padding: 6px 10px;
    border-radius: var(--r-pill);
    border: 1px solid var(--border-strong);
    background: rgba(8, 16, 28, 0.78);
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: 0.68rem;
    letter-spacing: 0.04em;
}

.t-badge {
    padding: 6px 11px;
    border-radius: var(--r-pill);
    background: var(--accent);
    color: #021018;
    font-family: var(--font-mono);
    font-size: 0.68rem;
    font-weight: 700;
    letter-spacing: 0.04em;
}

.t-meta {
    text-align: right;
    font-size: 0.78rem;
    color: var(--text-muted);
    line-height: 1.65;
}

/* ─── HEALTH RAIL ───────────────────────────────────────────────────────── */
.health-rail {
    display: flex;
    align-items: center;
    gap: 6px;
    margin: 8px 0 12px 0;
    flex-wrap: wrap;
}

.h-pill {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    padding: 5px 10px;
    border-radius: var(--r-pill);
    font-family: var(--font-mono);
    font-size: 0.68rem;
    letter-spacing: 0.06em;
    border: 1px solid;
}

.h-ok    { border-color: rgba(50,217,140,0.38); color: var(--positive); }
.h-fail  { border-color: rgba(255,95,114,0.38);  color: var(--negative); }
.h-stale { border-color: rgba(240,192,80,0.38);  color: var(--warning); }

.h-dot {
    width: 5px; height: 5px;
    border-radius: 50%;
    display: inline-block;
}
.h-dot-ok    { background: var(--positive); }
.h-dot-fail  { background: var(--negative); }
.h-dot-stale { background: var(--warning); }

/* ─── STATUS HUB ────────────────────────────────────────────────────────── */
.status-hub {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
    padding: 14px 18px;
    border-radius: var(--r-md);
    border: 1px solid var(--border);
    background: var(--panel);
    margin-bottom: 10px;
}

.sh-left { flex: 1; min-width: 0; }
.sh-title {
    font-size: 0.84rem;
    font-weight: 600;
    color: var(--text-primary);
}
.sh-copy {
    font-size: 0.78rem;
    color: var(--text-muted);
    margin-top: 3px;
    line-height: 1.5;
}

.sh-stats {
    display: flex;
    gap: 10px;
    flex-wrap: wrap;
}

.sh-stat {
    padding: 8px 12px;
    border-radius: var(--r-xs);
    border: 1px solid var(--border);
    background: rgba(255,255,255,0.024);
    text-align: center;
    min-width: 80px;
}
.sh-stat-label {
    display: block;
    font-family: var(--font-mono);
    font-size: 0.6rem;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--text-muted);
}
.sh-stat-value {
    display: block;
    margin-top: 4px;
    font-size: 0.9rem;
    font-weight: 700;
    color: var(--text-primary);
}

/* ─── SURFACE SYSTEM ────────────────────────────────────────────────────── */
.surface {
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: var(--r-lg);
    padding: var(--sp-5);
    box-shadow: var(--shadow-sm);
    backdrop-filter: blur(12px);
}

.surface-sm  { padding: var(--sp-4); border-radius: var(--r-md); }
.surface-xs  { padding: var(--sp-3) var(--sp-4); border-radius: var(--r-sm); }

/* ─── SECTION LABELS ────────────────────────────────────────────────────── */
.s-kicker {
    font-family: var(--font-mono);
    font-size: 0.62rem;
    letter-spacing: 0.2em;
    text-transform: uppercase;
    color: var(--accent);
    margin-bottom: 6px;
}

.s-title {
    font-size: 1.35rem;
    font-weight: 800;
    letter-spacing: -0.04em;
    color: var(--text-primary);
    line-height: 1.1;
}

.s-subtitle {
    font-size: 0.82rem;
    color: var(--text-muted);
    line-height: 1.55;
    margin-top: 5px;
}

.s-divider {
    height: 1px;
    background: var(--border);
    margin: 14px 0;
}

.section-notice {
    padding: var(--sp-3) var(--sp-4);
    border-radius: var(--r-sm);
    border: 1px solid var(--border);
    border-left: 3px solid var(--accent);
    background: rgba(8,16,28,0.8);
    color: var(--text-secondary);
    font-size: 0.82rem;
    line-height: 1.55;
    margin: 8px 0 12px;
}

/* ─── REGIME HERO ───────────────────────────────────────────────────────── */
.regime-hero {
    padding: var(--sp-5);
    border-radius: var(--r-lg);
    background: var(--panel);
    border: 1px solid var(--border);
    height: 100%;
}

.regime-score-num {
    font-size: 4.2rem;
    font-weight: 900;
    letter-spacing: -0.1em;
    color: #fff;
    line-height: 0.9;
    margin-top: 14px;
}

.regime-overlay-badge {
    display: inline-flex;
    align-items: center;
    padding: 6px 12px;
    border-radius: var(--r-pill);
    border: 1px solid var(--border-strong);
    background: rgba(10, 22, 38, 0.7);
    font-family: var(--font-mono);
    font-size: 0.72rem;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--text-primary);
}

.regime-band-copy {
    font-size: 0.88rem;
    color: var(--text-muted);
    line-height: 1.65;
    margin-top: 10px;
    max-width: 52ch;
}

.cue-row {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
    margin-top: 14px;
}

.cue-chip {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 7px 11px;
    border-radius: var(--r-pill);
    border: 1px solid var(--border);
    background: rgba(255,255,255,0.03);
    font-family: var(--font-mono);
    font-size: 0.7rem;
    color: var(--text-muted);
}

.cue-chip strong { color: var(--text-primary); font-weight: 600; }

.regime-stats-row {
    display: grid;
    grid-template-columns: repeat(3, minmax(0,1fr));
    gap: 10px;
    margin-top: 16px;
}

.rstat {
    padding: 12px;
    border-radius: var(--r-sm);
    background: rgba(255,255,255,0.024);
    border: 1px solid var(--border-soft);
}

.rstat-label {
    display: block;
    font-family: var(--font-mono);
    font-size: 0.6rem;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--text-muted);
}

.rstat-value {
    display: block;
    margin-top: 6px;
    font-size: 0.9rem;
    font-weight: 700;
    color: var(--text-primary);
    line-height: 1.35;
}

/* ─── CONTRIBUTION LIST ─────────────────────────────────────────────────── */
.contrib-list { margin-top: 16px; display: grid; gap: 8px; }

.contrib-row {
    display: flex;
    gap: 10px;
    align-items: center;
}

.contrib-label {
    min-width: 130px;
    font-size: 0.8rem;
    color: var(--text-muted);
}

.contrib-bar-track {
    flex: 1;
    height: 5px;
    border-radius: var(--r-pill);
    background: rgba(255,255,255,0.05);
    overflow: hidden;
}

.contrib-bar-fill {
    height: 100%;
    border-radius: var(--r-pill);
    background: linear-gradient(90deg, var(--accent) 0%, rgba(82,200,255,0.3) 100%);
}

.contrib-pts {
    min-width: 50px;
    text-align: right;
    font-family: var(--font-mono);
    font-size: 0.78rem;
    font-weight: 600;
    color: var(--text-secondary);
}

/* ─── FRAGILITY PANEL ───────────────────────────────────────────────────── */
.frag-panel {
    padding: var(--sp-5);
    border-radius: var(--r-lg);
    background: var(--panel);
    border: 1px solid var(--border);
    height: 100%;
}

.frag-score {
    font-size: 3rem;
    font-weight: 900;
    letter-spacing: -0.08em;
    color: #fff;
    line-height: 0.9;
    margin-top: 10px;
}

.frag-label {
    margin-top: 7px;
    font-family: var(--font-mono);
    font-size: 0.72rem;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--warning);
}

.frag-flags {
    display: grid;
    gap: 7px;
    margin-top: 14px;
}

.frag-flag {
    padding: 9px 11px;
    border-radius: var(--r-sm);
    border: 1px solid var(--border-soft);
    background: rgba(255,255,255,0.025);
    color: var(--text-secondary);
    font-size: 0.82rem;
    line-height: 1.5;
}

/* ─── FACTOR CARDS ──────────────────────────────────────────────────────── */
.factor-grid-2 {
    display: grid;
    grid-template-columns: repeat(2, minmax(0,1fr));
    gap: 14px;
    margin-top: 14px;
}

.factor-card {
    padding: var(--sp-4);
    border-radius: var(--r-md);
    border: 1px solid var(--border);
    background: rgba(255,255,255,0.022);
}

.fc-head {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 10px;
}

.fc-name {
    font-size: 0.9rem;
    font-weight: 700;
    color: var(--text-primary);
}

.fc-weight {
    font-family: var(--font-mono);
    font-size: 0.66rem;
    letter-spacing: 0.08em;
    color: var(--text-muted);
}

.fc-score-row {
    display: flex;
    justify-content: space-between;
    align-items: flex-end;
    gap: 10px;
    margin-top: 12px;
}

.fc-score {
    font-size: 2.1rem;
    font-weight: 900;
    letter-spacing: -0.07em;
    color: #fff;
    line-height: 0.9;
}

.fc-delta {
    font-family: var(--font-mono);
    font-size: 0.78rem;
    letter-spacing: 0.04em;
    padding-bottom: 2px;
}

.fc-delta-up   { color: var(--positive); }
.fc-delta-down { color: var(--negative); }
.fc-delta-flat { color: var(--text-muted); }

.fc-copy {
    margin-top: 9px;
    font-size: 0.82rem;
    color: var(--text-muted);
    line-height: 1.6;
}

.fc-meta {
    margin-top: 10px;
    display: flex;
    justify-content: space-between;
    gap: 10px;
    font-size: 0.76rem;
    color: var(--text-faint);
}

.fc-drivers {
    display: grid;
    gap: 7px;
    margin-top: 12px;
    border-top: 1px solid var(--border-soft);
    padding-top: 10px;
}

.fc-driver {
    font-size: 0.8rem;
    color: var(--text-muted);
    line-height: 1.55;
}

/* ─── COMMAND SURFACE ───────────────────────────────────────────────────── */
.command-surface {
    padding: var(--sp-5);
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: var(--r-lg);
    height: 100%;
    display: flex;
    flex-direction: column;
    gap: 14px;
}

.cs-title {
    font-size: 1.65rem;
    font-weight: 800;
    letter-spacing: -0.05em;
    color: var(--text-primary);
    line-height: 1.05;
}

.cs-copy {
    font-size: 0.84rem;
    color: var(--text-muted);
    line-height: 1.7;
    max-width: 58ch;
}

.cs-stat-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0,1fr));
    gap: 10px;
}

.cs-stat {
    padding: 12px;
    border-radius: var(--r-sm);
    background: rgba(255,255,255,0.026);
    border: 1px solid var(--border-soft);
}

.cs-stat-label {
    font-family: var(--font-mono);
    font-size: 0.6rem;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--text-muted);
}

.cs-stat-value {
    display: block;
    margin-top: 6px;
    font-size: 0.9rem;
    font-weight: 700;
    color: var(--text-primary);
    line-height: 1.4;
}

.cs-cols {
    display: grid;
    grid-template-columns: repeat(2, minmax(0,1fr));
    gap: 12px;
}

.cs-block {
    padding: 12px;
    border-radius: var(--r-sm);
    background: rgba(255,255,255,0.02);
    border: 1px solid var(--border-soft);
}

.cs-block-title {
    font-size: 0.78rem;
    font-weight: 700;
    color: var(--text-secondary);
    letter-spacing: 0.01em;
    margin-bottom: 10px;
}

.cs-list { display: grid; gap: 8px; }

.cs-item {
    position: relative;
    padding-left: 13px;
    font-size: 0.82rem;
    color: var(--text-muted);
    line-height: 1.6;
}

.cs-item::before {
    content: "";
    position: absolute;
    left: 0;
    top: 0.58rem;
    width: 5px;
    height: 5px;
    border-radius: 50%;
    background: var(--accent);
    opacity: 0.7;
}

/* ─── SIGNAL DECK ───────────────────────────────────────────────────────── */
.signal-deck {
    position: relative;
    overflow: hidden;
    padding: var(--sp-4);
    border-radius: var(--r-lg);
    background: linear-gradient(180deg,
        rgba(10, 19, 33, 0.94) 0%,
        rgba(7, 13, 22, 0.97) 100%);
    border: 1px solid var(--border);
    box-shadow: var(--shadow-sm);
    height: 100%;
}

.signal-deck::before {
    content: "";
    position: absolute;
    inset: 0 0 auto 0;
    height: 1px;
    background: linear-gradient(90deg,
        transparent 0%,
        rgba(82, 200, 255, 0.28) 50%,
        transparent 100%);
}

.sd-top {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 10px;
}

.sd-title {
    font-size: 1.0rem;
    font-weight: 700;
    color: var(--text-primary);
    letter-spacing: -0.02em;
}

.sd-score-block { text-align: right; }
.sd-score-num {
    display: block;
    font-size: 1.15rem;
    font-weight: 800;
    color: var(--text-primary);
}
.sd-score-label {
    display: block;
    font-family: var(--font-mono);
    font-size: 0.6rem;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--text-muted);
    margin-top: 2px;
}

.sd-copy {
    margin-top: 8px;
    font-size: 0.8rem;
    color: var(--text-muted);
    line-height: 1.6;
}

.sd-band {
    margin-top: 12px;
    padding: 9px 11px;
    border-radius: var(--r-sm);
    border: 1px solid var(--border);
    font-size: 0.78rem;
    line-height: 1.55;
}

.sd-band-ok   { border-color: rgba(50,217,140,0.22); background: rgba(50,217,140,0.07); color: #c0f5df; }
.sd-band-warn { border-color: rgba(240,192,80,0.22); background: rgba(240,192,80,0.07); color: #f8e6b0; }
.sd-band-risk { border-color: rgba(255,95,114,0.22); background: rgba(255,95,114,0.07); color: #ffd4da; }

.sd-chips {
    display: flex;
    gap: 6px;
    flex-wrap: wrap;
    margin-top: 12px;
}

.sd-chip {
    display: inline-flex;
    align-items: center;
    padding: 4px 8px;
    border-radius: var(--r-pill);
    border: 1px solid var(--border);
    background: rgba(255,255,255,0.025);
    font-family: var(--font-mono);
    font-size: 0.66rem;
    color: var(--text-muted);
    font-weight: 500;
}

.sd-ctx-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
    gap: 8px;
    margin-top: 12px;
}

.sd-ctx-item {
    padding: 10px;
    border-radius: var(--r-xs);
    background: rgba(255,255,255,0.025);
    border: 1px solid var(--border-soft);
}

.sd-ctx-label {
    display: block;
    font-family: var(--font-mono);
    font-size: 0.62rem;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--text-muted);
}

.sd-ctx-value {
    display: block;
    margin-top: 6px;
    font-size: 0.84rem;
    font-weight: 700;
    color: var(--text-primary);
}

.sd-rows { display: grid; gap: 8px; margin-top: 12px; }

.sd-row {
    display: flex;
    justify-content: space-between;
    gap: 10px;
    padding-bottom: 7px;
    border-bottom: 1px solid var(--border-soft);
}

.sd-row:last-child { border-bottom: none; padding-bottom: 0; }

.sd-row-key { font-size: 0.8rem; color: var(--text-muted); line-height: 1.5; }
.sd-row-val { font-size: 0.82rem; font-weight: 700; color: var(--text-primary); text-align: right; }

/* ─── METRIC CARD ───────────────────────────────────────────────────────── */
.metric-card {
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: var(--r-md);
    padding: var(--sp-4);
    box-shadow: var(--shadow-sm);
    min-height: 90px;
}

.mc-label {
    font-family: var(--font-mono);
    font-size: 0.62rem;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--text-muted);
}

.mc-value {
    font-size: 1.45rem;
    font-weight: 800;
    letter-spacing: -0.04em;
    color: var(--text-primary);
    margin-top: 8px;
    line-height: 1.1;
}

.mc-value-missing { color: var(--text-muted); font-size: 1rem; }

.mc-delta-pos { color: var(--positive); font-family: var(--font-mono); font-size: 0.76rem; margin-top: 4px; }
.mc-delta-neg { color: var(--negative); font-family: var(--font-mono); font-size: 0.76rem; margin-top: 4px; }
.mc-delta-neu { color: var(--text-muted); font-family: var(--font-mono); font-size: 0.76rem; margin-top: 4px; }

/* ─── COMPACT STRIP ─────────────────────────────────────────────────────── */
.compact-strip {
    background: rgba(255,255,255,0.025);
    border: 1px solid var(--border);
    border-radius: var(--r-sm);
    padding: 11px 13px;
    min-height: 76px;
}

.cs-strip-label {
    font-family: var(--font-mono);
    font-size: 0.62rem;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--text-muted);
}

.cs-strip-value {
    font-size: 0.98rem;
    font-weight: 700;
    color: var(--text-primary);
    margin-top: 6px;
    line-height: 1.3;
}

.cs-strip-tone {
    font-size: 0.74rem;
    color: var(--text-muted);
    margin-top: 4px;
}

/* ─── DATA TABLE CARDS ──────────────────────────────────────────────────── */
.data-card {
    background: linear-gradient(180deg, rgba(10, 18, 30, 0.92), rgba(7, 13, 22, 0.96));
    border: 1px solid var(--border);
    border-radius: var(--r-lg);
    padding: 13px;
    height: 100%;
    box-shadow: var(--shadow-sm);
}

.dc-head {
    padding-bottom: 8px;
    margin-bottom: 8px;
    border-bottom: 1px solid var(--border);
}

.dc-kicker {
    font-family: var(--font-mono);
    font-size: 0.6rem;
    letter-spacing: 0.16em;
    text-transform: uppercase;
    color: var(--accent);
    margin-bottom: 6px;
}

.dc-title {
    font-size: 0.98rem;
    font-weight: 700;
    letter-spacing: -0.02em;
    color: var(--text-primary);
}

.dc-caption {
    font-size: 0.78rem;
    color: var(--text-muted);
    line-height: 1.5;
    margin: 6px 0 12px;
}

.dc-grid-head {
    display: grid;
    grid-template-columns: minmax(0,1fr) minmax(110px,0.85fr);
    gap: 12px;
    padding: 0 2px 8px;
    border-bottom: 1px solid var(--border-soft);
    font-family: var(--font-mono);
    font-size: 0.62rem;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--text-muted);
}

.dc-grid-head-delta {
    grid-template-columns: minmax(0,1fr) minmax(100px,0.78fr) minmax(76px,0.54fr);
}

.dc-grid-head span:last-child { text-align: right; }

.dc-rows { display: grid; }

.dc-row {
    display: grid;
    grid-template-columns: minmax(0,1fr) minmax(110px,0.85fr);
    gap: 12px;
    padding: 8px 2px;
    border-bottom: 1px solid rgba(100,140,185,0.07);
    transition: background var(--transition);
}

.dc-row:last-child { border-bottom: none; }
.dc-row:hover { background: rgba(255,255,255,0.018); }
.dc-row-delta { grid-template-columns: minmax(0,1fr) minmax(100px,0.78fr) minmax(76px,0.54fr); }

.dc-key   { font-size: 0.84rem; color: var(--text-muted); line-height: 1.5; }
.dc-value { font-size: 0.86rem; font-weight: 600; color: var(--text-primary); text-align: right; word-break: break-word; line-height: 1.5; }
.dc-delta { font-size: 0.78rem; font-weight: 600; text-align: right; font-family: var(--font-mono); }
.dc-pos   { color: var(--positive); }
.dc-neg   { color: var(--negative); }
.dc-neu   { color: var(--text-muted); }

/* ─── REPORT CARDS ──────────────────────────────────────────────────────── */
.report-box {
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: var(--r-md);
    padding: 17px 20px;
    line-height: 1.72;
    font-size: 0.9em;
}

.rb-kicker {
    font-family: var(--font-mono);
    font-size: 0.62rem;
    letter-spacing: 0.18em;
    text-transform: uppercase;
    color: var(--accent);
    margin-bottom: 8px;
}

.rb-title {
    font-size: 1rem;
    font-weight: 700;
    color: var(--text-primary);
    margin-bottom: 8px;
}

.rb-body { color: var(--text-secondary); font-size: 0.9rem; line-height: 1.78; }
.rb-section-title {
    color: var(--text-primary);
    font-size: 0.88rem;
    font-weight: 700;
    margin: 18px 0 8px;
    letter-spacing: 0.01em;
}
.rb-line { color: var(--text-secondary); font-size: 0.9rem; line-height: 1.72; margin: 0 0 6px; }
.rb-line-thread { color: var(--text-primary); font-weight: 500; }
.rb-spacer { height: 8px; }

/* ─── SCENARIO MATRIX ───────────────────────────────────────────────────── */
.matrix-table {
    width: 100%;
    border-collapse: collapse;
    margin-top: 12px;
}

.matrix-table th,
.matrix-table td {
    padding: 10px 9px;
    border-bottom: 1px solid var(--border-soft);
    text-align: left;
    vertical-align: top;
}

.matrix-table th {
    font-family: var(--font-mono);
    font-size: 0.62rem;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--text-muted);
}

.matrix-table td {
    font-size: 0.84rem;
    color: var(--text-primary);
    line-height: 1.6;
}

/* ─── ALERT / NEWS ──────────────────────────────────────────────────────── */
.alert-item {
    padding: 11px 13px;
    border-radius: var(--r-sm);
    background: rgba(255,255,255,0.026);
    border: 1px solid var(--border-soft);
    margin-bottom: 8px;
}

.alert-item strong { display: block; color: var(--text-primary); font-size: 0.84rem; margin-bottom: 3px; }
.alert-item span   { color: var(--text-muted); font-size: 0.8rem; line-height: 1.55; }

.news-card {
    background: var(--panel);
    border: 1px solid var(--border-soft);
    border-left: 2px solid var(--accent);
    border-radius: var(--r-sm);
    padding: 12px 14px;
    margin-bottom: 9px;
}

.news-card a { color: var(--text-secondary); text-decoration: none; font-weight: 600; font-size: 0.86rem; }
.news-card a:hover { color: var(--text-primary); }
.news-meta { color: var(--text-muted); font-size: 0.68em; margin-top: 4px; font-family: var(--font-mono); }

/* ─── SIGNALS (long/short/neutral) ──────────────────────────────────────── */
.sig-long    { background: var(--positive-dim); border: 1px solid var(--positive); color: var(--positive); }
.sig-short   { background: var(--negative-dim); border: 1px solid var(--negative); color: var(--negative); }
.sig-neutral { background: var(--warning-dim); border: 1px solid var(--warning); color: var(--warning); }
.sig-long, .sig-short, .sig-neutral {
    font-family: var(--font-mono);
    font-size: 0.66rem;
    padding: 4px 9px;
    border-radius: var(--r-pill);
    display: inline-block;
    font-weight: 700;
    letter-spacing: 0.03em;
}

/* ─── SIDEBAR ───────────────────────────────────────────────────────────── */
.sidebar-note {
    padding: 11px 13px;
    border-radius: var(--r-sm);
    border: 1px solid var(--border);
    background: rgba(255,255,255,0.024);
    color: var(--text-muted);
    font-size: 0.8rem;
    line-height: 1.65;
}

/* ─── PANEL ROWS (key/value pairs) ─────────────────────────────────────── */
.panel-row {
    display: grid;
    grid-template-columns: minmax(110px,0.9fr) minmax(0,1.15fr);
    gap: 12px;
    padding: 9px 0;
    border-bottom: 1px solid rgba(28,42,64,0.9);
}
.panel-row:last-child { border-bottom: none; }
.panel-row span   { color: var(--text-muted); font-size: 0.84rem; }
.panel-row strong { color: var(--text-primary); text-align: right; font-size: 0.86rem; line-height: 1.5; }

/* ─── CATALYST STREAM ───────────────────────────────────────────────────── */
.catalyst-stream {
    padding: var(--sp-4);
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: var(--r-lg);
    height: 100%;
}

.cs-stream-cols {
    display: grid;
    grid-template-columns: repeat(2, minmax(0,1fr));
    gap: 12px;
    margin-top: 12px;
}

/* ─── RESPONSIVE ────────────────────────────────────────────────────────── */
@media (max-width: 1100px) {
    .t-header { flex-direction: column; }
    .t-header-right { align-items: flex-start; min-width: 0; }
    .t-pill-row { justify-content: flex-start; }
    .t-meta { text-align: left; }
    .regime-stats-row { grid-template-columns: repeat(2, minmax(0,1fr)); }
    .factor-grid-2,
    .cs-cols,
    .cs-stat-grid,
    .cs-stream-cols { grid-template-columns: 1fr; }
}

@media (max-width: 760px) {
    .t-state-chips { display: grid; }
    .regime-score-num { font-size: 3rem; }
}

/* ── Sidebar toggle — tüm olası Streamlit versiyonları için ─────────────── */
[data-testid="collapsedControl"],
button[kind="header"],
.st-emotion-cache-1rtdyuf,
.st-emotion-cache-pkbazv  {
    display: flex !important;
    visibility: visible !important;
    opacity: 1 !important;
    min-width: 28px !important;
    min-height: 48px !important;
    background: rgba(0, 170, 255, 0.15) !important;
    border: 1px solid rgba(0, 170, 255, 0.4) !important;
    border-radius: 0 6px 6px 0 !important;
    z-index: 999999 !important;
}

/* ─── FLOATING SIDEBAR TOGGLE ───────────────────────────────────────────── */
#sa-sidebar-toggle {
    position: fixed;
    top: 50%;
    left: 0;
    transform: translateY(-50%);
    z-index: 9999999;
    width: 22px;
    height: 64px;
    background: rgba(8, 20, 36, 0.92);
    border: 1px solid rgba(82, 200, 255, 0.28);
    border-left: none;
    border-radius: 0 8px 8px 0;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: width 0.18s ease, background 0.18s ease, border-color 0.18s ease;
    backdrop-filter: blur(8px);
    box-shadow: 2px 0 16px rgba(0,0,0,0.5), inset -1px 0 0 rgba(82,200,255,0.08);
}
#sa-sidebar-toggle:hover {
    width: 30px;
    background: rgba(82, 200, 255, 0.12);
    border-color: rgba(82, 200, 255, 0.55);
    box-shadow: 2px 0 20px rgba(82,200,255,0.15), inset -1px 0 0 rgba(82,200,255,0.15);
}
#sa-sidebar-toggle svg {
    transition: transform 0.22s ease, opacity 0.18s ease;
    opacity: 0.55;
}
#sa-sidebar-toggle:hover svg {
    opacity: 1;
    transform: scale(1.15);
}
#sa-sidebar-toggle.sidebar-open svg {
    transform: rotate(180deg);
}
#sa-sidebar-toggle:hover.sidebar-open svg {
    transform: rotate(180deg) scale(1.15);
}
</style>
"""
