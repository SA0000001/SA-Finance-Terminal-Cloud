"""
SA Finance Alpha Terminal — Manuel On-Chain Veri Deposu
=======================================================
CryptoQuant / Glassnode gibi kaynaklardan manuel girilen günlük
on-chain değerlerini JSON olarak saklar ve okur.

Streamlit Cloud'da dosya sistemi ephemeral olduğundan bu modül
st.session_state'i birincil depo, JSON dosyasını ikincil depo
olarak kullanır. Her ikisi de senkronize tutulur.

Depolanan metrikler (BCRM-12 referanslı):
  - btc_price           : BTC/USD fiyatı
  - nupl                : Net Unrealized Profit/Loss  (örn. 0.42)
  - sopr                : Spent Output Profit Ratio   (örn. 1.02)
  - mvrv                : MVRV Ratio                  (örn. 1.51)
  - sth_cost_basis      : STH Realized Price USD      (örn. 73800)
  - lth_cost_basis      : LTH Realized Price USD      (örn. 42000)
  - exchange_netflow    : Exchange Netflow BTC/gün     (örn. -2800)
  - exchange_reserve    : Exchange Reserve BTC         (örn. 2720000)
  - funding_rate        : Funding Rate %               (örn. 0.01)
  - open_interest       : Open Interest USD milyar     (örn. 23.8)
  - coinbase_premium    : Coinbase Premium Index       (örn. -0.5)
  - etf_flow_cumulative : Kümülatif ETF Flow USD milyar (örn. 66.3)
  - notes               : Serbest not metni
"""
from __future__ import annotations

import json
import math
import os
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional

import streamlit as st

# ── Storage path ──────────────────────────────────────────────────────────────
# Streamlit Cloud'da /tmp kalıcı değil ama uygulama yeniden başlayana kadar
# session içi erişim için yeterli. Asıl kalıcılık session_state üzerinden.
_DATA_DIR  = Path(os.getenv("ONCHAIN_MANUAL_DIR", "/tmp/sa_onchain_manual"))
_DATA_FILE = _DATA_DIR / "manual_entries.json"
_SS_KEY    = "onchain_manual_store"   # session_state anahtarı

# Boş template
METRIC_KEYS: list[str] = [
    "nupl",
    "sopr",
    "mvrv",
    "mvrv_z_score",
    "lth_cost_basis",
    "sth_cost_basis",
    "realized_price",
    "sth_rpl",
    "exchange_netflow",
    "exchange_reserve",
    "funding_rate",
    "open_interest",
    "long_liquidations",
    "short_liquidations",
    "coinbase_premium",
    "etf_flow_cumulative",
    "notes",
]

METRIC_LABELS: dict[str, str] = {
    "nupl":                "NUPL",
    "sopr":                "SOPR",
    "mvrv":                "MVRV Ratio",
    "mvrv_z_score":        "MVRV Ratio Z-Score",
    "lth_cost_basis":      "BTC Cost Basis — LTH Realized Price (USD)",
    "sth_cost_basis":      "BTC Cost Basis — STH Realized Price (USD)",
    "realized_price":      "Realized Price (USD)",
    "sth_rpl":             "STH Holder Realized P&L (%)",
    "exchange_netflow":    "Exchange Netflow — All Exchanges (BTC)",
    "exchange_reserve":    "Exchange Reserve — All Exchanges (BTC)",
    "funding_rate":        "Funding Rates — All Exchanges (%)",
    "open_interest":       "Open Interest — All Exchanges (USD milyar)",
    "long_liquidations":   "Bitcoin Futures Long Liquidations (USD milyon)",
    "short_liquidations":  "Bitcoin Futures Short Liquidations (USD milyon)",
    "coinbase_premium":    "Coinbase Premium Index",
    "etf_flow_cumulative": "Cumulative ETF Flow (USD milyar)",
    "notes":               "Not",
}

