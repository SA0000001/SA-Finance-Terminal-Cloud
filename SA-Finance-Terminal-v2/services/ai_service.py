import re

from openai import OpenAI

from prompts.strategy_report import build_strategy_report_prompt


def build_openrouter_client(api_key: str) -> OpenAI:
    return OpenAI(base_url="https://openrouter.ai/api/v1", api_key=api_key)


def _safe(value, fallback: str = "-") -> str:
    if value in (None, "", [], {}):
        return fallback
    return str(value)


def _parse_percent(value) -> float | None:
    if value in (None, "", "-", "Veri bekleniyor"):
        return None
    text = str(value).replace("%", "").replace(",", "").strip()
    try:
        return float(text)
    except ValueError:
        return None


def _parse_compact_number(value) -> float | None:
    if value in (None, "", "-", "Veri bekleniyor"):
        return None
    text = str(value).replace("$", "").replace(",", "").strip().upper()
    multiplier = 1.0
    if text.endswith("T"):
        multiplier = 1e12
        text = text[:-1]
    elif text.endswith("B"):
        multiplier = 1e9
        text = text[:-1]
    elif text.endswith("M"):
        multiplier = 1e6
        text = text[:-1]
    try:
        return float(text) * multiplier
    except ValueError:
        return None


def _change_phrase(value) -> str:
    pct = _parse_percent(value)
    if pct is None:
        return _safe(value)
    direction = "artis" if pct > 0 else "dususte" if pct < 0 else "yatay"
    if pct == 0:
        return "%0.00 yatay"
    return f"%{abs(pct):.2f} {direction}"


def _relative_altcoin_summary(data: dict, period_key: str) -> str:
    btc_move = _parse_percent(data.get(f"BTC_{period_key}"))
    if btc_move is None:
        return "-"
    labels = []
    for sym in ("ETH", "SOL", "BNB", "XRP", "ADA", "AVAX", "DOT", "LINK"):
        alt_move = _parse_percent(data.get(f"{sym}_{period_key}"))
        if alt_move is None:
            continue
        diff = alt_move - btc_move
        tone = "BTC'den guclu" if diff > 0.35 else "BTC'ye yakin" if diff >= -0.35 else "BTC'den zayif"
        labels.append(f"{sym} {data.get(f'{sym}_{period_key}', '-')} ({tone}, {diff:+.2f} puan)")
    return "; ".join(labels) if labels else "-"


def _breadth_ratio_summary(data: dict) -> str:
    total = data.get("TOTAL_CAP_NUM") or _parse_compact_number(data.get("TOTAL_CAP"))
    total2 = data.get("TOTAL2_CAP_NUM") or _parse_compact_number(data.get("TOTAL2_CAP"))
    total3 = data.get("TOTAL3_CAP_NUM") or _parse_compact_number(data.get("TOTAL3_CAP"))
    others = data.get("OTHERS_CAP_NUM") or _parse_compact_number(data.get("OTHERS_CAP"))
    if not total:
        return "-"
    parts = []
    if total2:
        parts.append(f"TOTAL2/TOTAL %{(total2 / total) * 100:.1f}")
    if total3:
        parts.append(f"TOTAL3/TOTAL %{(total3 / total) * 100:.1f}")
    if others is not None:
        parts.append(f"OTHERS/TOTAL %{(others / total) * 100:.1f}")
    return " | ".join(parts) if parts else "-"


def _normalize_content_part(part) -> str:
    if part is None:
        return ""
    if isinstance(part, str):
        return part
    if isinstance(part, dict):
        for key in ("text", "content", "value", "output_text"):
            value = part.get(key)
            if isinstance(value, list):
                normalized = _normalize_content(value)
                if normalized:
                    return normalized
            if value not in (None, ""):
                return str(value)
        return ""
    for attr in ("text", "content", "value", "output_text"):
        value = getattr(part, attr, None)
        if isinstance(value, list):
            normalized = _normalize_content(value)
            if normalized:
                return normalized
        if value not in (None, ""):
            return str(value)
    return ""


def _normalize_content(content) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(part for part in (_normalize_content_part(item) for item in content) if part).strip()
    return _normalize_content_part(content)


def _extract_tagged_section(text, tag: str) -> str:
    normalized_text = _normalize_content(text)
    pattern = re.compile(rf"<{tag}>\s*(.*?)\s*</{tag}>", re.IGNORECASE | re.DOTALL)
    match = pattern.search(normalized_text or "")
    return match.group(1).strip() if match else ""


