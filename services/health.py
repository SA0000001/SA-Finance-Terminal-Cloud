from __future__ import annotations

import html
import re
from datetime import datetime, timezone
from urllib.parse import urlsplit


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def stale_after_for_source(source: str) -> int:
    source_lower = source.lower()
    if any(
        keyword in source_lower
        for keyword in ("order book", "funding", "open interest", "taker", "long/short", "usdt.d", "market cap")
    ):
        return 300
    if any(keyword in source_lower for keyword in ("etf flow", "farside")):
        return 43200
    if any(keyword in source_lower for keyword in ("news", "coindesk", "cryptocompare", "fng")):
        return 1800
    if any(keyword in source_lower for keyword in ("fred", "stablecoin")):
        return 21600
    if "blockchain" in source_lower:
        return 3600
    return 900


class HealthRecorder:
    def __init__(self):
        self._entries: dict[str, dict] = {}

    def success(self, source: str, latency_ms: float | None = None, stale_after_seconds: int | None = None):
        now = utc_now_iso()
        self._entries[source] = {
            "source": source,
            "ok": True,
            "latency_ms": round(latency_ms, 1) if latency_ms is not None else None,
            "fetched_at": now,
            "last_success_at": now,
            "error": "",
            "stale_after_seconds": stale_after_seconds or stale_after_for_source(source),
        }

    def failure(self, source: str, error: str, latency_ms: float | None = None, stale_after_seconds: int | None = None):
        self._entries[source] = {
            "source": source,
            "ok": False,
            "latency_ms": round(latency_ms, 1) if latency_ms is not None else None,
            "fetched_at": utc_now_iso(),
            "last_success_at": None,
            "error": error,
            "stale_after_seconds": stale_after_seconds or stale_after_for_source(source),
        }

    def export(self) -> dict[str, dict]:
        return dict(self._entries)


def is_stale(entry: dict, now: datetime | None = None) -> bool:
    if not entry.get("last_success_at"):
        return False
    now = now or datetime.now(timezone.utc)
    last_success = parse_iso_datetime(entry.get("last_success_at"))
    if last_success is None:
        return False
    threshold = entry.get("stale_after_seconds") or stale_after_for_source(entry.get("source", ""))
    return (now - last_success).total_seconds() > threshold


def merge_source_health(previous: dict[str, dict] | None, latest: dict[str, dict] | None) -> dict[str, dict]:
    previous = previous or {}
    latest = latest or {}
    merged: dict[str, dict] = {}
    now = datetime.now(timezone.utc)

    for source, entry in latest.items():
        merged_entry = dict(previous.get(source, {}))
        merged_entry.update(entry)
        merged_entry["source"] = source
        merged_entry["stale_after_seconds"] = (
            entry.get("stale_after_seconds")
            or merged_entry.get("stale_after_seconds")
            or stale_after_for_source(source)
        )

        if entry.get("ok"):
            merged_entry["last_success_at"] = (
                entry.get("last_success_at")
                or entry.get("fetched_at")
                or previous.get(source, {}).get("last_success_at")
            )
        else:
            merged_entry["last_success_at"] = entry.get("last_success_at") or previous.get(source, {}).get(
                "last_success_at"
            )

        merged_entry["stale"] = is_stale(merged_entry, now)
        merged[source] = merged_entry

    return merged


def _format_timestamp(value: str | None) -> str:
    parsed = parse_iso_datetime(value)
    if parsed is None:
        return "Never"
    return parsed.astimezone().strftime("%d.%m %H:%M:%S")


_SENSITIVE_QUERY_RE = re.compile(r"([?&](?:api_key|apikey|token|access_token|key)=)[^&\s]+", re.IGNORECASE)
_URL_RE = re.compile(r"https?://[^\s]+", re.IGNORECASE)
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_HEALTH_ERROR_FRAGMENT_RE = re.compile(
    r'health-(?:issue-error|source-health-detail)">([^<]+)', re.IGNORECASE
)


def normalize_health_display_text(value) -> str:
    if value in (None, ""):
        return "-"

    if isinstance(value, dict):
        parts = [
            normalize_health_display_text(item_value)
            for item_value in value.values()
            if normalize_health_display_text(item_value) != "-"
        ]
        return " | ".join(parts) if parts else "-"

    if isinstance(value, (list, tuple, set)):
        parts = [
            normalize_health_display_text(item_value)
            for item_value in value
            if normalize_health_display_text(item_value) != "-"
        ]
        return " | ".join(parts) if parts else "-"

    text = html.unescape(str(value)).replace("\r", " ").strip()
    if not text:
        return "-"

    html_matches = [match.strip() for match in _HEALTH_ERROR_FRAGMENT_RE.findall(text) if match.strip()]
    if html_matches:
        text = " | ".join(html_matches)

    text = _HTML_TAG_RE.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text or "-"


def _shorten_url(url: str) -> str:
    try:
        parsed = urlsplit(url)
    except ValueError:
        return url
    path = parsed.path or ""
    return f"{parsed.netloc}{path}"


def _format_error_for_display(source: str, error: str | None) -> str:
    text = normalize_health_display_text(error)
    if text == "-":
        return "-"

    lowered = text.lower()
    if source == "TradingView Market Cap" and "market cap not found" in lowered:
        return "TradingView market cap metni parse edilemedi; CoinGecko fallback kullaniliyor."
    if source == "FairEconomy Calendar" and "429" in lowered:
        return "FairEconomy Calendar oran sinirina takildi (429); takvim gecici olarak kullanilamiyor."
    if source.startswith("FRED") and "500" in lowered:
        return "FRED gecici sunucu hatasi (500); son basarili veri korunuyor."

    text = _SENSITIVE_QUERY_RE.sub(r"\1[redacted]", text)
    text = _URL_RE.sub(lambda match: _shorten_url(match.group(0)), text)
    text = normalize_health_display_text(text)
    return text


_TV_FALLBACK_SOURCES = {
    "TradingView Commodities",
    "TradingView FX",
    "TradingView Indices",
}


def build_health_summary(health_state: dict[str, dict]) -> dict:
    entries = []
    stale_sources = []
    failed_sources = []

    for source in sorted(health_state):
        entry = dict(health_state[source])
        status = "OK"
        if entry.get("stale"):
            status = "STALE"
            stale_sources.append(source)
        elif not entry.get("ok"):
            status = "FAIL"
            # TV fallback'lar yfinance ile karşılanıyor; sorun sayılmaz
            if source not in _TV_FALLBACK_SOURCES:
                failed_sources.append(source)

        # TV fallback FAIL satırlarını tablodan da gizle
        if status == "FAIL" and source in _TV_FALLBACK_SOURCES:
            continue

        entries.append(
            {
                "Kaynak": source,
                "Durum": status,
                "Gecikme": f"{entry['latency_ms']:.0f} ms" if entry.get("latency_ms") is not None else "-",
                "Son basarili": _format_timestamp(entry.get("last_success_at")),
                "Hata": _format_error_for_display(source, entry.get("error", "")),
            }
        )

    return {
        "total_sources": len(entries),
        "healthy_sources": sum(1 for item in entries if item["Durum"] == "OK"),
        "failed_sources": failed_sources,
        "stale_sources": stale_sources,
        "rows": entries,
    }
