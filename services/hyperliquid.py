# services/hyperliquid.py — Hyperliquid Balina Veri Servisi
# Hyperliquid on-chain perpetual DEX'inden büyük pozisyon ve trade verisi çeker.
# Auth gerektirmez — tamamen public API.
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

import requests

LOGGER = logging.getLogger("sa_finance_terminal.hyperliquid")
if not LOGGER.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    LOGGER.addHandler(handler)
LOGGER.setLevel(logging.INFO)

HL_API_URL  = "https://api.hyperliquid.xyz/info"
HL_HEADERS  = {"Content-Type": "application/json"}
HL_TIMEOUT  = 12

# Balina eşiği: bu değerin üzerindeki pozisyonlar/işlemler raporlanır
WHALE_NOTIONAL_USD = 500_000   # $500K+
LARGE_TRADE_USD    = 100_000   # $100K+ single trade


# ── Veri sınıfları ─────────────────────────────────────────────────────────────

@dataclass
class HLTrade:
    coin: str
    side: str          # "B" (buy/long) veya "A" (ask/sell/short)
    px: float
    sz: float
    notional: float
    time_ms: int

@dataclass
class HLPosition:
    user: str
    coin: str
    side: str          # "long" veya "short"
    szi: float         # position size in coin
    entry_px: float
    upnl: float
    notional: float

@dataclass
class HLWhaleSnapshot:
    """fetch_hl_whale_data() tarafından döndürülen tam snapshot."""
    large_trades: list[HLTrade]        = field(default_factory=list)
    top_positions: list[HLPosition]    = field(default_factory=list)
    net_bias_usd: float                = 0.0   # pozitif = net long, negatif = net short
    long_total_usd: float              = 0.0
    short_total_usd: float             = 0.0
    big_trade_count_1h: int            = 0
    whale_alert: str                   = ""    # "🐋 LONG" / "🐋 SHORT" / ""
    latency_ms: float                  = 0.0
    error: str                         = ""


# ── Yardımcı fonksiyonlar ──────────────────────────────────────────────────────

def _post(payload: dict) -> dict | list | None:
    """Hyperliquid info endpoint'ine POST atar; hata durumunda None döner."""
    try:
        r = requests.post(HL_API_URL, json=payload, headers=HL_HEADERS, timeout=HL_TIMEOUT)
        r.raise_for_status()
        return r.json()
    except requests.Timeout:
        LOGGER.warning("hyperliquid: timeout (%ds)", HL_TIMEOUT)
    except requests.HTTPError as exc:
        LOGGER.warning("hyperliquid: HTTP %s", exc.response.status_code if exc.response else exc)
    except Exception as exc:
        LOGGER.warning("hyperliquid: %s", exc)
    return None


def _notional(px: float, sz: float) -> float:
    return abs(px * sz)


# ── Büyük trade çekici ─────────────────────────────────────────────────────────

def _fetch_large_trades(coin: str = "BTC") -> list[HLTrade]:
    """
    Son işlemlerden WHALE_NOTIONAL_USD üzerindeki trade'leri döner.
    Hyperliquid recentTrades endpoint'i son ~200 trade verir.
    """
    raw = _post({"type": "recentTrades", "coin": coin})
    if not isinstance(raw, list):
        return []

    trades: list[HLTrade] = []
    now_ms = int(time.time() * 1000)
    one_hour_ms = 3_600_000

    for item in raw:
        try:
            px  = float(item.get("px", 0))
            sz  = float(item.get("sz", 0))
            notional = _notional(px, sz)
            if notional < LARGE_TRADE_USD:
                continue
            ts = int(item.get("time", 0))
            # Son 1 saatteki işlemleri al
            if now_ms - ts > one_hour_ms:
                continue
            side = item.get("side", "")  # "B" buy / "A" sell
            trades.append(HLTrade(
                coin=coin, side=side, px=px, sz=sz, notional=notional, time_ms=ts
            ))
        except (TypeError, ValueError, KeyError):
            continue

    return trades


# ── Top trader pozisyon çekici ─────────────────────────────────────────────────