def _fallback_x_lead(data: dict, analytics: dict) -> str:
    return (
        f"Makro Bulten | BTC {_safe(data.get('BTC_P'))}, 24s {_safe(data.get('BTC_C'))}. "
        f"DXY {_safe(data.get('DXY'))}, US10Y {_safe(data.get('US10Y'))}, VIX {_safe(data.get('VIX'))}; "
        f"ETF {_safe(data.get('ETF_FLOW_TOTAL'))}. Destek {_safe(data.get('Sup_Wall'))}, direnc {_safe(data.get('Res_Wall'))}."
    )[:280]


def _fallback_x_thread(data: dict, analytics: dict) -> str:
    scores = analytics.get("scores", {})
    weekly_alt_summary = _relative_altcoin_summary(data, "7D")
    items = [
        f"1/5 Rejim {scores.get('overall', '-')}/100. Ana cikarim: {_safe(scores.get('summary'))}. Bias {_safe(scores.get('bias'))}.",
        f"2/5 Makro: SP500 {_safe(data.get('SP500'))} ({_safe(data.get('SP500_C'))}), NASDAQ {_safe(data.get('NASDAQ'))} ({_safe(data.get('NASDAQ_C'))}), DXY {_safe(data.get('DXY'))}, US10Y {_safe(data.get('US10Y'))}, VIX {_safe(data.get('VIX'))}.",
        f"3/5 BTC ve turev: BTC {_safe(data.get('BTC_P'))} | 24s {_safe(data.get('BTC_C'))} | 7g {_safe(data.get('BTC_7D'))}; funding {_safe(data.get('FR'))}, OI {_safe(data.get('OI'))}, L/S {_safe(data.get('LS_Ratio'))}, Taker {_safe(data.get('Taker'))}.",
        f"4/5 Flow ve breadth: ETF {_safe(data.get('ETF_FLOW_TOTAL'))}, Stable.C.D {_safe(data.get('STABLE_C_D'))}, USDT.D {_safe(data.get('USDT_D'))}; {_breadth_ratio_summary(data)}. Altcoinlerin BTC'ye gore 7g dagilimi: {weekly_alt_summary}.",
        f"5/5 Seviyeler: destek {_safe(data.get('Sup_Wall'))}, direnc {_safe(data.get('Res_Wall'))}. Invalidate: {_safe(' | '.join(scores.get('invalidate_conditions', [])[:1]))}",
    ]
    return "\n".join(items)