METRIC_HELP: dict[str, str] = {
    "nupl":                "0 altı: loss zone · 0–0.25: hope · 0.25–0.5: belief · 0.5–0.75: euphoria · 0.75+: greed",
    "sopr":                "1 altı: ortalama zararla satış · 1 üstü: kârlı satış · 1'de desteklenme bullish",
    "mvrv":                "1 altı: ucuz · 1.2–2.4: yapıcı · 2.4–3.0: dikkat · 3.0+: pahalı/aşırı ısınma",
    "mvrv_z_score":        "0 altı: zayıf/dip · 1–4: sağlıklı · 4–6: dikkat · 6+: tepe riski · 7+: aşırı ısınma",
    "lth_cost_basis":      "Long-Term Holder (155+ gün) ortalama alış fiyatı — fiyat üstünde olması yapısal pozitif",
    "sth_cost_basis":      "Short-Term Holder (<155 gün) ortalama alış fiyatı — fiyat altındaysa STH baskısı",
    "realized_price":      "Tüm coin'lerin son hareket fiyatı ortalaması — fiyat üstündeyse piyasa kârlı",
    "sth_rpl":             "STH holderların realize P&L yüzdesi; kontrollü kâr sağlıklı, sert zarar = capitulation",
    "exchange_netflow":    "Pozitif = borsaya giriş (satış baskısı) · Negatif = çıkış (withdrawal/tutma)",
    "exchange_reserve":    "Tüm borsalardaki toplam BTC miktarı — düşüş trendi bullish",
    "funding_rate":        "Perpetual funding; hafif pozitif nötr · 0.05%+ long overcrowding · negatif short baskısı",
    "open_interest":       "Tüm borsalar açık pozisyon (milyar USD) — fiyatla birlikte artış sağlıklı",
    "long_liquidations":   "24 saatlik long tasfiye hacmi (USD milyon) — yüksek değer = long flush / downside stres",
    "short_liquidations":  "24 saatlik short tasfiye hacmi (USD milyon) — yüksek değer = short squeeze",
    "coinbase_premium":    "Coinbase - Binance fiyat farkı; pozitif = ABD kurumsal alımı · negatif = ABD satımı",
    "etf_flow_cumulative": "Bitcoin spot ETF kümülatif toplam akış (milyar USD) — yükselen trend güçlü kurumsal talep",
    "notes":               "Serbest not; bültene eklenmez",
}


# ── Internal helpers ──────────────────────────────────────────────────────────

def _load_from_file() -> dict[str, Any]:
    """JSON dosyasından kayıtları yükle. Hata → boş dict."""
    try:
        if _DATA_FILE.exists():
            return json.loads(_DATA_FILE.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        pass
    return {}


def _save_to_file(store: dict[str, Any]) -> None:
    """Dict'i JSON dosyasına yaz. Hata → sessizce yutulur."""
    try:
        _DATA_DIR.mkdir(parents=True, exist_ok=True)
        _DATA_FILE.write_text(json.dumps(store, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass


def _ensure_store() -> dict[str, Any]:
    """session_state'teki mağazayı başlat / dosyadan yükle."""
    if _SS_KEY not in st.session_state:
        st.session_state[_SS_KEY] = _load_from_file()
    return st.session_state[_SS_KEY]


def _today_key() -> str:
    return date.today().isoformat()  # "2026-06-04"


# ── Public API ────────────────────────────────────────────────────────────────

def save_entry(entry: dict[str, Any], entry_date: Optional[str] = None) -> None:
    """Günlük on-chain girdiyi depola."""
    store = _ensure_store()
    key   = entry_date or _today_key()
    # Temizle: NaN/Inf değerleri None'a çevir
    cleaned: dict[str, Any] = {}
    for k, v in entry.items():
        if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
            cleaned[k] = None
        else:
            cleaned[k] = v
    cleaned["_saved_at"] = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    store[key] = cleaned
    st.session_state[_SS_KEY] = store
    _save_to_file(store)


def load_entry(entry_date: Optional[str] = None) -> Optional[dict[str, Any]]:
    """Belirli tarihin (varsayılan: bugün) girişini döndür. Yoksa None."""
    store = _ensure_store()
    key   = entry_date or _today_key()
    return store.get(key)


def load_latest_entry() -> Optional[dict[str, Any]]:
    """En son kaydedilen girişi döndür (tarihten bağımsız)."""
    store = _ensure_store()
    if not store:
        return None
    latest_key = max(store.keys())
    return store[latest_key]


def load_all_entries() -> dict[str, dict]:
    """Tüm kayıtları {tarih: entry} olarak döndür."""
    return dict(_ensure_store())


def delete_entry(entry_date: str) -> bool:
    """Belirli tarihin girişini sil. Başarılı ise True."""
    store = _ensure_store()
    if entry_date in store:
        del store[entry_date]
        st.session_state[_SS_KEY] = store
        _save_to_file(store)
        return True
    return False


def has_today_entry() -> bool:
    """Bugün için veri girilmiş mi?"""
    store = _ensure_store()
    return _today_key() in store


def entry_count() -> int:
    """Toplam kayıt sayısı."""
    return len(_ensure_store())


def get_metric_safe(entry: Optional[dict], key: str) -> Optional[float]:
    """Girdiden float metrik çek; None / non-numeric → None."""
    if entry is None:
        return None
    v = entry.get(key)
    if v is None:
        return None
    try:
        f = float(v)
        return None if (math.isnan(f) or math.isinf(f)) else f
    except (TypeError, ValueError):
        return None
