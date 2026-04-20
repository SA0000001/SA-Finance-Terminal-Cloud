from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

from domain.analytics import build_alerts, build_analytics_payload
from domain.market_brief import build_market_brief
from services.ai_service import _fallback_terminal_report, build_openrouter_client, generate_strategy_report
from services.health import build_health_summary
from services.market_data import load_terminal_data
from services.preferences import DEFAULT_PREFERENCES, load_preferences

DEFAULT_MODEL = "google/gemini-2.5-flash"
DEFAULT_DEPTH = "Derin"
TELEGRAM_MESSAGE_LIMIT = 2800
ISTANBUL_TZ = ZoneInfo("Europe/Istanbul")

# Rapor arsivi dizini
REPORTS_DIR = Path("reports")
ARCHIVE_DIR = REPORTS_DIR / "archive"


@dataclass(frozen=True)
class RuntimeConfig:
    openrouter_api_key: str
    telegram_token: str
    telegram_chat_id: str
    fred_api_key: str
    report_depth: str
    openrouter_model: str
    slot: str  # "1630" veya "2245"


def _safe(value, fallback: str = "-") -> str:
    if value in (None, "", [], {}):
        return fallback
    return str(value)


def load_runtime_config() -> RuntimeConfig:
    openrouter_api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    telegram_token     = os.getenv("TELEGRAM_TOKEN", "").strip()
    telegram_chat_id   = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    fred_api_key       = os.getenv("FRED_API_KEY", "").strip()
    report_depth       = os.getenv("REPORT_DEPTH", DEFAULT_DEPTH).strip() or DEFAULT_DEPTH
    openrouter_model   = os.getenv("OPENROUTER_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL
    slot               = os.getenv("BULLETIN_SLOT", "2245").strip() or "2245"

    missing = [
        name
        for name, value in (
            ("OPENROUTER_API_KEY", openrouter_api_key),
            ("TELEGRAM_TOKEN", telegram_token),
            ("TELEGRAM_CHAT_ID", telegram_chat_id),
        )
        if not value
    ]
    if missing:
        raise RuntimeError(f"Eksik zorunlu environment variable: {', '.join(missing)}")

    return RuntimeConfig(
        openrouter_api_key=openrouter_api_key,
        telegram_token=telegram_token,
        telegram_chat_id=telegram_chat_id,
        fred_api_key=fred_api_key,
        report_depth=report_depth,
        openrouter_model=openrouter_model,
        slot=slot,
    )


def build_bulletin_context(config: RuntimeConfig) -> dict:
    preferences = load_preferences()
    thresholds  = preferences.get("thresholds") or DEFAULT_PREFERENCES["thresholds"]
    data        = load_terminal_data(config.fred_api_key)
    return {
        "data":           data,
        "brief":          build_market_brief(data),
        "analytics":      build_analytics_payload(data),
        "alerts":         build_alerts(data, thresholds),
        "health_summary": build_health_summary(data.get("_health", {})),
    }


def normalize_report_payload(report, context: dict) -> dict:
    fallback = _fallback_terminal_report(context["data"], context["brief"], context["analytics"])
    if not isinstance(report, dict):
        return {"terminal_report": fallback, "raw": str(report or "").strip()}
    return {
        "terminal_report": str(report.get("terminal_report") or fallback),
        "x_lead":   str(report.get("x_lead") or ""),
        "x_thread": str(report.get("x_thread") or ""),
        "raw":      str(report.get("raw") or "").strip(),
    }


def generate_bulletin_report(client, context: dict, config: RuntimeConfig) -> tuple[dict, bool]:
    try:
        report = generate_strategy_report(
            client,
            context["data"],
            context["brief"],
            context["analytics"],
            context["alerts"],
            context["health_summary"],
            model=config.openrouter_model,
            depth=config.report_depth,
        )
        return normalize_report_payload(report, context), False
    except Exception as exc:
        print(f"AI raporu uretilemedi, fallback kullaniliyor: {exc}")
        return normalize_report_payload(None, context), True


# ??? JSON KAYIT / ARSIV ??????????????????????????????????????????????????????

def save_report_to_disk(report: dict, context: dict, config: RuntimeConfig, now: datetime) -> None:
    """
    Raporu iki yere kaydeder:
      reports/latest_2245.json  - her zaman güncel
      reports/archive/2025-04-09_2245.json  - kalıcı arşiv
    
    Arşivde sadece 22:45 bültenleri saklanır (1630 latest olarak tutulur ama arşive yazılmaz).
    """
    REPORTS_DIR.mkdir(exist_ok=True)
    ARCHIVE_DIR.mkdir(exist_ok=True)

    scores = context["analytics"].get("scores", {})
    payload = {
        "slot":      config.slot,
        "timestamp": now.isoformat(),
        "date":      now.strftime("%Y-%m-%d"),
        "time_label": "16:30" if config.slot == "1630" else "22:45",
        "regime": {
            "overlay":         _safe(scores.get("overall")),
            "score":           _safe(scores.get("overall")),
            "dominant_driver": _safe(scores.get("dominant_driver")),
            "bias":            _safe(scores.get("bias")),
            "fragility":       _safe(scores.get("fragility", {}).get("label")),
            "confidence":      _safe(scores.get("confidence")),
        },
        "market": {
            "btc_price":    _safe(context["data"].get("BTC_P")),
            "btc_change":   _safe(context["data"].get("BTC_C")),
            "support":      _safe(context["data"].get("Sup_Wall")),
            "resistance":   _safe(context["data"].get("Res_Wall")),
            "etf_flow":     _safe(context["data"].get("ETF_FLOW_TOTAL")),
            "funding":      _safe(context["data"].get("FR")),
            "fng":          _safe(context["data"].get("FNG")),
        },
        "report": {
            "terminal_report": report.get("terminal_report", ""),
            "x_lead":          report.get("x_lead", ""),
            "x_thread":        report.get("x_thread", ""),
        },
        "fallback_used": report.get("fallback_used", False),
    }

    # Her zaman latest dosyasını güncelle
    latest_path = REPORTS_DIR / f"latest_{config.slot}.json"
    latest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Latest rapor kaydedildi: {latest_path}")

    # Sadece 22:45 bülteni arşive yazılır
    if config.slot == "2245":
        archive_path = ARCHIVE_DIR / f"{now.strftime('%Y-%m-%d')}_2245.json"
        archive_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Arsiv raporu kaydedildi: {archive_path}")


def load_latest_report(slot: str) -> dict | None:
    """Terminal tarafından kullanılır - en güncel raporu okur."""
    path = REPORTS_DIR / f"latest_{slot}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def list_archive_reports() -> list[dict]:
    """Arşivdeki tüm 22:45 raporlarını tarih azalan sırada döner."""
    if not ARCHIVE_DIR.exists():
        return []
    files = sorted(ARCHIVE_DIR.glob("*_2245.json"), reverse=True)
    reports = []
    for f in files:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            reports.append({
                "date":       data.get("date", f.stem.split("_")[0]),
                "timestamp":  data.get("timestamp", ""),
                "time_label": data.get("time_label", "22:45"),
                "regime":     data.get("regime", {}),
                "market":     data.get("market", {}),
                "report":     data.get("report", {}),
            })
        except Exception:
            continue
    return reports


# ??? TELEGRAM ????????????????????????????????????????????????????????????????

def build_telegram_summary(context: dict, config: RuntimeConfig | None = None, fallback_used: bool = False, now: datetime | None = None) -> str:
    now    = now or datetime.now(ISTANBUL_TZ)
    data   = context["data"]
    scores = context["analytics"].get("scores", {})
    slot_label = ("16:30" if config.slot == "1630" else "22:45") if config else "22:45"
    invalidate = " | ".join(scores.get("invalidate_conditions", [])[:1]) or _safe(scores.get("weakest_driver"))

    lines = [
        f"*SA Finance Alpha | Gunluk Makro Bulten {slot_label}*",
        now.strftime("%d.%m.%Y %H:%M TRT"),
        f"Rejim: {_safe(scores.get('overlay'))} ({_safe(scores.get('overall'))}/100)",
        f"BTC: {_safe(data.get('BTC_P'))} | 24s {_safe(data.get('BTC_C'))}",
        f"Ana surucu: {_safe(scores.get('dominant_driver'))}",
        f"Destek / Direnc: {_safe(data.get('Sup_Wall'))} / {_safe(data.get('Res_Wall'))}",
        f"Ana risk: {invalidate}",
    ]
    if fallback_used:
        lines.append("Not: AI yerine fallback bulten kullanildi.")
    return "\n".join(lines)


def format_terminal_report_for_telegram(report_text: str) -> str:
    formatted_lines = []
    for raw_line in (report_text or "").splitlines():
        line = raw_line.strip()
        if not line:
            formatted_lines.append("")
            continue
        if line.startswith("### "):
            formatted_lines.append(f"*{line[4:].strip()}*")
            continue
        if line.startswith("- "):
            formatted_lines.append(f"- {line[2:].strip()}")
            continue
        formatted_lines.append(line)
    text = "\n".join(formatted_lines).strip()
    while "\n\n\n" in text:
        text = text.replace("\n\n\n", "\n\n")
    return text


def split_telegram_message(text: str, limit: int = TELEGRAM_MESSAGE_LIMIT, reserved: int = 0) -> list[str]:
    remaining = (text or "").strip()
    if not remaining:
        return []
    chunk_limit = max(1, limit - max(reserved, 0))
    parts = []
    while remaining:
        if len(remaining) <= chunk_limit:
            parts.append(remaining)
            break
        split_at = remaining.rfind("\n\n", 0, chunk_limit)
        if split_at == -1:
            split_at = remaining.rfind("\n", 0, chunk_limit)
        if split_at == -1:
            split_at = chunk_limit
        parts.append(remaining[:split_at].strip())
        remaining = remaining[split_at:].strip()
    return parts


def send_telegram_text(token: str, chat_id: str, text: str, *, prefer_markdown: bool = True) -> dict:
    payload = {"chat_id": chat_id, "text": text, "disable_web_page_preview": True}
    url     = f"https://api.telegram.org/bot{token}/sendMessage"
    if prefer_markdown:
        response = requests.post(url, json={**payload, "parse_mode": "Markdown"}, timeout=15)
        if response.ok:
            return response.json().get("result", {})
    fallback = requests.post(url, json=payload, timeout=15)
    if fallback.ok:
        return fallback.json().get("result", {})
    raise RuntimeError(f"Telegram sendMessage failed: {fallback.text}")


def delete_telegram_message(token: str, chat_id: str, message_id: int) -> bool:
    url      = f"https://api.telegram.org/bot{token}/deleteMessage"
    response = requests.post(url, json={"chat_id": chat_id, "message_id": message_id}, timeout=15)
    return response.ok


def build_failure_notification(error_text: str, now: datetime | None = None) -> str:
    now    = now or datetime.now(ISTANBUL_TZ)
    lowered = error_text.lower()
    reason  = "Telegram mesaj limiti asildi." if "message is too long" in lowered else error_text.replace("\n", " ").strip()[:180]
    return "\n".join(["Gunluk Makro Bulten gonderilemedi.", now.strftime("%d.%m.%Y %H:%M TRT"), f"Neden: {reason}"])


def send_daily_bulletin(token: str, chat_id: str, summary_text: str, terminal_report: str):
    report_text  = format_terminal_report_for_telegram(terminal_report)
    report_parts = split_telegram_message(report_text, reserved=32)
    total_parts  = len(report_parts)
    sent_ids: list[int] = []

    if not report_parts:
        send_telegram_text(token, chat_id, build_failure_notification("Makro Bulten bos uretildi."), prefer_markdown=False)
        raise RuntimeError("Makro Bulten bos uretildi.")

    try:
        for index, part in enumerate(report_parts, start=1):
            header = f"*Makro Bulten {index}/{total_parts}*\n\n" if total_parts > 1 else "*Makro Bulten*\n\n"
            result = send_telegram_text(token, chat_id, f"{header}{part}", prefer_markdown=True)
            msg_id = result.get("message_id") if isinstance(result, dict) else None
            if isinstance(msg_id, int):
                sent_ids.append(msg_id)
        send_telegram_text(token, chat_id, summary_text, prefer_markdown=True)
    except Exception as exc:
        for mid in reversed(sent_ids):
            try:
                delete_telegram_message(token, chat_id, mid)
            except Exception:
                pass
        try:
            send_telegram_text(token, chat_id, build_failure_notification(str(exc)), prefer_markdown=False)
        except Exception:
            pass
        raise


# ??? MAIN ????????????????????????????????????????????????????????????????????

def main():
    config = load_runtime_config()
    now    = datetime.now(ISTANBUL_TZ)
    print(f"Slot: {config.slot} | {now.strftime('%d.%m.%Y %H:%M TRT')}")

    print("Terminal verileri yukleniyor...")
    context = build_bulletin_context(config)

    print("Makro Bulten uretiliyor...")
    client = build_openrouter_client(config.openrouter_api_key)
    report, fallback_used = generate_bulletin_report(client, context, config)
    report["fallback_used"] = fallback_used

    print("Rapor diske kaydediliyor...")
    save_report_to_disk(report, context, config, now)

    print("Telegram ozeti hazirlaniyor...")
    summary_text = build_telegram_summary(context, config, fallback_used=fallback_used, now=now)

    print("Telegram gonderimi basliyor...")
    send_daily_bulletin(config.telegram_token, config.telegram_chat_id, summary_text, report["terminal_report"])
    print("Tamamlandi.")


if __name__ == "__main__":
    main()