def _fallback_terminal_report(data: dict, brief: dict, analytics: dict) -> str:
    scores = analytics.get("scores", {})
    participation = scores.get("participation", {})
    macro_breadth = participation.get("subfactors", {}).get("macro", {})
    crypto_breadth = participation.get("subfactors", {}).get("crypto", {})
    news = data.get("NEWS", [])
    top_news = news[0].get("title") if news else "-"
    weekly_alt_summary = _relative_altcoin_summary(data, "7D")
    daily_alt_summary = _relative_altcoin_summary(data, "C")
    breadth_ratio_summary = _breadth_ratio_summary(data)
    return "\n".join(
        [
            "### SA Finance Alpha Makro Bulteni Giris",
            f"Gunun ana cercevesinde BTC {_safe(data.get('BTC_P'))} seviyesinde islem gorurken, piyasa resmi tek bir etikete indirgenmek yerine likidite, oynaklik ve katilim uzerinden okunmali. Bu not, makro ortam ile kripto internallerini ayni karar akisinda birlestirir.",
            "",
            "### Gunluk Harita ve Ana Cikarim",
            f"Gunun ana surucusu {_safe(scores.get('dominant_driver'))}; zayif halka ise {_safe(scores.get('weakest_driver'))}. Temel davranis cizgisi {_safe(scores.get('bias'))}. Neden onemli: ana surucu ile zayif halka ayni anda bozulursa gorus hizla kirilganlasir.",
            "",
            "### Makro Ortam ve Risk Istahi",
            f"Makro tarafta DXY {_safe(data.get('DXY'))} ({_change_phrase(data.get('DXY_C'))}), ABD 10Y {_safe(data.get('US10Y'))} ({_change_phrase(data.get('US10Y_C'))}) ve VIX {_safe(data.get('VIX'))} ({_change_phrase(data.get('VIX_C'))}) birlikte okundugunda risk istahi temkinli ama tamamen bozulmus degil. SP500 {_safe(data.get('SP500'))} ({_safe(data.get('SP500_C'))}) ve NASDAQ {_safe(data.get('NASDAQ'))} ({_safe(data.get('NASDAQ_C'))}) riskli varliklara taban verdigini gosterirken, DAX {_safe(data.get('DAX'))} ve NIKKEI {_safe(data.get('NIKKEI'))} tarafindaki ayrisma global teyidin ne kadar guclu oldugunu belirliyor. Emtia tarafinda altin {_safe(data.get('GOLD'))} ({_safe(data.get('GOLD_C'))}), gumus {_safe(data.get('SILVER'))} ({_safe(data.get('SILVER_C'))}) ve petrol {_safe(data.get('OIL'))} ({_safe(data.get('OIL_C'))}) fiyatlamasi; hem enflasyon beklentisi hem de buyume algisi icin ikinci kontrol alani olmaya devam ediyor. Neden onemli: dolar, faiz ve vol ayni anda sertlesirse kriptodaki yapici zemin hizla incelir.",
            "",
            "### BTC, Turev ve Order Book Analizi",
            f"BTC {_safe(data.get('BTC_P'))} seviyesinde; son 24 saatte {_safe(data.get('BTC_C'))}, son 7 gunde ise {_safe(data.get('BTC_7D'))} performans sergiledi. BTC dominansi {_safe(data.get('Dom'))}, ETH dominansi {_safe(data.get('ETH_Dom'))} ile birlikte okundugunda liderligin ne kadar genele yayildigi daha netlesiyor. Turev tarafta OI {_safe(data.get('OI'))}, funding {_safe(data.get('FR'))}, taker {_safe(data.get('Taker'))}, L/S {_safe(data.get('LS_Ratio'))}, long %{_safe(data.get('Long_Pct'))} ve short %{_safe(data.get('Short_Pct'))} kaldirac yogunlugunun halen anlamli olduguna isaret ediyor. Order book tarafinda destek {_safe(data.get('Sup_Wall'))}, direnc {_safe(data.get('Res_Wall'))}; birlesik sinyal {_safe(data.get('ORDERBOOK_SIGNAL'))} ve detay {_safe(data.get('ORDERBOOK_SIGNAL_DETAIL'))}. Neden onemli: yuksek OI ile daralan alan, hem squeeze hem de likidasyon zinciri riskini buyutur.",
            "",
            "### ETF, Stablecoin ve Altcoinler",
            f"ETF tarafinda {_safe(data.get('ETF_FLOW_DATE'))} tarihli toplam net akim {_safe(data.get('ETF_FLOW_TOTAL'))} ve kaynak {_safe(data.get('ETF_FLOW_SOURCE'))}. Stablecoin tarafinda toplam buyukluk {_safe(data.get('Total_Stable'))}, USDT {_safe(data.get('USDT_MCap'))}, USDC {_safe(data.get('USDC_MCap'))}, DAI {_safe(data.get('DAI_MCap'))}; Stable.C.D {_safe(data.get('STABLE_C_D'))}, USDT.D {_safe(data.get('USDT_D'))}, USDT'nin stablecoin icindeki payi {_safe(data.get('USDT_Dom_Stable'))}. Altcoin akiminda 7 gunluk tabloda BTC'ye gore goreli performans: {weekly_alt_summary}. Son 24 saatlik tabloda goreli dagilim: {daily_alt_summary}. Neden onemli: spot ETF talebi ve stablecoin likiditesi destek verirken altcoinlerin BTC'ye gore dagilimi risk istahinin ne kadar yayildigini gosterir.",
            "",
            "### Macro Breadth ve Crypto Breadth",
            f"Makro katilim tarafinda macro breadth {_safe(macro_breadth.get('score'))}/100 ile buyuk endekslerin ve proxy ETF'lerin harekete ne kadar genis tabanli katildigini olcuyor. Kripto tarafinda crypto breadth {_safe(crypto_breadth.get('score'))}/100 ve composite participation {_safe(participation.get('score'))}/100; sermayenin BTC disina yayilip yayilmadigini gosteriyor. Ham oranlara bakildiginda {breadth_ratio_summary}; BTC dominansi {_safe(data.get('Dom'))}, ETH dominansi {_safe(data.get('ETH_Dom'))}. Neden onemli: fiyat yukselirken katilim daralirsa hareket daha kirilgan ve daha secici hale gelir.",
            "",
            "### Ekonomik Takvim ve Olasi Etkiler",
            f"Takvim kaynagi {_safe(data.get('ECONOMIC_CALENDAR_SOURCE'))}. En yakin yuksek etkili veriler, faiz ve dolar beklentileri uzerinden once DXY/VIX'i, ardindan da BTC oynakligini etkileyebilir. Neden onemli: veri surprizi, spot akim ve turev konumlanmasinin yonunu ayni gun icinde degistirebilir.",
            "",
            "### Onemli Haberler ve Piyasa Yorumu",
            f"Haber akisinin ana basligi: {_safe(top_news)}. Burada onemli olan, haberin tek basina pozitif ya da negatif olmasindan cok ETF akisi, stablecoin buyuklugu ve order book teyidiyle birlikte okunmasi. Neden onemli: haber destekli ama akis teyitsiz hareketler daha kisa omurlu olur.",
            "",
            "### Long / Short / Bekle ve Kritik Riskler",
            f"Long yalnizca destek bolgesi korunur, ETF akisi zayiflamaz ve funding/OI dengesi daha da tasmazsa anlamli. Short yalnizca {_safe(scores.get('weakest_driver'))} tarafindaki bozulma derinlesir, VIX/DXY sertlesir ve fiyat destek altina sarkarsa daha temizlesir. Bekle modu ise fiyat kritik seviyeler arasinda sikisiyor, order book teyidi dagiliyor ve invalidate kosullari yakina geliyorsa daha sagliklidir. Kritik riskler: ETF akisinin zayiflamasi, volatilitenin yeniden yukselmesi, BTC dominansinin sert toparlanmasi ve altcoinlerde goreli zayifligin derinlesmesi.",
            "",
            "### Kritik Seviyeler, Invalidation ve Bugun Ne Izlenmeli",
            f"Destek {_safe(data.get('Sup_Wall'))}, direnc {_safe(data.get('Res_Wall'))}. Invalidate: {_safe(' | '.join(scores.get('invalidate_conditions', [])[:2]))}. Watch next: {_safe(' | '.join(scores.get('watch_next', [])[:3]))}",
        ]
    )


