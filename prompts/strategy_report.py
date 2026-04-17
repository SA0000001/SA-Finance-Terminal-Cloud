import pandas as pd


DEPTH_RULES = {
    "Kisa": {
        "terminal_length": "350-500 kelime",
        "style": "Kisa ama research-note tonunda, net ve karar odakli yaz.",
    },
    "Orta": {
        "terminal_length": "550-800 kelime",
        "style": "Research note tonunda, sayisal, editoryal ve uygulanabilir yaz.",
    },
    "Derin": {
        "terminal_length": "800-1100 kelime",
        "style": "Detayli ama tekrar etmeyen, bolum disiplini guclu bir research note yaz.",
    },
}


def _safe(value, fallback: str = "-") -> str:
    if value in (None, "", [], {}):
        return fallback
    return str(value)


def _format_news(news: list[dict]) -> str:
    if not news:
        return "- Haber akisi su an yok"
    return "\n".join(
        f"- {_safe(item.get('title'))} | {_safe(item.get('source'))} | {_safe(item.get('time'))}"
        for item in news[:3]
    )


def _format_alerts(alerts: list[dict]) -> str:
    if not alerts:
        return "- Aktif alarm yok"
    return "\n".join(
        f"- {_safe(item.get('title'))}: {_safe(item.get('detail'))}"
        for item in alerts[:4]
    )


def _format_health(health_summary: dict) -> str:
    rows = health_summary.get("rows", [])
    if not rows:
        return "- Veri sagligi kaydi yok"
    problem_rows = [row for row in rows if row.get("Durum") != "OK"][:4]
    if not problem_rows:
        return (
            f"- Veri sagligi: {health_summary.get('healthy_sources', 0)} saglikli kaynak, "
            f"{len(health_summary.get('failed_sources', []))} fail, {len(health_summary.get('stale_sources', []))} stale"
        )
    return "\n".join(
        f"- {_safe(row.get('Kaynak'))}: {_safe(row.get('Durum'))} | {_safe(row.get('Detay'))}"
        for row in problem_rows
    )


def _format_calendar(calendar_events: list[dict]) -> str:
    if not calendar_events:
        return "- Calendar unavailable"
    return "\n".join(
        (
            f"- {_safe(event.get('date'))} {_safe(event.get('time'))} | {_safe(event.get('country'))} | "
            f"{_safe(event.get('impact'))} | {_safe(event.get('title'))} | "
            f"A:{_safe(event.get('actual'))} F:{_safe(event.get('forecast'))} P:{_safe(event.get('previous'))}"
        )
        for event in calendar_events[:3]
    )


def _format_brief(brief: dict) -> str:
    sections = []
    for key in ("regime", "liquidity", "positioning", "focus"):
        item = brief.get(key, {})
        why = " | ".join(item.get("why", [])) if item.get("why") else "-"
        sections.append(
            f"- {key}: {_safe(item.get('title'))} | badge: {_safe(item.get('badge'))} | why: {why}"
        )
    return "\n".join(sections)


def _format_scenarios(analytics: dict) -> str:
    scenarios = analytics.get("scenarios", [])
    if not scenarios:
        return "- Senaryo verisi yok"
    return "\n".join(
        f"- {_safe(item.get('Scenario'))}: {_safe(item.get('Trigger'))} | {_safe(item.get('Follow-through'))}"
        for item in scenarios[:3]
    )


def _format_factor_lines(scores: dict) -> str:
    factors = scores.get("factors", [])
    if not factors:
        return "- Faktor verisi yok"
    return "\n".join(
        (
            f"- {_safe(factor.get('label'))}: {_safe(factor.get('score'))}/100 | "
            f"delta7g {_safe(factor.get('delta_7d'))} | support {_safe(factor.get('primary_support'))} | "
            f"risk {_safe(factor.get('primary_risk'))}"
        )
        for factor in factors
    )


