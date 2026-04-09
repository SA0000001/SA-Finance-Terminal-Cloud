from datetime import datetime

import pytest

import notify
from notify import (
    ISTANBUL_TZ,
    TELEGRAM_MESSAGE_LIMIT,
    build_failure_notification,
    build_telegram_summary,
    delete_telegram_message,
    format_terminal_report_for_telegram,
    send_daily_bulletin,
    send_telegram_text,
    split_telegram_message,
)


def test_build_telegram_summary_includes_core_market_fields():
    context = {
        "data": {
            "BTC_P": "$68,077",
            "BTC_C": "0.04%",
            "Sup_Wall": "$67,700",
            "Res_Wall": "$69,600",
        },
        "analytics": {
            "scores": {
                "overlay": "Constructive Risk-On",
                "overall": 64,
                "dominant_driver": "Liquidity",
                "invalidate_conditions": ["ETF akisi zayiflar"],
            }
        },
    }

    summary = build_telegram_summary(
        context,
        now=datetime(2026, 4, 1, 21, 0, tzinfo=ISTANBUL_TZ),
    )

    assert "SA Finance Alpha | Gunluk Makro Bulten" in summary
    assert "01.04.2026 21:00 TRT" in summary
    assert "Rejim: Constructive Risk-On (64/100)" in summary
    assert "BTC: $68,077 | 24s 0.04%" in summary
    assert "Ana surucu: Liquidity" in summary
    assert "Destek / Direnc: $67,700 / $69,600" in summary
    assert "Ana risk: ETF akisi zayiflar" in summary


def test_format_terminal_report_for_telegram_formats_headings_and_bullets():
    raw = "### Baslik\n\n- Ilk madde\n- Ikinci madde\n\nNormal satir"

    formatted = format_terminal_report_for_telegram(raw)

    assert "*Baslik*" in formatted
    assert "- Ilk madde" in formatted
    assert "- Ikinci madde" in formatted
    assert "Normal satir" in formatted


def test_split_telegram_message_respects_limit_with_reserved_budget():
    text = "A" * 20 + "\n\n" + "B" * 20 + "\n\n" + "C" * 20

    parts = split_telegram_message(text, limit=35, reserved=5)

    assert len(parts) == 3
    assert all(len(part) <= 30 for part in parts)


def test_send_telegram_text_falls_back_to_plain_text(monkeypatch):
    calls = []

    class FakeResponse:
        def __init__(self, ok, payload):
            self.ok = ok
            self._payload = payload
            self.text = str(payload)

        def json(self):
            return self._payload

    def fake_post(url, json, timeout):
        calls.append({"url": url, "json": json, "timeout": timeout})
        if len(calls) == 1:
            return FakeResponse(False, {"ok": False})
        return FakeResponse(True, {"ok": True, "result": {"message_id": 42}})

    monkeypatch.setattr(notify.requests, "post", fake_post)

    result = send_telegram_text("token", "chat", "Merhaba", prefer_markdown=True)

    assert result["message_id"] == 42
    assert calls[0]["json"]["parse_mode"] == "Markdown"
    assert "parse_mode" not in calls[1]["json"]


def test_delete_telegram_message_returns_boolean(monkeypatch):
    class FakeResponse:
        def __init__(self, ok):
            self.ok = ok

    monkeypatch.setattr(notify.requests, "post", lambda *args, **kwargs: FakeResponse(True))
    assert delete_telegram_message("token", "chat", 10) is True

    monkeypatch.setattr(notify.requests, "post", lambda *args, **kwargs: FakeResponse(False))
    assert delete_telegram_message("token", "chat", 10) is False


def test_send_daily_bulletin_sends_report_before_summary(monkeypatch):
    sent = []

    def fake_send(token, chat_id, text, prefer_markdown=True):
        sent.append({"text": text, "prefer_markdown": prefer_markdown})
        return {"message_id": len(sent)}

    monkeypatch.setattr(notify, "send_telegram_text", fake_send)

    send_daily_bulletin(
        "token",
        "chat",
        "*Ozet*",
        "### Baslik\n\n- Ilk madde\n\nNormal satir",
    )

    assert sent[0]["text"].startswith("*Makro Bulten*")
    assert sent[-1]["text"] == "*Ozet*"


def test_send_daily_bulletin_rolls_back_and_sends_failure_note(monkeypatch):
    sent = []
    deleted = []
    summary_text = "*Ozet*"

    def fake_send(token, chat_id, text, prefer_markdown=True):
        sent.append({"text": text, "prefer_markdown": prefer_markdown})
        if len(sent) == 1:
            return {"message_id": 101}
        if len(sent) == 2:
            raise RuntimeError('Telegram sendMessage failed: {"ok":false,"error_code":400,"description":"Bad Request: message is too long"}')
        return {"message_id": 999}

    monkeypatch.setattr(notify, "send_telegram_text", fake_send)
    monkeypatch.setattr(notify, "delete_telegram_message", lambda token, chat_id, message_id: deleted.append(message_id) or True)

    with pytest.raises(RuntimeError, match="message is too long"):
        send_daily_bulletin(
            "token",
            "chat",
            summary_text,
            "A" * 6000,
        )

    assert deleted == [101]
    assert all(entry["text"] != summary_text for entry in sent)
    assert any("Gunluk Makro Bulten gonderilemedi." in entry["text"] for entry in sent)


def test_build_failure_notification_maps_long_message_error():
    note = build_failure_notification("Telegram sendMessage failed: message is too long")

    assert "Gunluk Makro Bulten gonderilemedi." in note
    assert "Telegram mesaj limiti asildi." in note


def test_send_daily_bulletin_keeps_each_payload_under_telegram_limit(monkeypatch):
    sent = []

    def fake_send(token, chat_id, text, prefer_markdown=True):
        sent.append(text)
        return {"message_id": len(sent)}

    monkeypatch.setattr(notify, "send_telegram_text", fake_send)

    send_daily_bulletin("token", "chat", "*Ozet*", "A" * 9000)

    assert sent[-1] == "*Ozet*"
    assert all(len(text) <= TELEGRAM_MESSAGE_LIMIT for text in sent[:-1])