def _parse_report_payload(content, data: dict, brief: dict, analytics: dict) -> dict:
    normalized_content = _normalize_content(content)
    terminal_report = _extract_tagged_section(content, "terminal_report")
    x_lead = _extract_tagged_section(content, "x_lead")
    x_thread = _extract_tagged_section(content, "x_thread")

    return {
        "terminal_report": terminal_report or _fallback_terminal_report(data, brief, analytics),
        "x_lead": x_lead or _fallback_x_lead(data, analytics),
        "x_thread": x_thread or _fallback_x_thread(data, analytics),
        "raw": normalized_content.strip(),
    }


def generate_strategy_report(
    client: OpenAI,
    data: dict,
    *args,
    brief: dict | None = None,
    analytics: dict | None = None,
    alerts: list[dict] | None = None,
    health_summary: dict | None = None,
    model: str = "google/gemini-2.5-flash",
    depth: str = "Orta",
) -> dict:
    if args:
        remaining = list(args)
        if remaining and isinstance(remaining[0], dict):
            brief = remaining.pop(0)
        if remaining and isinstance(remaining[0], dict):
            analytics = remaining.pop(0)
        if remaining and isinstance(remaining[0], list):
            alerts = remaining.pop(0)
        if remaining and isinstance(remaining[0], dict):
            health_summary = remaining.pop(0)
        if remaining and isinstance(remaining[0], str):
            model = remaining.pop(0)
        if remaining and isinstance(remaining[0], str):
            depth = remaining.pop(0)

    brief = brief or {}
    analytics = analytics or {}
    alerts = alerts or []
    health_summary = health_summary or {}

    prompt = build_strategy_report_prompt(
        data,
        brief=brief,
        analytics=analytics,
        alerts=alerts,
        health_summary=health_summary,
        depth=depth,
    )
    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": "You are a macro-crypto bulletin writer. Follow the requested tags exactly and avoid extra prefacing text.",
            },
            {"role": "user", "content": prompt},
        ],
        max_tokens=8000,
    )
    content = _normalize_content(response.choices[0].message.content)
    return _parse_report_payload(content, data, brief, analytics)