def _format_risk_on_off(analytics: dict) -> str:
    roo = analytics.get("risk_on_off", {})
    if not roo:
        return "- Risk On/Off verisi yok"
    tx = roo.get("cross_asset_transmission", {})
    tx_items = tx.get("items", [])
    tx_lines = " | ".join(
        f"{item['pair']} {item['display']} ({item['signal']})"
        for item in tx_items
    ) if tx_items else "-"
    drivers = " | ".join(
        f"{d['label']} {d['change']}" for d in roo.get("drivers", [])
    ) or "-"
    drags = " | ".join(
        f"{d['label']} {d['change']}" for d in roo.get("drags", [])
    ) or "-"
    return (
        f"- Global sinyal: {_safe(roo.get('global_signal'))} | Strict: {_safe(roo.get('strict_score'))}/100 | Live: {_safe(roo.get('live_score'))}/100\n"
        f"- Phase: {_safe(roo.get('phase'))} | Side bias: {_safe(roo.get('side_bias'))} | Confidence: {_safe(roo.get('confidence_tier'))}\n"
        f"- Playbook: {_safe(roo.get('playbook'))}\n"
        f"- Sync Q: {_safe(roo.get('sync_q'))} | Agree Q: {_safe(roo.get('agree_q'))} | Coverage: {_safe(roo.get('coverage'))}\n"
        f"- Drivers: {drivers}\n"
        f"- Drags: {drags}\n"
        f"- Cross-asset transmission: {_safe(tx.get('signal'))} | {tx_lines}"
    )


def _format_decision_verdict(analytics: dict) -> str:
    dec = analytics.get("decision", {})
    if not dec:
        return "- Karar verisi yok"
    verdict = dec.get("verdict", {})
    mqs = dec.get("mqs", {})
    ews = dec.get("ews", {})
    mqs_comps = " | ".join(
        f"{c['label']} {c['score']}/100"
        for c in mqs.get("components", [])
    ) or "-"
    ews_comps = " | ".join(
        f"{c['label']} {c['score']}/100"
        for c in ews.get("components", [])
    ) or "-"
    return (
        f"- Karar: {_safe(verdict.get('verdict'))} ({_safe(verdict.get('verdict_en'))})\n"
        f"- Özet: {_safe(verdict.get('summary'))}\n"
        f"- Aksiyon: {_safe(verdict.get('action'))}\n"
        f"- MQS: {_safe(mqs.get('score'))}/100 ({_safe(mqs.get('label'))}) | Güçlü: {_safe(mqs.get('strongest'))} | Zayıf: {_safe(mqs.get('weakest'))}\n"
        f"  Bileşenler: {mqs_comps}\n"
        f"- EWS: {_safe(ews.get('score'))}/100 ({_safe(ews.get('label'))}) | Güçlü: {_safe(ews.get('strongest'))} | Zayıf: {_safe(ews.get('weakest'))}\n"
        f"  Bileşenler: {ews_comps}\n"
        f"- Destek: {_safe(ews.get('support'))} | Direnç: {_safe(ews.get('resistance'))}"
    )


def _format_stock_fng(data: dict) -> str:
    sfng = data.get("STOCK_FNG", "-")
    sfng_num = data.get("STOCK_FNG_NUM", 0)
    sfng_vix = data.get("STOCK_FNG_VIX", "-")
    sfng_mom = data.get("STOCK_FNG_MOM", "-")
    sfng_brd = data.get("STOCK_FNG_BRD", "-")
    crypto_fng = data.get("FNG", "-")
    if sfng == "-":
        return f"- Stock F&G: veri yok | Crypto F&G: {crypto_fng}"
    return (
        f"- Stock Market F&G: {sfng}\n"
        f"  VIX bileşeni: {sfng_vix}/100 | Momentum: {sfng_mom}/100 | Breadth: {sfng_brd}/100\n"
        f"- Crypto F&G: {crypto_fng}"
    )