def _fetch_top_positions() -> list[HLPosition]:
    """
    Leaderboard'daki top trader'ların BTC pozisyonlarını çeker.
    Sadece WHALE_NOTIONAL_USD üzeri pozisyonlar alınır.
    """
    raw = _post({"type": "leaderboard"})
    if not isinstance(raw, dict):
        return []

    # leaderboard_rows içinde her trader'ın pozisyon listesi var
    rows = raw.get("leaderboardRows", [])
    positions: list[HLPosition] = []

    for row in rows[:50]:  # top 50 trader
        user = row.get("ethAddress", "")[:10]
        prize = row.get("prize", {})
        # Her trader'ın pozisyon snapshot'ı için ayrı sorgu gerekmez;
        # leaderboard'da accountValue + positions embedded gelir bazı versiyonlarda
        # Yoksa clearinghouseState ile takip edilebilir ama rate limit açısından
        # sadece embedded data'yı kullanalım.
        acct = row.get("accountValue", "0")
        try:
            acct_val = float(acct)
        except (TypeError, ValueError):
            acct_val = 0.0

        if acct_val < WHALE_NOTIONAL_USD:
            continue

        # Pozisyon detayları embedded geliyorsa parse et
        for pos in row.get("positions", []):
            try:
                coin = pos.get("coin", "")
                szi  = float(pos.get("szi", 0))
                entry_px = float(pos.get("entryPx", 0) or 0)
                upnl = float(pos.get("unrealizedPnl", 0) or 0)
                notional = _notional(entry_px, szi)
                if notional < WHALE_NOTIONAL_USD:
                    continue
                side = "long" if szi > 0 else "short"
                positions.append(HLPosition(
                    user=user, coin=coin, side=side,
                    szi=abs(szi), entry_px=entry_px,
                    upnl=upnl, notional=notional,
                ))
            except (TypeError, ValueError, KeyError):
                continue

    return positions


# ── Ana fetch fonksiyonu ───────────────────────────────────────────────────────

def fetch_hl_whale_data(coins: list[str] | None = None) -> HLWhaleSnapshot:
    """
    Hyperliquid'den balina verisi çeker ve HLWhaleSnapshot döner.

    Terminaldeki veri motoru tarafından çağrılır.
    Hata durumunda boş snapshot döner (terminal çalışmaya devam eder).
    """
    if coins is None:
        coins = ["BTC", "ETH", "SOL"]

    started = time.perf_counter()
    snap = HLWhaleSnapshot()

    # 1) Büyük trade'ler
    all_trades: list[HLTrade] = []
    for coin in coins:
        all_trades.extend(_fetch_large_trades(coin))
    snap.large_trades = sorted(all_trades, key=lambda t: t.notional, reverse=True)[:20]
    snap.big_trade_count_1h = len(snap.large_trades)

    # 2) Top pozisyonlar
    snap.top_positions = _fetch_top_positions()

    # 3) Net bias hesabı (trade'lerden)
    long_usd  = sum(t.notional for t in snap.large_trades if t.side == "B")
    short_usd = sum(t.notional for t in snap.large_trades if t.side == "A")
    # Pozisyonlardan da ekle
    for p in snap.top_positions:
        if p.side == "long":
            long_usd  += p.notional
        else:
            short_usd += p.notional

    snap.long_total_usd  = long_usd
    snap.short_total_usd = short_usd
    snap.net_bias_usd    = long_usd - short_usd

    # 4) Whale alert etiketi
    threshold = 2_000_000  # $2M net bias = dikkat çekici
    if snap.net_bias_usd > threshold:
        snap.whale_alert = "🐋 NET LONG"
    elif snap.net_bias_usd < -threshold:
        snap.whale_alert = "🐋 NET SHORT"

    snap.latency_ms = (time.perf_counter() - started) * 1000
    LOGGER.info(
        "hyperliquid: %d büyük trade, %d pozisyon | net_bias $%.0f | %.0fms",
        len(snap.large_trades), len(snap.top_positions), snap.net_bias_usd, snap.latency_ms,
    )
    return snap


# ── Yardımcı format fonksiyonları (UI için) ────────────────────────────────────

def fmt_usd_short(val: float) -> str:
    """$142.3M / $1.2B gibi kısa format."""
    if val == 0:
        return "$0"
    sign = "-" if val < 0 else "+"
    abs_val = abs(val)
    if abs_val >= 1_000_000_000:
        return f"{sign}${abs_val/1_000_000_000:.1f}B"
    if abs_val >= 1_000_000:
        return f"{sign}${abs_val/1_000_000:.1f}M"
    return f"{sign}${abs_val/1_000:.0f}K"


def whale_summary_rows(snap: HLWhaleSnapshot) -> list[tuple[str, str]]:
    """
    render_data_table_card() için satır listesi döner.
    Snapshot boşsa placeholder satırları döner.
    """
    if snap.error:
        return [("HL Durum", "⚠ Veri alınamadı")]

    rows = [
        ("HL Net Bias (1s)",   fmt_usd_short(snap.net_bias_usd) if snap.net_bias_usd != 0 else "—"),
        ("HL Long Hacim",      fmt_usd_short(snap.long_total_usd) if snap.long_total_usd else "—"),
        ("HL Short Hacim",     fmt_usd_short(snap.short_total_usd) if snap.short_total_usd else "—"),
        ("Büyük İşlem (1s)",   f"{snap.big_trade_count_1h} adet" if snap.big_trade_count_1h else "—"),
        ("Balina Sinyali",     snap.whale_alert if snap.whale_alert else "Nötr"),
    ]

    # En büyük 3 işlemi göster
    for i, t in enumerate(snap.large_trades[:3], 1):
        side_label = "AL" if t.side == "B" else "SAT"
        rows.append((
            f"İşlem #{i} ({t.coin})",
            f"{side_label} {fmt_usd_short(t.notional)}",
        ))

    return rows
