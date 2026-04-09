from domain.parsers import parse_number
from domain.signals import badge_class

PLACEHOLDER = "-"


def _why(*items):
    return [item for item in items if item and PLACEHOLDER not in item][:3]


def build_market_brief(data):
    btc_change = parse_number(data.get("BTC_C"))
    funding = parse_number(data.get("FR"))
    usdt_d = parse_number(data.get("USDT_D"))
    stable_c_d = parse_number(data.get("STABLE_C_D"))
    vix = parse_number(data.get("VIX"))
    etf_flow_total = data.get("ETF_FLOW_TOTAL", PLACEHOLDER)
    etf_flow_num = parse_number(etf_flow_total)
    etf_flow_date = data.get("ETF_FLOW_DATE", PLACEHOLDER)
    ls_signal = data.get("LS_Signal", PLACEHOLDER)
    orderbook_signal = data.get("ORDERBOOK_SIGNAL", PLACEHOLDER)
    orderbook_detail = data.get("ORDERBOOK_SIGNAL_DETAIL", PLACEHOLDER)
    has_positioning_data = any(
        parse_number(data.get(key)) is not None for key in ("FR", "LS_Ratio", "Taker")
    ) or any(data.get(key, PLACEHOLDER) != PLACEHOLDER for key in ("LS_Signal", "Long_Pct", "Short_Pct"))

    if btc_change is not None and btc_change >= 2:
        regime = {
            "label": "Piyasa Rejimi",
            "title": "Momentum Guclu",
            "detail": f"BTC 24s {data.get('BTC_C', PLACEHOLDER)} | VIX {data.get('VIX', PLACEHOLDER)}",
            "badge": "TREND",
            "class": "signal-long",
            "why": _why(
                f"BTC degisimi {data.get('BTC_C', PLACEHOLDER)}",
                f"VIX {data.get('VIX', PLACEHOLDER)}",
                f"ETF netflow {etf_flow_total}",
            ),
        }
    elif btc_change is not None and btc_change <= -2:
        regime = {
            "label": "Piyasa Rejimi",
            "title": "Baski Artiyor",
            "detail": f"BTC 24s {data.get('BTC_C', PLACEHOLDER)} | VIX {data.get('VIX', PLACEHOLDER)}",
            "badge": "RISK",
            "class": "signal-short",
            "why": _why(
                f"BTC degisimi {data.get('BTC_C', PLACEHOLDER)}",
                f"VIX {data.get('VIX', PLACEHOLDER)}",
                f"Funding {data.get('FR', PLACEHOLDER)}",
            ),
        }
    else:
        regime = {
            "label": "Piyasa Rejimi",
            "title": "Denge Araniyor",
            "detail": f"BTC 24s {data.get('BTC_C', PLACEHOLDER)} | VIX {data.get('VIX', PLACEHOLDER)}",
            "badge": "RANGE",
            "class": "signal-neutral",
            "why": _why(
                f"BTC degisimi {data.get('BTC_C', PLACEHOLDER)}",
                f"VIX {data.get('VIX', PLACEHOLDER)}",
                f"OI {data.get('OI', PLACEHOLDER)}",
            ),
        }

    if not has_positioning_data:
        positioning = {
            "label": "Pozisyonlanma",
            "title": "Turev akis bekleniyor",
            "detail": "Funding, L/S ve taker verisi henuz teyit edilmedi.",
            "badge": "DATA",
            "class": "signal-neutral",
            "why": [
                "Funding verisi bekleniyor",
                "Long/Short verisi bekleniyor",
                "Taker akisi bekleniyor",
            ],
        }
    elif funding is not None and funding > 0 and "Long" in ls_signal:
        positioning = {
            "label": "Pozisyonlanma",
            "title": "Longlar Kalabalik",
            "detail": f"Funding {data.get('FR', PLACEHOLDER)} | L/S {data.get('LS_Ratio', PLACEHOLDER)} | Taker {data.get('Taker', PLACEHOLDER)}",
            "badge": ls_signal,
            "class": "signal-short",
            "why": _why(
                f"Funding {data.get('FR', PLACEHOLDER)}",
                f"Long/Short {data.get('LS_Ratio', PLACEHOLDER)}",
                f"Taker {data.get('Taker', PLACEHOLDER)}",
            ),
        }
    elif funding is not None and funding < 0:
        positioning = {
            "label": "Pozisyonlanma",
            "title": "Short Baskisi",
            "detail": f"Funding {data.get('FR', PLACEHOLDER)} | L/S {data.get('LS_Ratio', PLACEHOLDER)} | Taker {data.get('Taker', PLACEHOLDER)}",
            "badge": ls_signal,
            "class": "signal-short",
            "why": _why(
                f"Funding {data.get('FR', PLACEHOLDER)}",
                f"Long/Short {data.get('LS_Ratio', PLACEHOLDER)}",
                f"Open interest {data.get('OI', PLACEHOLDER)}",
            ),
        }
    else:
        positioning = {
            "label": "Pozisyonlanma",
            "title": "Daha Dengeli Akis",
            "detail": f"Funding {data.get('FR', PLACEHOLDER)} | L/S {data.get('LS_Ratio', PLACEHOLDER)} | Taker {data.get('Taker', PLACEHOLDER)}",
            "badge": ls_signal,
            "class": badge_class(ls_signal),
            "why": _why(
                f"Funding {data.get('FR', PLACEHOLDER)}",
                f"Long/Short {data.get('LS_Ratio', PLACEHOLDER)}",
                f"Taker {data.get('Taker', PLACEHOLDER)}",
            ),
        }

    liquidity_pressure = (
        max(value for value in [usdt_d, stable_c_d] if value is not None)
        if any(value is not None for value in [usdt_d, stable_c_d])
        else None
    )
    liquidity_detail = (
        f"ETF Netflow {etf_flow_total} | {etf_flow_date} | "
        f"Stable.C.D {data.get('STABLE_C_D', PLACEHOLDER)} | USDT.D {data.get('USDT_D', PLACEHOLDER)}"
    )

    if etf_flow_num is not None and etf_flow_num > 0 and (liquidity_pressure is None or liquidity_pressure < 7):
        liquidity = {
            "label": "Likidite",
            "title": "Risk Sermayesi Akiyor",
            "detail": liquidity_detail,
            "badge": "FLOW",
            "class": "signal-long",
            "why": _why(
                f"ETF netflow {etf_flow_total}",
                f"USDT.D {data.get('USDT_D', PLACEHOLDER)}",
                f"Stable.C.D {data.get('STABLE_C_D', PLACEHOLDER)}",
            ),
        }
    elif (etf_flow_num is not None and etf_flow_num < 0) or (
        liquidity_pressure is not None and liquidity_pressure >= 7
    ):
        liquidity = {
            "label": "Likidite",
            "title": "Savunmaci Konumlanma",
            "detail": liquidity_detail,
            "badge": "CASH",
            "class": "signal-short",
            "why": _why(
                f"ETF netflow {etf_flow_total}",
                f"USDT.D {data.get('USDT_D', PLACEHOLDER)}",
                f"Stable.C.D {data.get('STABLE_C_D', PLACEHOLDER)}",
            ),
        }
    else:
        liquidity = {
            "label": "Likidite",
            "title": "Likidite Kararsiz",
            "detail": liquidity_detail,
            "badge": "WATCH",
            "class": "signal-neutral",
            "why": _why(
                f"ETF netflow {etf_flow_total}",
                f"USDT.D {data.get('USDT_D', PLACEHOLDER)}",
                f"Stable.C.D {data.get('STABLE_C_D', PLACEHOLDER)}",
            ),
        }

    if orderbook_signal == PLACEHOLDER and orderbook_detail == PLACEHOLDER:
        focus = {
            "label": "Odak Seviye",
            "title": "Order book teyidi bekleniyor",
            "detail": "Borsa seviyeleri dogrulaninca ortak destek/direnc burada guncellenecek.",
            "badge": "WATCH",
            "class": "signal-neutral",
            "why": [
                "Kraken seviyesi bekleniyor",
                "OKX seviyesi bekleniyor",
                "Coklu borsa teyidi bekleniyor",
            ],
        }
    elif "destek" in orderbook_signal.lower():
        focus = {
            "label": "Odak Seviye",
            "title": "Ortak Destek",
            "detail": orderbook_detail,
            "badge": "SUPPORT",
            "class": "signal-long",
            "why": _why(
                orderbook_detail,
                f"Kraken destek {data.get('Sup_Wall', PLACEHOLDER)}",
                f"OKX destek {data.get('OKX_Sup_Wall', PLACEHOLDER)}",
            ),
        }
    elif "direnc" in orderbook_signal.lower():
        focus = {
            "label": "Odak Seviye",
            "title": "Ortak Direnc",
            "detail": orderbook_detail,
            "badge": "RESISTANCE",
            "class": "signal-short",
            "why": _why(
                orderbook_detail,
                f"Kraken direnc {data.get('Res_Wall', PLACEHOLDER)}",
                f"OKX direnc {data.get('OKX_Res_Wall', PLACEHOLDER)}",
            ),
        }
    elif "Diren" in data.get("Wall_Status", PLACEHOLDER):
        focus = {
            "label": "Odak Seviye",
            "title": "Kraken Direnci",
            "detail": f"Simdi {data.get('BTC_Now', PLACEHOLDER)} | Duvar {data.get('Res_Wall', PLACEHOLDER)} ({data.get('Res_Vol', PLACEHOLDER)})",
            "badge": "RESISTANCE",
            "class": "signal-short",
            "why": _why(
                f"Kraken direnc {data.get('Res_Wall', PLACEHOLDER)}",
                f"Kraken hacim {data.get('Res_Vol', PLACEHOLDER)}",
                f"Spot fiyat {data.get('BTC_Now', PLACEHOLDER)}",
            ),
        }
    elif "Dest" in data.get("Wall_Status", PLACEHOLDER):
        focus = {
            "label": "Odak Seviye",
            "title": "Kraken Destegi",
            "detail": f"Simdi {data.get('BTC_Now', PLACEHOLDER)} | Duvar {data.get('Sup_Wall', PLACEHOLDER)} ({data.get('Sup_Vol', PLACEHOLDER)})",
            "badge": "SUPPORT",
            "class": "signal-long",
            "why": _why(
                f"Kraken destek {data.get('Sup_Wall', PLACEHOLDER)}",
                f"Kraken hacim {data.get('Sup_Vol', PLACEHOLDER)}",
                f"Spot fiyat {data.get('BTC_Now', PLACEHOLDER)}",
            ),
        }
    else:
        focus = {
            "label": "Odak Seviye",
            "title": "Seviye Dengesi",
            "detail": orderbook_detail,
            "badge": data.get("ORDERBOOK_SIGNAL_BADGE", "RANGE"),
            "class": data.get("ORDERBOOK_SIGNAL_CLASS", "signal-neutral"),
            "why": _why(
                orderbook_detail,
                f"Kraken {data.get('Sup_Wall', PLACEHOLDER)} / {data.get('Res_Wall', PLACEHOLDER)}",
                f"OKX {data.get('OKX_Sup_Wall', PLACEHOLDER)} / {data.get('OKX_Res_Wall', PLACEHOLDER)}",
            ),
        }

    if vix is not None and vix >= 25:
        regime["detail"] = f"{regime['detail']} | Yuksek oynaklik"

    return {
        "regime": regime,
        "positioning": positioning,
        "liquidity": liquidity,
        "focus": focus,
    }