def build_strategy_report_prompt(
    data,
    brief: dict | None = None,
    analytics: dict | None = None,
    alerts: list[dict] | None = None,
    health_summary: dict | None = None,
    depth: str = "Orta",
):
    data = data or {}
    brief = brief or {}
    analytics = analytics or {}
    alerts = alerts or []
    health_summary = health_summary or {}
    rules = DEPTH_RULES.get(depth, DEPTH_RULES["Orta"])
    now_text = pd.Timestamp.now(tz="Europe/Istanbul").strftime("%d %B %Y %H:%M")
    scores = analytics.get("scores", {})
    participation = scores.get("participation", {})
    macro_breadth = participation.get("subfactors", {}).get("macro", {})
    crypto_breadth = participation.get("subfactors", {}).get("crypto", {})

    return f"""
Sen SA Finance Alpha Terminal icin günlük Makro Bülten hazırlayan üst duzey bir makro-kripto stratejistsin.
Türkçe yaz. Çıktı profesyonel, research-note tonunda, sayısal ve paylaşılabilir olsun.

Ana amac:
- Terminal icin karar destek bülteni yazmak
- X hesabinda paylaşılabilecek özet paketini birlikte vermek
- Anlatiyi editoryal ama disiplinli tutmak; rapor genel yorum gibi değil, gunluk strateji notu gibi okunmalı

Stil:
- {rules['style']}
- Terminal raporu uzunlugu: {rules['terminal_length']}
- Tekrara dusme
- Her ana bolumde neden onemli oldugunu tek cumleyle bagla
- Genel laflar yerine esik, trigger, invalidate ve davranis cumlesi ver
- Gereksiz yasal uyari ekleme
- Haberleri tek basina anlatma; rejime etkisi uzerinden kullan
- Markdown tablo kullanma
- Her ana bolum 1 kisa paragraf ve gerekirse 2-4 kisa madde icersin
- Ayni metrigi birden fazla bolumde uzun uzun tekrar etme
- "Long / Short / Bekle" bolumunde net davranis kosullari ver
- "Ekonomik Takvim" bolumunde en fazla 5 olay yaz
- "Onemli Haberler" bolumunde en fazla 3 haber yaz
- Ic analitik etiketleri rapora aynen kopyalama. "Fragile confidence", "Mixed overlay", "Neutral/Mixed" gibi ifadeleri dogrudan tekrar etme; bunlari dogal piyasa diliyle cevir.
- Her ana bolumde siralama su olsun: veri -> yorum -> neden onemli.
- Skorlar destekleyici baglamdir; ana cumle skoru degil, piyasayi anlatsin.

Zorunlu cikti formati:
<terminal_report>
### SA Finance Alpha Makro Bülteni Giriş
### Günlük Harita ve Ana Çıkarım
### Makro Ortam ve Risk İştahı
### BTC, Türev ve Order Book Analizi
### ETF, Stablecoin ve Altcoinler
### Macro Breadth ve Crypto Breadth
### Ekonomik Takvim ve Olası Etkiler
### Önemli Haberler ve Piyasa Yorumu
### Long / Short / Bekle ve Kritik Riskler
### Kritik Seviyeler, Invalidation ve Bugün Ne İzlenmeli
</terminal_report>
<x_lead>
Tek postluk acilis metni. 280 karakteri gecmesin. Pazarlama dili kullanma; sabah notu gibi yaz.
</x_lead>
<x_thread>
1/5 ...
2/5 ...
3/5 ...
4/5 ...
5/5 ...
</x_thread>

Canli baglam ({now_text}):

1) Rejim motoru
- Overall: {_safe(scores.get('overall'))}/100
- Base score: {_safe(scores.get('base_score'))}/100
- Fragility: {_safe(scores.get('fragility', {}).get('score'))}/100 | {_safe(scores.get('fragility', {}).get('label'))}
- Confidence: {_safe(scores.get('confidence'))}/100 | {_safe(scores.get('confidence_label'))}
- Regime band: {_safe(scores.get('regime_band'))}
- Overlay: {_safe(scores.get('overlay'))}
- Bias: {_safe(scores.get('bias'))}
- Dominant driver: {_safe(scores.get('dominant_driver'))}
- Weakest link: {_safe(scores.get('weakest_driver'))}
- Summary: {_safe(scores.get('summary'))}

2) Faktor kirilimi
{_format_factor_lines(scores)}

3) Participation
- Composite participation: {_safe(participation.get('score'))}/100 | {_safe(participation.get('state'))}
- Macro breadth: {_safe(macro_breadth.get('score'))}/100 | {_safe(macro_breadth.get('state'))}
- Crypto breadth: {_safe(crypto_breadth.get('score'))}/100 | {_safe(crypto_breadth.get('state'))}

4) Makro ve cross-asset veri seti
- SP500: {_safe(data.get('SP500'))} | 24s {_safe(data.get('SP500_C'))}
- NASDAQ: {_safe(data.get('NASDAQ'))} | 24s {_safe(data.get('NASDAQ_C'))}
- DAX: {_safe(data.get('DAX'))} | 24s {_safe(data.get('DAX_C'))}
- NIKKEI: {_safe(data.get('NIKKEI'))} | 24s {_safe(data.get('NIKKEI_C'))}
- VIX: {_safe(data.get('VIX'))} | 24s {_safe(data.get('VIX_C'))}
- DXY: {_safe(data.get('DXY'))} | 24s {_safe(data.get('DXY_C'))}
- US10Y: {_safe(data.get('US10Y'))} | 24s {_safe(data.get('US10Y_C'))}
- FED: {_safe(data.get('FED'))}
- GOLD: {_safe(data.get('GOLD'))} | 24s {_safe(data.get('GOLD_C'))}
- SILVER: {_safe(data.get('SILVER'))} | 24s {_safe(data.get('SILVER_C'))}
- OIL: {_safe(data.get('OIL'))} | 24s {_safe(data.get('OIL_C'))}

5) BTC, turev ve execution verileri
- BTC: {_safe(data.get('BTC_P'))} | 24s {_safe(data.get('BTC_C'))} | 7g {_safe(data.get('BTC_7D'))}
- BTC dominance: {_safe(data.get('Dom'))} | ETH dominance: {_safe(data.get('ETH_Dom'))}
- Funding: {_safe(data.get('FR'))} | OI: {_safe(data.get('OI'))} | L/S: {_safe(data.get('LS_Ratio'))} | Long %: {_safe(data.get('Long_Pct'))} | Short %: {_safe(data.get('Short_Pct'))} | Taker: {_safe(data.get('Taker'))}
- ETF netflow: {_safe(data.get('ETF_FLOW_TOTAL'))} | Tarih: {_safe(data.get('ETF_FLOW_DATE'))} | Kaynak: {_safe(data.get('ETF_FLOW_SOURCE'))}
- Order book signal: {_safe(data.get('ORDERBOOK_SIGNAL'))}
- Order book detail: {_safe(data.get('ORDERBOOK_SIGNAL_DETAIL'))}
- Order book sources: {_safe(data.get('ORDERBOOK_SOURCES'))}
- Support: {_safe(data.get('Sup_Wall'))} | Resistance: {_safe(data.get('Res_Wall'))}

6) Stablecoin, breadth ve altcoin veri seti
- Total stable: {_safe(data.get('Total_Stable'))} | USDT: {_safe(data.get('USDT_MCap'))} | USDC: {_safe(data.get('USDC_MCap'))} | DAI: {_safe(data.get('DAI_MCap'))}
- Stable.C.D: {_safe(data.get('STABLE_C_D'))} | USDT.D: {_safe(data.get('USDT_D'))} | USDT Dom Stable: {_safe(data.get('USDT_Dom_Stable'))}
- TOTAL: {_safe(data.get('TOTAL_CAP'))} | TOTAL2: {_safe(data.get('TOTAL2_CAP'))} | TOTAL3: {_safe(data.get('TOTAL3_CAP'))} | OTHERS: {_safe(data.get('OTHERS_CAP'))}
- ETH: {_safe(data.get('ETH_P'))} | 24s {_safe(data.get('ETH_C'))} | 7g {_safe(data.get('ETH_7D'))}
- SOL: {_safe(data.get('SOL_P'))} | 24s {_safe(data.get('SOL_C'))} | 7g {_safe(data.get('SOL_7D'))}
- BNB: {_safe(data.get('BNB_P'))} | 24s {_safe(data.get('BNB_C'))} | 7g {_safe(data.get('BNB_7D'))}
- XRP: {_safe(data.get('XRP_P'))} | 24s {_safe(data.get('XRP_C'))} | 7g {_safe(data.get('XRP_7D'))}
- ADA: {_safe(data.get('ADA_P'))} | 24s {_safe(data.get('ADA_C'))} | 7g {_safe(data.get('ADA_7D'))}
- AVAX: {_safe(data.get('AVAX_P'))} | 24s {_safe(data.get('AVAX_C'))} | 7g {_safe(data.get('AVAX_7D'))}
- DOT: {_safe(data.get('DOT_P'))} | 24s {_safe(data.get('DOT_C'))} | 7g {_safe(data.get('DOT_7D'))}
- LINK: {_safe(data.get('LINK_P'))} | 24s {_safe(data.get('LINK_C'))} | 7g {_safe(data.get('LINK_7D'))}

7) Brief yorumu
{_format_brief(brief)}

8) Invalidate ve watch next
{chr(10).join(f"- {item}" for item in scores.get('invalidate_conditions', [])) or '- Invalidate verisi yok'}
{chr(10).join(f"- watch: {item}" for item in scores.get('watch_next', [])) or '- Watch list yok'}

9) Senaryolar
{_format_scenarios(analytics)}

10) Alarmlar
{_format_alerts(alerts)}

11) Haberler
{_format_news(data.get('NEWS', []))}

12) Ekonomik takvim
Kaynak: {_safe(data.get('ECONOMIC_CALENDAR_SOURCE'))}
{_format_calendar(data.get('ECONOMIC_CALENDAR', []))}

13) Global Risk On/Off Göstergesi
{_format_risk_on_off(analytics)}

14) Karar Motoru (MQS + EWS)
{_format_decision_verdict(analytics)}

15) Sentiment — Crypto & Stock Fear/Greed
{_format_stock_fng(data)}

16) Veri sagligi
{_format_health(health_summary)}

Ek kurallar:
- X lead ve X thread, terminal raporunun kisa yansimasi olmali; yeni hikaye uydurma.
- X thread 7 madde olmali ve her madde tek paragraf olmali.
- X thread maddeleri su akisa bagli olsun: rejim, makro, BTC+turev, ETF/stablecoin/altcoin+breadth, seviyeler+invalidate.
- X thread ve x lead icinde pazarlama dili, slogan veya promosyon kullanma.
- X thread'in her maddesinde en az bir sayi, oran veya kritik seviye bulunsun.
- Terminal raporunda kritik seviyeleri dolar veya yuzde ile mutlaka yaz.
- Invalidation bolumunde ne olursa gorusun bozulacagini net soyle.
- "Günlük Harita ve Ana Çıkarım" bolumunde rejim, dominant driver, weakest link ve gunun temel davranis cizgisi ilk 5-6 satirda verilmis olsun.
- "Long / Short / Bekle ve Kritik Riskler" bolumunde su uc kalip zorunlu: long icin anlamli kosul, short icin anlamli kosul, beklemek icin anlamli kosul.
- "Makro Ortam ve Risk İştahı" bolumunde mutlaka DXY, US10Y, VIX, SP500, NASDAQ ve DAX, NIKKEI, GOLD, SILVER, OIL verilerini somut sayilarla kullan.
- "BTC, Türev ve Order Book Analizi" bolumunde BTC 24s ve 7g hareketini, funding/OI/L-S/Taker verileriyle birlestir; kaldirac yogunlugu ve squeeze riskine yorum getir.
- "ETF, Stablecoin ve Altcoinler" bolumunde ETF akisi, stablecoin buyuklugu ve altcoinlerin 24s/7g performansini BTC ile goreli kiyaslayarak yaz.
- "Macro Breadth ve Crypto Breadth" bolumunde skor tekrari yapmak yerine katilimin genis mi dar mi oldugunu, BTC disina yayilim olup olmadigini ve uyum/ayrisma durumunu anlat.
- "Makro Ortam ve Risk İştahı" bolumunde Global Risk On/Off sinyalini (phase, side bias, playbook) ve cross-asset transmission sonuclarini (ETH/BTC, BTC/NQ, BTC/GOLD) somut yorumla kullan.
- "Günlük Harita ve Ana Çıkarım" bolumunde MQS ve EWS skorlarini karar algilamasina bagla: piyasa kalitesi yuksekse agresiflik, dusukse temkin vurgulansin.
- Stock Market Fear & Greed ve Crypto Fear & Greed verilerini sentiment konfirmasyonu olarak kullan; iki endeks arasindan ayrisma varsa bunu belirt.
- Karar Motoru'ndaki (EVET/DIKKAT/HAYIR) sonucu "Long/Short/Bekle" bolumune dogal dille entegre et; skoru aynen kopyalama.
"""
