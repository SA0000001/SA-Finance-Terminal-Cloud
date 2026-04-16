from __future__ import annotations

from io import BytesIO

from domain.parsers import parse_number

PLACEHOLDER = "-"
DEFAULT_PINNED_METRICS = ["BTC_P", "BTC_C", "FNG", "FR", "VIX", "ETF_FLOW_TOTAL", "USDT_D", "TOTAL_CAP"]
FACTOR_WEIGHTS = {
    "liquidity": 0.35,
    "volatility": 0.25,
    "positioning": 0.20,
    "participation": 0.20,
}
METRIC_LABELS = {
    "BTC_P": "BTC fiyat",
    "BTC_C": "BTC 24s",
    "BTC_7D": "BTC 7g",
    "FNG": "Fear & Greed",
    "FR": "Funding",
    "OI": "Open Interest",
    "VIX": "VIX",
    "ETF_FLOW_TOTAL": "ETF netflow",
    "USDT_D": "USDT.D",
    "STABLE_C_D": "Stable.C.D",
    "TOTAL_CAP": "TOTAL",
    "TOTAL2_CAP": "TOTAL2",
    "TOTAL3_CAP": "TOTAL3",
    "ETH_P": "ETH fiyat",
    "SOL_P": "SOL fiyat",
    "DXY": "DXY",
    "FED": "FED",
}

# Metrik başvuru eşikleri — data table card'larda bağlam notu olarak gösterilir
METRIC_CONTEXT: dict[str, str] = {
    "FR":              "Nötr: 0% · Dikkat: >+0.01% · Aşırı: >+0.03%",
    "FNG":             "Aşırı Korku: 0–24 · Korku: 25–44 · Nötr: 45–55 · Açgözlülük: 56–74 · Aşırı: 75–100",
    "VIX":             "Normal: <20 · Endişe: 20–30 · Korku: 30–40 · Panik: >40",
    "ETF_FLOW_TOTAL":  "Güçlü Giriş: >500M · Giriş: >0 · Çıkış: <0 · Güçlü Çıkış: <-200M",
    "USDT_D":          "Düşük (risk-on): <4% · Nötr: 4–6% · Yüksek (risk-off): >6%",
    "STABLE_C_D":      "Pozitif: piyasaya stablecoin giriyor · Negatif: stablecoin çekiliyor",
    "OI":              "Yükselen OI + yükselen fiyat: sağlıklı. Yükselen OI + düşen fiyat: dikkat.",
    "DXY":             "Güçlü DXY genellikle kripto için baskıcı. Zayıf DXY risk-on ortamı destekler.",
    "US10Y":           "Hızlı yükseliş likiditeyi sıkar. >4.5% seviyeleri risk varlıkları için baskı.",
    "M2":              "M2 YoY artışı likidite genişlemesine işaret eder; kripto için tarihsel olarak pozitif.",
    "Dom":             "BTC Dom artışı: altcoin riskten kaçış. Düşüş: altcoin sezonuna geçiş sinyali.",
    "ETH_Dom":         "ETH dom güçleniyorsa ETH liderliği; zayıflıyorsa BTC veya altcoin rotasyonu.",
    "LS_Ratio":        "L/S >1: uzun pozisyon ağırlıklı. <1: short ağırlıklı. Aşırı uçlar dikkat sinyali.",
    "Sup_Wall":        "Mevcut fiyatın altındaki en güçlü alım duvarı seviyesi.",
    "Res_Wall":        "Mevcut fiyatın üstündeki en güçlü satış duvarı seviyesi.",
    "Hash":            "Hashrate artışı madenci güvenini ve ağ sağlığını gösterir.",
    "Active":          "Aktif adres artışı on-chain kullanım ve talep artışına işaret eder.",
    "TOTAL_CAP":       "Tüm kripto piyasa değeri. Yeni ATH yaklaşımı geniş katılımı gösterir.",
    "TOTAL2_CAP":      "BTC hariç kripto piyasa değeri. Altcoin sezonu göstergesi.",
    "TOTAL3_CAP":      "BTC ve ETH hariç. Küçük/orta cap katılımını ölçer.",
}


def clamp_score(value: float) -> int:
    return max(0, min(100, int(round(value))))


def _display(value) -> str:
    return str(value) if value not in (None, "", PLACEHOLDER) else PLACEHOLDER


def _linear_score(value: float | None, low: float, high: float, *, inverse: bool = False) -> int:
    if value is None or high == low:
        return 50
    ratio = (value - low) / (high - low)
    ratio = max(0.0, min(1.0, ratio))
    score = (1 - ratio) * 100 if inverse else ratio * 100
    return clamp_score(score)


def _balance_score(value: float | None, center: float, caution: float, danger: float) -> int:
    if value is None:
        return 50
    distance = abs(value - center)
    if distance <= caution:
        return clamp_score(100 - (distance / caution) * 12) if caution else 100
    if distance >= danger:
        return 5
    span = danger - caution
    severity = (distance - caution) / span if span else 1.0
    return clamp_score(88 - severity * 83)


def _trend_score(change: float | None, *, favorable_up: bool, scale: float) -> int:
    if change is None or scale <= 0:
        return 50
    normalized = max(-1.0, min(1.0, change / scale))
    if not favorable_up:
        normalized *= -1
    return clamp_score(50 + normalized * 50)


def _delta_from_trend(trend_score: int) -> int:
    return int(round((trend_score - 50) / 4))


def _weighted_metric_score(metrics: list[dict]) -> int:
    total_weight = sum(item["weight"] for item in metrics) or 1
    weighted = sum(item["score"] * item["weight"] for item in metrics) / total_weight
    return clamp_score(weighted)


def _format_driver(metric: dict) -> str:
    tone = "destekleyici" if metric["score"] >= 55 else "baski yaratiyor"
    return f"{metric['label']} {tone} ({metric['display']})"


def _top_drivers(metrics: list[dict], count: int = 3) -> list[str]:
    ordered = sorted(metrics, key=lambda item: abs(item["score"] - 50), reverse=True)
    return [_format_driver(metric) for metric in ordered[:count]]


def _factor_state(score: int) -> str:
    if score >= 75:
        return "Güçlü destek"
    if score >= 60:
        return "Yapıcı"
    if score >= 45:
        return "Karışık"
    if score >= 30:
        return "Kırıgan"
    return "Stresli"


def _factor_trend_text(delta_7d: int) -> str:
    if delta_7d >= 4:
        return "İyileşiyor"
    if delta_7d <= -4:
        return "Bozuluyor"
    return "Dengeleniyor"


def _count_positive(*values: float | None) -> int:
    return sum(1 for value in values if value is not None and value > 0)


def _display_spread(label_a: str, value_a, label_b: str, value_b) -> str:
    first = parse_number(value_a)
    second = parse_number(value_b)
    if first is None or second is None:
        return PLACEHOLDER
    spread = first - second
    sign = "+" if spread >= 0 else ""
    return f"{label_a}-{label_b} {sign}{spread:.2f}pp"


def _confidence_score(metrics: list[dict]) -> int:
    if not metrics:
        return 0
    available = sum(1 for metric in metrics if metric.get("display") not in {PLACEHOLDER, "", None})
    return clamp_score((available / len(metrics)) * 100)


def _confidence_label(score: int) -> str:
    if score >= 80:
        return "High confidence"
    if score >= 60:
        return "Moderate confidence"
    if score >= 40:
        return "Guarded confidence"
    return "Low confidence"


def _regime_confidence_score(
    factors: dict[str, dict], overall: int, fragility: dict, invalidate_conditions: list[str]
) -> int:
    data_confidence = sum(factor["confidence"] * factor["weight"] for factor in factors.values())
    dominant_factor = max(factors.values(), key=lambda factor: factor["contribution"])
    weakest_factor = min(factors.values(), key=lambda factor: factor["score"])
    participation = factors["participation"]
    macro_breadth = participation["subfactors"]["macro"]["score"]
    crypto_breadth = participation["subfactors"]["crypto"]["score"]
    alignment_gap = abs(macro_breadth - crypto_breadth)

    regime_clarity = clamp_score(
        (abs(overall - 50) * 1.25) + ((dominant_factor["score"] - weakest_factor["score"]) * 0.28)
    )
    driver_strength = clamp_score(
        ((dominant_factor["score"] - 50) * 1.35) + ((dominant_factor["contribution"] / dominant_factor["weight"]) - 45)
    )
    alignment_score = clamp_score(100 - (alignment_gap * 3.4))
    stability_mix = clamp_score((factors["volatility"]["score"] * 0.58) + (factors["positioning"]["score"] * 0.42))

    raw_score = (
        (data_confidence * 0.24)
        + (regime_clarity * 0.18)
        + (driver_strength * 0.12)
        + (alignment_score * 0.14)
        + (stability_mix * 0.20)
        + (factors["liquidity"]["score"] * 0.12)
    )

    weakest_penalty = max(0.0, (56 - weakest_factor["score"]) * 0.58)
    fragility_penalty = max(0.0, (fragility["score"] - 22) * 0.56)
    crowding_penalty = max(0.0, (62 - factors["positioning"]["score"]) * 0.44)
    volatility_penalty = max(0.0, (60 - factors["volatility"]["score"]) * 0.26)
    alignment_penalty = max(0.0, (alignment_gap - 12) * 0.45)
    invalidate_penalty = max(0.0, len(invalidate_conditions) - 1) * 4.5
    invalidate_proximity_penalty = 0.0
    if factors["liquidity"]["score"] < 58:
        invalidate_proximity_penalty += 3.0
    if factors["volatility"]["score"] < 60:
        invalidate_proximity_penalty += 3.0
    if factors["positioning"]["score"] < 58:
        invalidate_proximity_penalty += 4.0
    if macro_breadth < 55:
        invalidate_proximity_penalty += 2.0
    if crypto_breadth < 55:
        invalidate_proximity_penalty += 2.0
    if alignment_gap >= 18:
        invalidate_proximity_penalty += 2.5

    calibrated = (
        raw_score
        - weakest_penalty
        - fragility_penalty
        - crowding_penalty
        - volatility_penalty
        - alignment_penalty
        - invalidate_penalty
        - invalidate_proximity_penalty
    )

    cap = 84
    if overall < 72:
        cap = 80
    if overall < 62:
        cap = 74
    if weakest_factor["score"] < 56 or fragility["score"] >= 38:
        cap = min(cap, 70)
    if factors["positioning"]["score"] < 56 or alignment_gap >= 18:
        cap = min(cap, 66)
    if fragility["score"] >= 55 or factors["positioning"]["score"] < 48 or weakest_factor["score"] < 48:
        cap = min(cap, 58)
    if fragility["score"] >= 70 or factors["positioning"]["score"] < 40 or weakest_factor["score"] < 40:
        cap = min(cap, 48)

    return clamp_score(min(calibrated, cap))


def _regime_confidence_label(score: int, fragility_score: int) -> str:
    if fragility_score >= 65 or score < 30:
        return "Fragile confidence"
    if fragility_score >= 45 or score < 55:
        return "Conditional confidence"
    if score < 74:
        return "Moderate confidence"
    return "High confidence"


def _build_liquidity_factor(data: dict) -> dict:
    dxy = parse_number(data.get("DXY"))
    dxy_change = parse_number(data.get("DXY_C"))
    us10y = parse_number(data.get("US10Y"))
    us10y_change = parse_number(data.get("US10Y_C"))
    etf_flow = parse_number(data.get("ETF_FLOW_TOTAL"))
    stable_cd = parse_number(data.get("STABLE_C_D"))
    usdt_d = parse_number(data.get("USDT_D"))

    metrics = [
        {
            "label": "ETF akislari",
            "display": _display(data.get("ETF_FLOW_TOTAL")),
            "score": _linear_score(etf_flow, -250, 250),
            "weight": 0.30,
        },
        {
            "label": "DXY seviyesi",
            "display": _display(data.get("DXY")),
            "score": _linear_score(dxy, 96, 106, inverse=True),
            "weight": 0.16,
        },
        {
            "label": "DXY trendi",
            "display": _display(data.get("DXY_C")),
            "score": _trend_score(dxy_change, favorable_up=False, scale=1.2),
            "weight": 0.10,
        },
        {
            "label": "US10Y",
            "display": _display(data.get("US10Y")),
            "score": _linear_score(us10y, 3.4, 5.2, inverse=True),
            "weight": 0.14,
        },
        {
            "label": "Yield trendi",
            "display": _display(data.get("US10Y_C")),
            "score": _trend_score(us10y_change, favorable_up=False, scale=2.0),
            "weight": 0.08,
        },
        {
            "label": "Stable.C.D",
            "display": _display(data.get("STABLE_C_D")),
            "score": _linear_score(stable_cd, 6.0, 15.0, inverse=True),
            "weight": 0.10,
        },
        {
            "label": "USDT.D",
            "display": _display(data.get("USDT_D")),
            "score": _linear_score(usdt_d, 4.5, 9.0, inverse=True),
            "weight": 0.12,
        },
    ]
    score = _weighted_metric_score(metrics)
    trend_mix = clamp_score(
        (_trend_score(dxy_change, favorable_up=False, scale=1.2) * 0.4)
        + (_trend_score(us10y_change, favorable_up=False, scale=2.0) * 0.3)
        + (_trend_score(etf_flow, favorable_up=True, scale=120) * 0.3)
    )
    delta_7d = _delta_from_trend(trend_mix)
    summary = "ETF akimlari ve dolar/yield baskisi likidite rejimini belirliyor."
    return {
        "key": "liquidity",
        "label": "Liquidity",
        "score": score,
        "weight": FACTOR_WEIGHTS["liquidity"],
        "delta_7d": delta_7d,
        "trend": "up" if delta_7d > 1 else "down" if delta_7d < -1 else "flat",
        "state": _factor_state(score),
        "summary": summary,
        "drivers": _top_drivers(metrics),
        "metrics": metrics,
    }


def _build_volatility_factor(data: dict) -> dict:
    vix = parse_number(data.get("VIX"))
    vix_change = parse_number(data.get("VIX_C"))
    btc_change = parse_number(data.get("BTC_C"))
    btc_7d = parse_number(data.get("BTC_7D"))
    accel = abs((btc_change or 0.0) - ((btc_7d or 0.0) / 7))

    metrics = [
        {
            "label": "VIX seviyesi",
            "display": _display(data.get("VIX")),
            "score": _linear_score(vix, 12, 40, inverse=True),
            "weight": 0.42,
        },
        {
            "label": "VIX trendi",
            "display": _display(data.get("VIX_C")),
            "score": _trend_score(vix_change, favorable_up=False, scale=6.0),
            "weight": 0.12,
        },
        {
            "label": "BTC 24s oynaklik",
            "display": _display(data.get("BTC_C")),
            "score": _linear_score(abs(btc_change) if btc_change is not None else None, 0.5, 8.0, inverse=True),
            "weight": 0.24,
        },
        {
            "label": "BTC 7g hareketi",
            "display": _display(data.get("BTC_7D")),
            "score": _linear_score(abs(btc_7d) if btc_7d is not None else None, 2.0, 18.0, inverse=True),
            "weight": 0.14,
        },
        {
            "label": "Vol hizlanmasi",
            "display": f"{accel:.2f}%" if accel else PLACEHOLDER,
            "score": _linear_score(accel, 0.4, 5.0, inverse=True),
            "weight": 0.08,
        },
    ]
    score = _weighted_metric_score(metrics)
    trend_mix = clamp_score(
        (_trend_score(vix_change, favorable_up=False, scale=6.0) * 0.5)
        + (_trend_score(-(abs(btc_change) if btc_change is not None else 0.0), favorable_up=True, scale=4.0) * 0.5)
    )
    delta_7d = _delta_from_trend(trend_mix)
    return {
        "key": "volatility",
        "label": "Volatility",
        "score": score,
        "weight": FACTOR_WEIGHTS["volatility"],
        "delta_7d": delta_7d,
        "trend": "up" if delta_7d > 1 else "down" if delta_7d < -1 else "flat",
        "state": _factor_state(score),
        "summary": "Kontrollu vol pozitif; sikisan veya sok tipi vol ise rejimi kirilganlastiriyor.",
        "drivers": _top_drivers(metrics),
        "metrics": metrics,
    }


def _build_positioning_factor(data: dict) -> dict:
    funding = parse_number(data.get("FR"))
    ls_ratio = parse_number(data.get("LS_Ratio"))
    taker = parse_number(data.get("Taker"))
    open_interest = parse_number(data.get("OI"))
    btc_change = parse_number(data.get("BTC_C"))
    etf_flow = parse_number(data.get("ETF_FLOW_TOTAL"))

    divergence_score = 80
    if (btc_change or 0) > 0 and (etf_flow or 0) < 0:
        divergence_score = 28
    elif (btc_change or 0) < 0 and (etf_flow or 0) > 0:
        divergence_score = 62

    metrics = [
        {
            "label": "Funding dengesi",
            "display": _display(data.get("FR")),
            "score": _balance_score(funding, 0.0, 0.006, 0.03),
            "weight": 0.30,
        },
        {
            "label": "L/S dengesi",
            "display": _display(data.get("LS_Ratio")),
            "score": _balance_score(ls_ratio, 1.0, 0.10, 0.55),
            "weight": 0.24,
        },
        {
            "label": "Taker akis",
            "display": _display(data.get("Taker")),
            "score": _balance_score(taker, 1.0, 0.05, 0.30),
            "weight": 0.20,
        },
        {
            "label": "Open interest",
            "display": _display(data.get("OI")),
            "score": _linear_score(open_interest, 1_800_000, 3_800_000, inverse=True),
            "weight": 0.16,
        },
        {
            "label": "Fiyat-akis uyumu",
            "display": f"BTC { _display(data.get('BTC_C')) } | ETF { _display(data.get('ETF_FLOW_TOTAL')) }",
            "score": divergence_score,
            "weight": 0.10,
        },
    ]
    score = _weighted_metric_score(metrics)
    crowding_pressure = clamp_score(
        100
        - (
            (_balance_score(funding, 0.0, 0.006, 0.03) * 0.4)
            + (_balance_score(ls_ratio, 1.0, 0.10, 0.55) * 0.35)
            + (_balance_score(taker, 1.0, 0.05, 0.30) * 0.25)
        )
    )
    delta_7d = -int(round((crowding_pressure - 40) / 8))
    return {
        "key": "positioning",
        "label": "Positioning",
        "score": score,
        "weight": FACTOR_WEIGHTS["positioning"],
        "delta_7d": delta_7d,
        "trend": "up" if delta_7d > 1 else "down" if delta_7d < -1 else "flat",
        "state": _factor_state(score),
        "summary": "Kalabalik trade ve squeeze riski burada olculuyor; bullish olmak otomatik yuksek puan vermiyor.",
        "drivers": _top_drivers(metrics),
        "metrics": metrics,
    }


def _build_macro_breadth_factor(data: dict) -> dict:
    spy_change = parse_number(data.get("SPY_C"))
    rsp_change = parse_number(data.get("RSP_C"))
    iwm_change = parse_number(data.get("IWM_C"))
    qqq_change = parse_number(data.get("QQQ_C"))
    sector_changes = [parse_number(data.get(key)) for key in ("XLK_C", "XLF_C", "XLI_C", "XLE_C", "XLY_C")]
    cross_asset_changes = [
        parse_number(data.get("SP500_C")),
        parse_number(data.get("NASDAQ_C")),
        parse_number(data.get("DAX_C")),
        parse_number(data.get("FTSE_C")),
        parse_number(data.get("NIKKEI_C")),
    ]

    equal_weight_spread = (rsp_change - spy_change) if rsp_change is not None and spy_change is not None else None
    small_cap_spread = (iwm_change - spy_change) if iwm_change is not None and spy_change is not None else None
    sector_positive = _count_positive(*sector_changes)
    index_positive = _count_positive(*cross_asset_changes)
    mega_cap_gap = (qqq_change - rsp_change) if qqq_change is not None and rsp_change is not None else None

    metrics = [
        {
            "label": "Equal-weight participation",
            "display": _display_spread("RSP", data.get("RSP_C"), "SPY", data.get("SPY_C")),
            "score": _linear_score(equal_weight_spread, -2.5, 2.5),
            "weight": 0.26,
        },
        {
            "label": "Small-cap participation",
            "display": _display_spread("IWM", data.get("IWM_C"), "SPY", data.get("SPY_C")),
            "score": _linear_score(small_cap_spread, -3.0, 3.0),
            "weight": 0.22,
        },
        {
            "label": "Sector participation",
            "display": f"{sector_positive}/5 sectors positive" if sector_positive else PLACEHOLDER,
            "score": _linear_score(sector_positive, 1, 5),
            "weight": 0.24,
        },
        {
            "label": "Cross-index confirmation",
            "display": f"{index_positive}/5 indices positive" if index_positive else PLACEHOLDER,
            "score": _linear_score(index_positive, 1, 5),
            "weight": 0.16,
        },
        {
            "label": "Mega-cap concentration",
            "display": _display_spread("QQQ", data.get("QQQ_C"), "RSP", data.get("RSP_C")),
            "score": _linear_score(mega_cap_gap, 0.0, 4.0, inverse=True),
            "weight": 0.12,
        },
    ]
    score = _weighted_metric_score(metrics)
    confidence = _confidence_score(metrics)
    breadth_trend = clamp_score(
        (_linear_score(equal_weight_spread, -2.5, 2.5) * 0.35)
        + (_linear_score(small_cap_spread, -3.0, 3.0) * 0.25)
        + (_linear_score(sector_positive, 1, 5) * 0.20)
        + (_linear_score(index_positive, 1, 5) * 0.20)
    )
    delta_7d = _delta_from_trend(breadth_trend)
    return {
        "key": "macro_breadth",
        "label": "Macro Breadth",
        "score": score,
        "weight": 0.45,
        "delta_7d": delta_7d,
        "trend": "up" if delta_7d > 1 else "down" if delta_7d < -1 else "flat",
        "state": _factor_state(score),
        "summary": "Makro risk katiliminin mega-cap disina, sektorlere ve small-cap'lere yayilip yayilmadigini olcer.",
        "drivers": _top_drivers(metrics),
        "metrics": metrics,
        "confidence": confidence,
        "confidence_label": _confidence_label(confidence),
        "primary_support": max(metrics, key=lambda item: item["score"])["label"],
        "primary_risk": min(metrics, key=lambda item: item["score"])["label"],
        "proxy_note": "ETF ve cross-index proxy'leri kullaniliyor.",
    }


def _build_crypto_breadth_factor(data: dict) -> dict:
    total = parse_number(data.get("TOTAL_CAP"))
    total2 = parse_number(data.get("TOTAL2_CAP"))
    total3 = parse_number(data.get("TOTAL3_CAP"))
    others = parse_number(data.get("OTHERS_CAP"))
    btc_dom = parse_number(data.get("Dom"))
    eth_dom = parse_number(data.get("ETH_Dom"))
    btc_change = parse_number(data.get("BTC_C"))

    total2_ratio = ((total2 / total) * 100) if total and total2 else None
    total3_ratio = ((total3 / total) * 100) if total and total3 else None
    others_ratio = ((others / total) * 100) if total and others else None
    trend_support = 55
    if (btc_change or 0) > 2 and (total3_ratio or 0) > 30:
        trend_support = 78
    elif (btc_change or 0) > 2 and (total3_ratio or 0) < 24:
        trend_support = 32

    metrics = [
        {
            "label": "TOTAL2 katilimi",
            "display": f"{total2_ratio:.1f}%" if total2_ratio is not None else PLACEHOLDER,
            "score": _linear_score(total2_ratio, 35, 55),
            "weight": 0.22,
        },
        {
            "label": "TOTAL3 katilimi",
            "display": f"{total3_ratio:.1f}%" if total3_ratio is not None else PLACEHOLDER,
            "score": _linear_score(total3_ratio, 20, 42),
            "weight": 0.26,
        },
        {
            "label": "OTHERS payi",
            "display": f"{others_ratio:.1f}%" if others_ratio is not None else PLACEHOLDER,
            "score": _linear_score(others_ratio, 4, 16),
            "weight": 0.12,
        },
        {
            "label": "BTC dominance",
            "display": _display(data.get("Dom")),
            "score": _linear_score(btc_dom, 46, 60, inverse=True),
            "weight": 0.18,
        },
        {
            "label": "ETH participation",
            "display": _display(data.get("ETH_Dom")),
            "score": _linear_score(eth_dom, 8, 20),
            "weight": 0.10,
        },
        {
            "label": "Alt participation teyidi",
            "display": _display(data.get("BTC_C")),
            "score": trend_support,
            "weight": 0.12,
        },
    ]
    score = _weighted_metric_score(metrics)
    confidence = _confidence_score(metrics)
    breadth_trend = clamp_score((_linear_score(total3_ratio, 20, 42) * 0.6) + (trend_support * 0.4))
    delta_7d = _delta_from_trend(breadth_trend)
    return {
        "key": "crypto_breadth",
        "label": "Crypto Breadth",
        "score": score,
        "weight": 0.55,
        "delta_7d": delta_7d,
        "trend": "up" if delta_7d > 1 else "down" if delta_7d < -1 else "flat",
        "state": _factor_state(score),
        "summary": "Kripto hareketinin BTC disina, alt katmanlara ve market cap segmentlerine yayilip yayilmadigini olcer.",
        "drivers": _top_drivers(metrics),
        "metrics": metrics,
        "confidence": confidence,
        "confidence_label": _confidence_label(confidence),
        "primary_support": max(metrics, key=lambda item: item["score"])["label"],
        "primary_risk": min(metrics, key=lambda item: item["score"])["label"],
        "proxy_note": "TOTAL/TOTAL2/TOTAL3, dominance ve segment proxy'leri kullaniliyor.",
    }


def _build_participation_factor(data: dict) -> dict:
    macro = _build_macro_breadth_factor(data)
    crypto = _build_crypto_breadth_factor(data)
    divergence = abs(macro["score"] - crypto["score"])
    divergence_penalty = clamp_score(_linear_score(divergence, 8, 35, inverse=True))
    base_score = (macro["score"] * 0.45) + (crypto["score"] * 0.55)
    score = clamp_score((base_score * 0.88) + (divergence_penalty * 0.12))
    trend_mix = clamp_score((macro["score"] * 0.45) + (crypto["score"] * 0.55))
    delta_7d = _delta_from_trend(trend_mix)
    metrics = [
        {
            "label": "Macro Breadth",
            "display": f"{macro['score']}/100 | {macro['state']}",
            "score": macro["score"],
            "weight": 0.45,
        },
        {
            "label": "Crypto Breadth",
            "display": f"{crypto['score']}/100 | {crypto['state']}",
            "score": crypto["score"],
            "weight": 0.55,
        },
        {
            "label": "Participation alignment",
            "display": f"Gap {divergence} puan",
            "score": divergence_penalty,
            "weight": 0.12,
        },
    ]
    if divergence >= 22:
        summary = "Macro ve crypto katilimi ayrisiyor; tek cepheden gelen risk-alimi kirilgan olabilir."
    elif score >= 65:
        summary = "Macro ve crypto katilimi birlikte destek veriyor; risk rejimi daha saglikli."
    else:
        summary = "Katilim karisik; hem macro hem crypto tarafinda tam bir senkron yok."
    return {
        "key": "participation",
        "label": "Composite Participation",
        "score": score,
        "weight": FACTOR_WEIGHTS["participation"],
        "delta_7d": delta_7d,
        "trend": "up" if delta_7d > 1 else "down" if delta_7d < -1 else "flat",
        "state": _factor_state(score),
        "summary": summary,
        "drivers": [
            f"Macro Breadth {_factor_state(macro['score']).lower()} ({macro['score']}/100)",
            f"Crypto Breadth {_factor_state(crypto['score']).lower()} ({crypto['score']}/100)",
            f"Macro/Crypto alignment {divergence_penalty}/100",
        ],
        "metrics": metrics,
        "subfactors": {"macro": macro, "crypto": crypto},
        "confidence": clamp_score(
            (_confidence_score(macro["metrics"]) * 0.45) + (_confidence_score(crypto["metrics"]) * 0.55)
        ),
        "confidence_label": _confidence_label(
            clamp_score((_confidence_score(macro["metrics"]) * 0.45) + (_confidence_score(crypto["metrics"]) * 0.55))
        ),
    }


def _regime_band(score: int) -> str:
    if score <= 20:
        return "Panic / Risk-Off"
    if score <= 40:
        return "Defensive"
    if score <= 60:
        return "Neutral / Mixed"
    if score <= 80:
        return "Constructive Risk-On"
    return "Strong Risk-On / Euphoric"


def _fragility_label(score: int) -> str:
    if score >= 75:
        return "Elevated Fragility"
    if score >= 55:
        return "Fragile"
    if score >= 35:
        return "Manageable"
    return "Stable"


def _build_fragility(factors: dict[str, dict], data: dict) -> dict:
    funding = parse_number(data.get("FR")) or 0.0
    ls_ratio = parse_number(data.get("LS_Ratio")) or 1.0
    taker = parse_number(data.get("Taker")) or 1.0
    vix = parse_number(data.get("VIX")) or 20.0
    btc_change = parse_number(data.get("BTC_C")) or 0.0
    etf_flow = parse_number(data.get("ETF_FLOW_TOTAL")) or 0.0
    usdt_d = parse_number(data.get("USDT_D")) or 0.0
    dxy = parse_number(data.get("DXY")) or 100.0

    score = 0
    flags = []

    if abs(funding) > 0.012 and ls_ratio > 1.15:
        score += 20
        flags.append("Long positioning kalabaliklasiyor")
    elif abs(funding) > 0.008:
        score += 12
        flags.append("Funding asirilik sinyali veriyor")

    if ls_ratio > 1.18 or ls_ratio < 0.84:
        score += 10
        flags.append("Long/short dengesi bozuluyor")

    if taker > 1.12 or taker < 0.88:
        score += 12
        flags.append("Taker akis tek yone yigiliyor")

    if ls_ratio > 1.22 and taker > 1.10:
        score += 8
        flags.append("Momentum longlari asiri kalabalik")

    if vix >= 30:
        score += 24
        flags.append("Vol rejimi stresli")
    elif vix >= 24:
        score += 14
        flags.append("Vol baskisi yukseliyor")

    if abs(btc_change) >= 4:
        score += 10
        flags.append("Fiyat hareketi sok tipine yaklasti")

    macro_breadth = factors["participation"]["subfactors"]["macro"]["score"]
    crypto_breadth = factors["participation"]["subfactors"]["crypto"]["score"]
    if crypto_breadth < 45:
        score += 16
        flags.append("Crypto breadth dar tabanli")
    if macro_breadth < 45:
        score += 10
        flags.append("Macro breadth zayif")
    if abs(macro_breadth - crypto_breadth) >= 20:
        score += 10
        flags.append("Macro ve crypto katilimi ayrisiyor")

    if factors["liquidity"]["score"] > 60 and factors["positioning"]["score"] < 45:
        score += 12
        flags.append("Likidite var ama positioning asiri kalabalik")

    if factors["positioning"]["score"] < 40 and btc_change > 2:
        score += 10
        flags.append("Yukselis kalabalik trade ile devam ediyor")

    if etf_flow < 0 and btc_change > 0:
        score += 10
        flags.append("Fiyat-akis ayrismasi var")

    if usdt_d >= 7.5 or dxy >= 103:
        score += 8
        flags.append("Savunmaci nakit talebi yukseliyor")

    fragility = clamp_score(score)
    if not flags:
        flags.append("Belirgin kirilganlik birikimi yok")

    return {
        "score": fragility,
        "label": _fragility_label(fragility),
        "flags": flags[:4],
    }


def build_regime_scores(data: dict) -> dict:
    factors = {
        "liquidity": _build_liquidity_factor(data),
        "volatility": _build_volatility_factor(data),
        "positioning": _build_positioning_factor(data),
        "participation": _build_participation_factor(data),
    }

    for factor in factors.values():
        factor["contribution"] = round(factor["score"] * factor["weight"], 1)
        factor["weight_pct"] = int(round(factor["weight"] * 100))
        factor["trend_text"] = _factor_trend_text(factor["delta_7d"])
        factor["confidence"] = factor.get("confidence", _confidence_score(factor["metrics"]))
        factor["confidence_label"] = factor.get("confidence_label", _confidence_label(factor["confidence"]))
        factor["primary_support"] = max(factor["metrics"], key=lambda item: item["score"])["label"]
        factor["primary_risk"] = min(factor["metrics"], key=lambda item: item["score"])["label"]

    base_score = clamp_score(sum(factor["contribution"] for factor in factors.values()))
    fragility = _build_fragility(factors, data)
    penalty = round(fragility["score"] * 0.18, 1)
    overall = clamp_score(base_score - penalty)
    dominant_driver = max(factors.values(), key=lambda factor: factor["contribution"])
    weakest_driver = min(factors.values(), key=lambda factor: factor["score"])
    regime_band = _regime_band(overall)

    if overall >= 61 and fragility["score"] >= 70:
        overlay = "Risk-On but Crowded"
    elif overall >= 50 and fragility["score"] >= 50:
        overlay = "Constructive but Fragile"
    elif overall <= 40 and factors["liquidity"]["delta_7d"] > 2:
        overlay = "Defensive with Improving Liquidity"
    elif overall <= 40 and fragility["score"] <= 35:
        overlay = "Defensive but Stabilizing"
    elif 41 <= overall <= 60 and fragility["score"] >= 55:
        overlay = "Mixed with Hidden Stress"
    else:
        overlay = regime_band

    if overall >= 75 and fragility["score"] <= 40:
        bias = "Risk alimi destekleniyor; momentum genis tabanli kaliyor."
    elif overall >= 60 and fragility["score"] <= 60:
        bias = "Risk-on korunabilir ama pozisyon boyutlari secici tutulmali."
    elif overall >= 60:
        bias = "Yapıcı rejim var ancak crowding ve vol nedeniyle taktik kalmak gerekiyor."
    elif overall >= 45:
        bias = "Kararsiz rejim; teyit gelmeden agresif pozisyon almak icin erken."
    elif factors["liquidity"]["delta_7d"] > 2:
        bias = "Savunmaci kal ama likidite iyilesmesini yakindan izle."
    else:
        bias = "Savunmaci durus daha dogru; internaller net sekilde toparlanmadi."

    invalidate_conditions = []
    macro_breadth_factor = factors["participation"]["subfactors"]["macro"]
    crypto_breadth_factor = factors["participation"]["subfactors"]["crypto"]
    if macro_breadth_factor["score"] < 50:
        invalidate_conditions.append("Macro breadth zayiflarsa risk-on tezi sadece mega-cap omuzlarinda kalir.")
    if crypto_breadth_factor["score"] < 50:
        invalidate_conditions.append("Crypto breadth 50 altinda kalirsa hareket BTC-odakli ve dar tabanli hale gelir.")
    if abs(macro_breadth_factor["score"] - crypto_breadth_factor["score"]) >= 20:
        invalidate_conditions.append(
            "Macro ve crypto katilimi daha fazla ayrisirse composite participation kirilganlasir."
        )
    if factors["volatility"]["score"] < 55:
        invalidate_conditions.append(
            f"VIX {data.get('VIX', PLACEHOLDER)} uzerinde yukselmeye devam ederse stres artar."
        )
    if factors["positioning"]["score"] < 50:
        invalidate_conditions.append("Funding, L/S ve taker tek yone daha fazla yigilirsa crowding artar.")
    if factors["liquidity"]["score"] < 55:
        invalidate_conditions.append("ETF akisi zayiflar ve DXY sert yukselirse likidite desteği kaybolur.")
    if not invalidate_conditions:
        invalidate_conditions.append("Belirgin invalidate kosulu yok; mevcut rejim saglikli gorunuyor.")

    confidence = _regime_confidence_score(factors, overall, fragility, invalidate_conditions)

    watch_next = [
        f"ETF akisi {data.get('ETF_FLOW_TOTAL', PLACEHOLDER)} ve DXY {data.get('DXY', PLACEHOLDER)}",
        f"Funding {data.get('FR', PLACEHOLDER)} | L/S {data.get('LS_Ratio', PLACEHOLDER)} | Taker {data.get('Taker', PLACEHOLDER)}",
        f"Macro breadth RSP {data.get('RSP_C', PLACEHOLDER)} | IWM {data.get('IWM_C', PLACEHOLDER)} | SPY {data.get('SPY_C', PLACEHOLDER)}",
        f"Crypto breadth TOTAL3 {data.get('TOTAL3_CAP', PLACEHOLDER)} | BTC Dom {data.get('Dom', PLACEHOLDER)} | VIX {data.get('VIX', PLACEHOLDER)}",
    ]

    return {
        "overall": overall,
        "base_score": base_score,
        "penalty": penalty,
        "regime_band": regime_band,
        "overlay": overlay,
        "fragility": fragility,
        "dominant_driver": dominant_driver["label"],
        "weakest_driver": weakest_driver["label"],
        "summary": f"{dominant_driver['label']} rejimi tasiyor, {weakest_driver['label']} ise en zayif halka.",
        "confidence": confidence,
        "confidence_label": _regime_confidence_label(confidence, fragility["score"]),
        "bias": bias,
        "invalidate_conditions": invalidate_conditions[:3],
        "watch_next": watch_next,
        "subscores": {
            "Liquidity": factors["liquidity"]["score"],
            "Volatility": factors["volatility"]["score"],
            "Positioning": factors["positioning"]["score"],
            "Participation": factors["participation"]["score"],
        },
        "factors": list(factors.values()),
        "participation": factors["participation"],
    }


def build_scenario_matrix(data: dict) -> list[dict]:
    current_price = parse_number(data.get("BTC_P")) or parse_number(data.get("BTC_Now")) or 0.0
    support = parse_number(data.get("Sup_Wall")) or (current_price * 0.98 if current_price else 0.0)
    resistance = parse_number(data.get("Res_Wall")) or (current_price * 1.02 if current_price else 0.0)

    return [
        {
            "Scenario": "Bullish",
            "Trigger": f"Fiyat {resistance:,.0f} ustu kalirsa" if resistance else PLACEHOLDER,
            "Follow-through": f"ETF akisi {data.get('ETF_FLOW_TOTAL', PLACEHOLDER)} ve funding {data.get('FR', PLACEHOLDER)} destekleyici olmali",
        },
        {
            "Scenario": "Base",
            "Trigger": (
                f"Fiyat {support:,.0f} - {resistance:,.0f} araliginda kalirsa"
                if support and resistance
                else PLACEHOLDER
            ),
            "Follow-through": f"VIX {data.get('VIX', PLACEHOLDER)} ve USDT.D {data.get('USDT_D', PLACEHOLDER)} dengeyi korumali",
        },
        {
            "Scenario": "Bear",
            "Trigger": f"Fiyat {support:,.0f} alti kapanirsa" if support else PLACEHOLDER,
            "Follow-through": f"Funding {data.get('FR', PLACEHOLDER)} ve ETF netflow {data.get('ETF_FLOW_TOTAL', PLACEHOLDER)} zayiflamayi teyit etmeli",
        },
    ]


def build_alerts(data: dict, thresholds: dict) -> list[dict]:
    alerts = []
    funding  = parse_number(data.get("FR"))
    vix      = parse_number(data.get("VIX"))
    etf_flow = parse_number(data.get("ETF_FLOW_TOTAL"))
    dxy      = parse_number(data.get("DXY"))

    funding_above = thresholds.get("funding_above")
    vix_above     = thresholds.get("vix_above")
    etf_below     = thresholds.get("etf_flow_below")
    dxy_above     = thresholds.get("dxy_above")

    if funding is not None and funding_above is not None and funding > funding_above:
        alerts.append(
            {
                "title": "Funding alarmi",
                "detail": f"Funding {data.get('FR', PLACEHOLDER)} | esik {funding_above:.4f}",
                "level": "warning",
            }
        )
    if vix is not None and vix_above is not None and vix > vix_above:
        alerts.append(
            {
                "title": "VIX alarmi",
                "detail": f"VIX {data.get('VIX', PLACEHOLDER)} | esik {vix_above:.2f}",
                "level": "error",
            }
        )
    if etf_flow is not None and etf_below is not None and etf_flow < etf_below:
        alerts.append(
            {
                "title": "ETF alarmi",
                "detail": f"ETF netflow {data.get('ETF_FLOW_TOTAL', PLACEHOLDER)} | esik {etf_below:.1f}",
                "level": "error",
            }
        )
    if dxy is not None and dxy_above is not None and dxy > dxy_above:
        alerts.append(
            {
                "title": "DXY alarmi",
                "detail": f"DXY {data.get('DXY', PLACEHOLDER)} | esik {dxy_above:.2f} — güçlü dolar kripto için baskıcı",
                "level": "warning",
            }
        )

    return alerts


def build_pinned_metrics(data: dict, metric_keys: list[str]) -> list[tuple[str, str, str]]:
    items = []
    for key in metric_keys[:8]:
        label = METRIC_LABELS.get(key, key)
        value = data.get(key, PLACEHOLDER)
        delta_key = f"{key}_C"
        delta = data.get(delta_key, "") if delta_key in data else ""
        items.append((label, value, delta))
    return items


def build_daily_summary_markdown(
    data: dict, brief: dict, analytics: dict, alerts: list[dict], health_summary: dict
) -> str:
    lines = [
        "# Gunluk Ozet",
        "",
        f"- BTC: {data.get('BTC_P', PLACEHOLDER)} | 24s {data.get('BTC_C', PLACEHOLDER)}",
        f"- Rejim skoru: {analytics['scores']['overall']}/100",
        f"- Likidite: {brief['liquidity']['title']}",
        f"- Pozisyonlanma: {brief['positioning']['title']}",
        f"- Odak seviye: {brief['focus']['detail']}",
        f"- Veri sagligi: {health_summary.get('healthy_sources', 0)} saglikli / {len(health_summary.get('failed_sources', []))} problemli / {len(health_summary.get('stale_sources', []))} stale",
        "",
        "## Neden boyle dusunuyorum?",
    ]
    for key in ["regime", "positioning", "liquidity", "focus"]:
        lines.append(f"- {brief[key]['title']}: " + " | ".join(brief[key].get("why", [])))
    if alerts:
        lines.extend(["", "## Aktif Alarmlar"])
        for alert in alerts:
            lines.append(f"- {alert['title']}: {alert['detail']}")
    lines.extend(["", "## Senaryo Matrisi"])
    for row in analytics["scenarios"]:
        lines.append(f"- {row['Scenario']}: {row['Trigger']} | {row['Follow-through']}")
    return "\n".join(lines)


def markdown_to_basic_pdf_bytes(markdown_text: str) -> bytes:
    safe_text = markdown_text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    lines = [line[:100] for line in safe_text.splitlines() if line.strip()]
    if not lines:
        lines = ["Gunluk Ozet"]

    content_lines = ["BT", "/F1 11 Tf", "50 780 Td"]
    first = True
    for line in lines[:45]:
        if first:
            content_lines.append(f"({line}) Tj")
            first = False
        else:
            content_lines.append("0 -16 Td")
            content_lines.append(f"({line}) Tj")
    content_lines.append("ET")
    stream = "\n".join(content_lines).encode("latin-1", errors="ignore")

    objects = []
    objects.append(b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n")
    objects.append(b"2 0 obj << /Type /Pages /Count 1 /Kids [3 0 R] >> endobj\n")
    objects.append(
        b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >> endobj\n"
    )
    objects.append(f"4 0 obj << /Length {len(stream)} >> stream\n".encode("latin-1") + stream + b"\nendstream endobj\n")
    objects.append(b"5 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n")

    buffer = BytesIO()
    buffer.write(b"%PDF-1.4\n")
    offsets = [0]
    for obj in objects:
        offsets.append(buffer.tell())
        buffer.write(obj)
    xref_pos = buffer.tell()
    buffer.write(f"xref\n0 {len(objects) + 1}\n".encode("latin-1"))
    buffer.write(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        buffer.write(f"{offset:010d} 00000 n \n".encode("latin-1"))
    buffer.write(f"trailer << /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF".encode("latin-1"))
    return buffer.getvalue()


def build_analytics_payload(data: dict) -> dict:
    scores = build_regime_scores(data)
    return {
        "scores":    scores,
        "scenarios": build_scenario_matrix(data),
        "decision":  build_decision_verdict(data, scores),
        "risk_on_off": build_risk_on_off(data),
    }


# ─── DECISION VERDICT (MQS + EWS) ────────────────────────────────────────────
#
# MQS — Market Quality Score
#   "Piyasa ortamı işlem için elverişli mi?"
#   Mevcut 4 faktörden türetilir; ağırlıklar biraz farklı yorumlanır.
#
# EWS — Execution Window Score
#   "Şu an işlem zamanlaması uygun mu?"
#   Kırılmalar tutunuyor mu, geri çekilmeler fırsat mı?
#   Order book + volatility + momentum odaklı.
#
# Verdict: EVET / DİKKAT / HAYIR
#

def _build_mqs(scores: dict) -> dict:
    """
    Market Quality Score — piyasa ortamının işlem için ne kadar elverişli olduğunu ölçer.
    Mevcut faktörlerin ağırlıklı kompoziti; fragility cezası uygulanır.
    
    Bileşenler:
      Liquidity    %30  — para akışı ve dolar baskısı
      Volatility   %25  — VIX ve BTC volatilitesi
      Positioning  %20  — crowding ve dengesiz pozisyonlar
      Participation %25 — macro + crypto breadth uyumu
    """
    factors = {f["key"]: f for f in scores["factors"]}
    
    liq   = factors["liquidity"]["score"]
    vol   = factors["volatility"]["score"]
    pos   = factors["positioning"]["score"]
    part  = factors["participation"]["score"]
    frag  = scores["fragility"]["score"]
    
    base = (
        liq  * 0.30 +
        vol  * 0.25 +
        pos  * 0.20 +
        part * 0.25
    )
    
    # Fragility cezası: fragility 35 üstünde her puan %0.22 düşürür
    frag_penalty = max(0.0, (frag - 35) * 0.22)
    
    # Alignment gap cezası
    m_bread = scores["participation"]["subfactors"]["macro"]["score"]
    c_bread = scores["participation"]["subfactors"]["crypto"]["score"]
    gap_penalty = max(0.0, (abs(m_bread - c_bread) - 10) * 0.25)
    
    mqs = clamp_score(base - frag_penalty - gap_penalty)
    
    # Bileşen dağılımı (görsel bar için)
    components = [
        {"key": "liquidity",    "label": "Liquidity",    "score": liq,  "weight": 30},
        {"key": "volatility",   "label": "Volatility",   "score": vol,  "weight": 25},
        {"key": "positioning",  "label": "Positioning",  "score": pos,  "weight": 20},
        {"key": "participation","label": "Participation","score": part, "weight": 25},
    ]
    
    # En güçlü ve en zayıf bileşen
    strongest = max(components, key=lambda c: c["score"])
    weakest   = min(components, key=lambda c: c["score"])
    
    if mqs >= 62:
        label = "Elverişli"
        color = "positive"
    elif mqs >= 45:
        label = "Karışık"
        color = "warning"
    else:
        label = "Elverişsiz"
        color = "negative"
    
    return {
        "score":      mqs,
        "label":      label,
        "color":      color,
        "components": components,
        "strongest":  strongest["label"],
        "weakest":    weakest["label"],
        "frag_penalty":  round(frag_penalty, 1),
        "gap_penalty":   round(gap_penalty, 1),
    }


def _build_ews(data: dict, scores: dict) -> dict:
    """
    Execution Window Score — şu an işlem zamanlaması uygun mu?
    Order book, momentum ve volatility hızına bakarak kırılma/geri çekilme
    kalitesini değerlendirir.
    
    Bileşenler:
      Order book signal  %30  — destek/direnç sağlamlığı
      Momentum quality   %25  — fiyat-akış uyumu
      Vol regime         %25  — ani şok riski
      Positioning room   %20  — squeeze ve crowding alanı
    """
    factors = {f["key"]: f for f in scores["factors"]}
    
    # Order book kalitesi
    ob_signal = data.get("ORDERBOOK_SIGNAL", "")
    ob_score = 55  # varsayılan nötr
    if isinstance(ob_signal, str):
        sig_lower = ob_signal.lower()
        if any(w in sig_lower for w in ["strong buy", "buy", "support"]):
            ob_score = 78
        elif any(w in sig_lower for w in ["strong sell", "sell", "resistance"]):
            ob_score = 28
        elif any(w in sig_lower for w in ["neutral", "mixed"]):
            ob_score = 52

    # Momentum kalitesi — fiyat hareketi + taker uyumu
    btc_change = parse_number(data.get("BTC_C")) or 0.0
    taker      = parse_number(data.get("Taker")) or 1.0
    etf_flow   = parse_number(data.get("ETF_FLOW_TOTAL")) or 0.0
    
    # Fiyat yönü ile taker ve ETF uyuyor mu?
    momentum_score = 50
    if btc_change > 0 and taker > 1.02 and etf_flow > 0:
        momentum_score = 80
    elif btc_change > 0 and taker > 1.02:
        momentum_score = 68
    elif btc_change < 0 and taker < 0.98 and etf_flow < 0:
        momentum_score = 22  # güçlü aşağı momentum
    elif btc_change < 0 and taker < 0.98:
        momentum_score = 35
    elif abs(btc_change) < 0.5:
        momentum_score = 55  # düz, belirsiz
    
    # Vol rejimi — ani şok riski
    vol_score = factors["volatility"]["score"]
    
    # Positioning alanı — crowding ne kadar?
    pos_score = factors["positioning"]["score"]
    
    base = (
        ob_score       * 0.30 +
        momentum_score * 0.25 +
        vol_score      * 0.25 +
        pos_score      * 0.20
    )
    
    ews = clamp_score(base)
    
    components = [
        {"key": "orderbook",  "label": "Order Book",  "score": ob_score,       "weight": 30},
        {"key": "momentum",   "label": "Momentum",    "score": momentum_score,  "weight": 25},
        {"key": "volatility", "label": "Vol Regime",  "score": vol_score,       "weight": 25},
        {"key": "positioning","label": "Positioning Room","score": pos_score,   "weight": 20},
    ]
    
    strongest = max(components, key=lambda c: c["score"])
    weakest   = min(components, key=lambda c: c["score"])
    
    if ews >= 62:
        label = "Pencere Açık"
        color = "positive"
    elif ews >= 45:
        label = "Dikkatli Ol"
        color = "warning"
    else:
        label = "Pencere Kapalı"
        color = "negative"
    
    # Destek / direnç seviyeleri
    sup = data.get("Sup_Wall", "-")
    res = data.get("Res_Wall", "-")
    
    return {
        "score":      ews,
        "label":      label,
        "color":      color,
        "components": components,
        "strongest":  strongest["label"],
        "weakest":    weakest["label"],
        "support":    sup,
        "resistance": res,
        "ob_signal":  ob_signal or "-",
    }


def _build_verdict(mqs: dict, ews: dict, scores: dict) -> dict:
    """
    EVET / DİKKAT / HAYIR kararını üretir.
    
    EVET:    MQS ≥ 60 VE EWS ≥ 58 VE fragility < 65
    DİKKAT: Yukarıdakilerin bazıları sağlanıyor ama hepsi değil
    HAYIR:   MQS < 45 VEYA EWS < 40 VEYA fragility ≥ 70
    """
    mqs_s  = mqs["score"]
    ews_s  = ews["score"]
    frag_s = scores["fragility"]["score"]
    overall = scores["overall"]
    
    # HAYIR koşulları
    hard_no = (
        mqs_s < 36 or
        ews_s < 34 or
        frag_s >= 72 or
        overall < 30
    )
    
    # EVET koşulları
    strong_yes = (
        mqs_s >= 60 and
        ews_s >= 58 and
        frag_s < 58 and
        overall >= 55
    )
    
    # DİKKAT koşulları — ikisi arasında kalan alan
    # hard_no değil ve strong_yes değilse otomatik DİKKAT devreye girer
    # Ek kontrol: en az biri 45+ olmalı
    at_least_one_ok = mqs_s >= 45 or ews_s >= 45
    
    if hard_no and not at_least_one_ok:
        verdict = "HAYIR"
        verdict_en = "NO TRADE"
        color = "negative"
        summary = "Piyasa ortamı veya işlem penceresi yeni pozisyon için elverişli değil. Kenarda dur, teyit bekle."
        size_guidance = "0%"
        action = "Kenarda kal. Mevcut pozisyonları koru, yeni açma."
    elif hard_no:
        verdict = "DİKKAT"
        verdict_en = "SELECTIVE"
        color = "warning"
        summary = "Koşullar zayıf. Mevcut açık pozisyonları koru, yeni pozisyon açmaktan kaçın."
        size_guidance = "0% — yeni pozisyon yok"
        action = "Yeni pozisyon açma. Mevcut pozisyonlarda stop'ları sıkılaştır."
    elif strong_yes:
        verdict = "EVET"
        verdict_en = "GO"
        color = "positive"
        summary = "Piyasa kalitesi ve işlem penceresi uyumlu. Teyitli setup'larda pozisyon alınabilir."
        # Boyut önerisi: overall ve MQS'e göre
        if overall >= 70 and mqs_s >= 70:
            size_guidance = "Tam boyut"
        else:
            size_guidance = "Seçici / yarı boyut"
        action = "Teyitli setup'larda pozisyon alınabilir. Boyut: " + size_guidance
    else:
        verdict = "DİKKAT"
        verdict_en = "SELECTIVE"
        color = "warning"
        summary = "Karma sinyal. Sadece en yüksek kaliteli setup'larda, küçük boyutle işlem yapılabilir."
        size_guidance = "Küçük boyut / seçici"
        action = "Yalnızca en güçlü teyitlerde, küçük boyutle işlem. Agresif pozisyon alma."
    
    # Hangi koşul kararı belirliyor?
    decisive_factors = []
    if mqs_s < 45:
        decisive_factors.append(f"MQS düşük ({mqs_s}/100)")
    if ews_s < 45:
        decisive_factors.append(f"EWS düşük ({ews_s}/100)")
    if frag_s >= 58:
        decisive_factors.append(f"Fragility yüksek ({frag_s}/100)")
    if mqs_s >= 60:
        decisive_factors.append(f"MQS destekleyici ({mqs_s}/100)")
    if ews_s >= 58:
        decisive_factors.append(f"EWS pencere açık ({ews_s}/100)")
    
    return {
        "verdict":         verdict,
        "verdict_en":      verdict_en,
        "color":           color,
        "summary":         summary,
        "action":          action,
        "size_guidance":   size_guidance,
        "decisive_factors": decisive_factors[:3],
        "mqs_score":       mqs_s,
        "ews_score":       ews_s,
        "frag_score":      frag_s,
        "overall":         overall,
    }


def build_decision_verdict(data: dict, scores: dict) -> dict:
    """
    Ana giriş noktası. analytics payload'a eklenir.
    Döner:
      verdict  — EVET / DİKKAT / HAYIR kararı
      mqs      — Market Quality Score detayı
      ews      — Execution Window Score detayı
    """
    mqs     = _build_mqs(scores)
    ews     = _build_ews(data, scores)
    verdict = _build_verdict(mqs, ews, scores)
    return {
        "verdict": verdict,
        "mqs":     mqs,
        "ews":     ews,
    }


# ─── RISK ON/OFF INDICATOR ────────────────────────────────────────────────────
#
# 4 bölgesel blok + makro stres katmanı:
#   ASIA     — Nikkei, HSI  (ağırlık %18)
#   EUROPE   — DAX, FTSE    (ağırlık %16)
#   US       — SP500, NASDAQ (ağırlık %18)
#   CRYPTO   — BTC, ETH     (ağırlık %18)
#   MACRO STRESS — DXY, VIX, US10Y, OIL, GOLD (ağırlık %30)
#
# Her bölge için:
#   - Bileşik skor (ağırlıklı değişim ortalaması)
#   - Breadth (kaç tanesi pozitif)
#   - Agreement (breadth / toplam, %)
#   - Sinyal: RISK ON / NEUTRAL / RISK OFF
#
# Global skor: bölge skorlarının ağırlıklı ortalaması
# Sync Q:    bölgeler arası uyum (agreement)
# Agree Q:   tüm varlıklar içinde pozitif olanların oranı
#

def _pct(value) -> float | None:
    """'%1.23' veya '1.23%' veya '1.23' → float veya None"""
    v = parse_number(value)
    return v


def _weighted_change_score(changes: list[float | None], weights: list[float]) -> float:
    """Ağırlıklı değişim ortalaması → normalize edilmiş 0-100 skor"""
    total_w = 0.0
    total_s = 0.0
    for c, w in zip(changes, weights):
        if c is None:
            continue
        # +/-5% aralığını 0-100'e normalize et
        normalized = max(0.0, min(100.0, (c + 5.0) / 10.0 * 100.0))
        total_s += normalized * w
        total_w += w
    if total_w == 0:
        return 50.0
    return total_s / total_w


def _breadth(changes: list[float | None]) -> tuple[int, int]:
    """(pozitif_sayısı, toplam_geçerli_sayısı)"""
    valid = [c for c in changes if c is not None]
    pos   = sum(1 for c in valid if c > 0)
    return pos, len(valid)


def _region_signal(score: float, breadth_pct: float) -> str:
    if score >= 60 and breadth_pct >= 60:
        return "RISK ON"
    if score <= 40 or breadth_pct <= 35:
        return "RISK OFF"
    return "NEUTRAL"


def _region_color(signal: str) -> str:
    return {"RISK ON": "positive", "NEUTRAL": "warning", "RISK OFF": "negative"}.get(signal, "warning")


def _build_region(
    name: str,
    assets: list[tuple[str, str, float]],   # (label, change_key, weight)
    data: dict,
    region_weight: float,
) -> dict:
    changes = [_pct(data.get(ck)) for _, ck, _ in assets]
    weights = [w for _, _, w in assets]
    pos, total = _breadth(changes)
    brd_pct    = (pos / total * 100) if total else 0.0
    score      = _weighted_change_score(changes, weights)
    signal     = _region_signal(score, brd_pct)

    # Değişim değerlerini gösterim için formatla
    asset_rows = []
    for (lbl, ck, _), chg in zip(assets, changes):
        asset_rows.append({
            "label":  lbl,
            "key":    ck,
            "change": f"{chg:+.2f}%" if chg is not None else "-",
            "value":  chg,
            "pos":    chg is not None and chg > 0,
        })

    return {
        "name":          name,
        "score":         round(score, 1),
        "weight":        region_weight,
        "signal":        signal,
        "color":         _region_color(signal),
        "breadth_pos":   pos,
        "breadth_total": total,
        "breadth_pct":   round(brd_pct, 0),
        "agree_pct":     round(brd_pct, 0),
        "assets":        asset_rows,
        "coverage":      f"{total}/{len(assets)}",
    }


def _build_macro_stress_block(data: dict) -> dict:
    """
    DXY, VIX, US10Y → stres göstergeleri (yüksek = risk-off sinyali → ters çevrilir)
    OIL, GOLD → karışık sinyal (her ikisi de izlenir)
    """
    dxy_c   = _pct(data.get("DXY_C"))
    vix_c   = _pct(data.get("VIX_C"))
    us10y_c = _pct(data.get("US10Y_C"))
    oil_c   = _pct(data.get("OIL_C"))
    gold_c  = _pct(data.get("GOLD_C"))

    # Stres bileşenleri: DXY↑ VIX↑ US10Y↑ = risk-off → ters normalize
    stress_changes  = [dxy_c, vix_c, us10y_c]
    stress_weights  = [0.25, 0.30, 0.20]
    stress_score_raw = _weighted_change_score(stress_changes, stress_weights)
    # Ters çevir: yüksek stres = düşük risk-on skoru
    stress_score = 100.0 - stress_score_raw

    # Emtia (OIL↑ + GOLD↑ birlikte → risk-off, ayrı ayrı karma sinyal)
    commodity_score = 50.0
    if oil_c is not None and gold_c is not None:
        if oil_c > 0 and gold_c > 0:
            commodity_score = 35.0  # her ikisi yukarı → risk-off ağırlıklı
        elif oil_c > 0 and gold_c < 0:
            commodity_score = 55.0
        elif oil_c < 0 and gold_c < 0:
            commodity_score = 65.0  # her ikisi aşağı → risk-on ağırlıklı
        else:
            commodity_score = 50.0

    final_score = stress_score * 0.75 + commodity_score * 0.25

    assets = [
        {"label": "DXY",   "key": "DXY_C",   "change": f"{dxy_c:+.2f}%"   if dxy_c   is not None else "-", "value": dxy_c,   "pos": dxy_c   is not None and dxy_c   < 0,  "risk_sign": -1},  # DXY düşüşü risk-on
        {"label": "VIX",   "key": "VIX_C",   "change": f"{vix_c:+.2f}%"   if vix_c   is not None else "-", "value": vix_c,   "pos": vix_c   is not None and vix_c   < 0,  "risk_sign": -1},  # VIX düşüşü risk-on
        {"label": "US10Y", "key": "US10Y_C", "change": f"{us10y_c:+.2f}%" if us10y_c is not None else "-", "value": us10y_c, "pos": us10y_c is not None and us10y_c < 0, "risk_sign": -1},  # yield düşüşü risk-on
        {"label": "OIL",   "key": "OIL_C",   "change": f"{oil_c:+.2f}%"   if oil_c   is not None else "-", "value": oil_c,   "pos": oil_c   is not None and oil_c   < 0,  "risk_sign": -1},  # petrol düşüşü risk-on
        {"label": "GOLD",  "key": "GOLD_C",  "change": f"{gold_c:+.2f}%"  if gold_c  is not None else "-", "value": gold_c,  "pos": gold_c  is not None and gold_c  < 0,  "risk_sign": -1},  # altın düşüşü risk-on
    ]

    signal = _region_signal(final_score, 50.0)
    return {
        "name":    "MACRO STRESS",
        "score":   round(final_score, 1),
        "weight":  0.30,
        "signal":  signal,
        "color":   _region_color(signal),
        "assets":  assets,
        "dxy":     f"{dxy_c:+.2f}%"   if dxy_c   is not None else "-",
        "vix":     f"{vix_c:+.2f}%"   if vix_c   is not None else "-",
        "us10y":   f"{us10y_c:+.2f}%" if us10y_c is not None else "-",
        "oil":     f"{oil_c:+.2f}%"   if oil_c   is not None else "-",
        "gold":    f"{gold_c:+.2f}%"  if gold_c  is not None else "-",
        "coverage": f"{sum(1 for v in [dxy_c,vix_c,us10y_c,oil_c,gold_c] if v is not None)}/5",
    }


def build_risk_on_off(data: dict) -> dict:
    """
    Global Risk On/Off göstergesi.
    Tüm bölgelerin ağırlıklı kompozit skoru.
    
    Döner:
      global_score   — 0-100 composite
      global_signal  — RISK ON / NEUTRAL / RISK OFF
      strict_score   — sadece yüksek güven bölgelerinden
      live_score     — tüm mevcut veriden
      sync_q         — bölgeler arası uyum skoru (0-100)
      agree_q        — tüm varlıklar içinde pozitif % (0-100)
      regions        — 4 bölgesel blok
      macro_stress   — makro stres katmanı
      drivers        — en güçlü 2 sürücü
      drags          — en güçlü 2 frenleme
      coverage       — kaç/toplam varlık verisi geldi
    """
    # ── Bölgeler ──────────────────────────────────────────────────────────────
    asia = _build_region("ASIA", [
        ("N225",  "NIKKEI_C", 0.40),
        ("HSI",   "HSI_C",    0.35),
        ("SHCOMP","CSI300_C", 0.25),
    ], data, region_weight=0.18)

    europe = _build_region("EUROPE", [
        ("DAX",  "DAX_C",  0.50),
        ("FTSE", "FTSE_C", 0.50),
    ], data, region_weight=0.16)

    us = _build_region("US FUTURES", [
        ("SP500",  "SP500_C",  0.50),
        ("NASDAQ", "NASDAQ_C", 0.50),
    ], data, region_weight=0.18)

    # BTC ve ETH değişimleri
    btc_c = _pct(data.get("BTC_C"))
    eth_c_raw = data.get("ETH_C")
    # ETH değişimi: ETH_P yoksa BTC ile birlikte gelmeyebilir, BTC_C proxy kullan
    eth_c = _pct(eth_c_raw) if eth_c_raw and eth_c_raw != "-" else (btc_c * 0.9 if btc_c else None)

    crypto = _build_region("CRYPTO", [
        ("BTC", "BTC_C",  0.55),
        ("ETH", "ETH_C",  0.45),
    ], data, region_weight=0.18)

    macro_stress = _build_macro_stress_block(data)

    # ── Global skor ───────────────────────────────────────────────────────────
    regions = [asia, europe, us, crypto]
    global_score_raw = sum(
        r["score"] * r["weight"] for r in regions
    ) + macro_stress["score"] * macro_stress["weight"]

    total_weight = sum(r["weight"] for r in regions) + macro_stress["weight"]
    global_score = clamp_score(global_score_raw / total_weight * (total_weight / 1.0))

    # Strict score: sadece tam coverage olan bölgeler
    strict_regions = [r for r in regions if r["breadth_total"] >= 2]
    if strict_regions:
        strict_raw = sum(r["score"] * r["weight"] for r in strict_regions)
        strict_w   = sum(r["weight"] for r in strict_regions)
        strict_score = clamp_score((strict_raw / strict_w) * 0.7 + macro_stress["score"] * 0.3)
    else:
        strict_score = global_score

    # ── Sync Q: bölgeler arası uyum ──────────────────────────────────────────
    # Bölge sinyalleri ne kadar birbirine benziyor?
    signals = [r["signal"] for r in regions]
    risk_on_count  = signals.count("RISK ON")
    risk_off_count = signals.count("RISK OFF")
    neutral_count  = signals.count("NEUTRAL")
    dominant       = max(risk_on_count, risk_off_count, neutral_count)
    sync_q         = clamp_score(dominant / len(signals) * 100)

    # ── Agree Q: tüm varlıklarda pozitif % ───────────────────────────────────
    all_assets = []
    for r in regions:
        all_assets.extend(r["assets"])
    all_assets.extend(macro_stress["assets"])
    total_assets   = len([a for a in all_assets if a["value"] is not None])
    positive_assets = len([a for a in all_assets if a["pos"] and a["value"] is not None])
    agree_q = clamp_score((positive_assets / total_assets * 100) if total_assets else 50)

    # ── Global sinyal ─────────────────────────────────────────────────────────
    if global_score >= 60 and sync_q >= 55:
        global_signal = "RISK ON"
        global_color  = "positive"
    elif global_score <= 40 or (risk_off_count >= 2 and global_score < 50):
        global_signal = "RISK OFF"
        global_color  = "negative"
    else:
        global_signal = "NEUTRAL"
        global_color  = "warning"

    # Strict signal
    if strict_score >= 62:
        strict_signal = "RISK ON"
        strict_color  = "positive"
    elif strict_score <= 38:
        strict_signal = "RISK OFF"
        strict_color  = "negative"
    else:
        strict_signal = "NEUTRAL"
        strict_color  = "warning"

    # ── Sürücüler ve frenleme ─────────────────────────────────────────────────
    # Önce raw asset hareketlerini risk_sign ile değerlendir
    scored_assets_raw = []
    for a in all_assets:
        if a["value"] is None:
            continue
        risk_sign = a.get("risk_sign", 1)
        risk_delta = a["value"] * risk_sign
        scored_assets_raw.append({"label": a["label"], "change": a["change"], "risk_delta": risk_delta})

    # Cross-asset ratio sinyallerini ekle: ETH/BTC, BTC/NQ, BTC/GOLD
    btc_c_d  = _pct(data.get("BTC_C"))
    eth_c_d  = _pct(data.get("ETH_C"))
    if eth_c_d is None and btc_c_d is not None:
        eth_c_d = btc_c_d * 0.9
    nq_c_d   = _pct(data.get("NASDAQ_C"))
    gold_c_d = _pct(data.get("GOLD_C"))
    _scale = 3.0
    for lbl, left, right in [("ETH/BTC", eth_c_d, btc_c_d), ("BTC/NQ", btc_c_d, nq_c_d), ("BTC/GOLD", btc_c_d, gold_c_d)]:
        if left is not None and right is not None:
            sp = left - right
            scored_assets_raw.append({"label": lbl, "change": f"{sp:+.2f}pp", "risk_delta": sp / _scale})

    max_abs = max((abs(a["risk_delta"]) for a in scored_assets_raw), default=1.0)
    def _dpay(a: dict) -> dict:
        mag = abs(a["risk_delta"])
        return {
            "label": a["label"],
            "change": a["change"],
            "impact": round(a["risk_delta"], 2),
            "bar_pct": max(20, min(100, int(round(20 + 80 * mag / max_abs)) if max_abs > 0 else 20)),
        }
    drivers = [_dpay(a) for a in sorted((x for x in scored_assets_raw if x["risk_delta"] > 0), key=lambda x: x["risk_delta"], reverse=True)[:3]]
    drags   = [_dpay(a) for a in sorted((x for x in scored_assets_raw if x["risk_delta"] < 0), key=lambda x: x["risk_delta"])[:3]]

    # ── Cross-asset transmission ────────────────────────────────────────────
    def _pair_item_d(pair, left, right, low=-3.0, high=3.0):
        if left is None or right is None:
            return None
        spread = left - right
        score = max(0, min(100, int((spread - low) / (high - low) * 100)))
        signal = "POSITIVE" if spread >= 0.60 else "NEGATIVE" if spread <= -0.60 else "NEUTRAL"
        return {"pair": pair, "spread": round(spread,2), "display": f"{spread:+.2f}", "score": score, "signal": signal, "contribution": round((score-50)/10,2)}
    btc_cx = _pct(data.get("BTC_C"))
    eth_raw_cx = data.get("ETH_C")
    eth_cx = _pct(eth_raw_cx) if eth_raw_cx and eth_raw_cx != "-" else (btc_cx * 0.9 if btc_cx else None)
    nq_cx  = _pct(data.get("NASDAQ_C"))
    gold_cx = _pct(data.get("GOLD_C"))
    tx_items = [x for x in [
        _pair_item_d("ETH/BTC", eth_cx, btc_cx),
        _pair_item_d("BTC/NQ",  btc_cx, nq_cx),
        _pair_item_d("BTC/GOLD", btc_cx, gold_cx),
    ] if x is not None]
    tx_score = max(0, min(100, int(sum(i["score"] for i in tx_items) / len(tx_items)))) if tx_items else 50
    tx_signal = "RISK ON" if tx_score >= 56 else "RISK OFF" if tx_score <= 44 else "NEUTRAL"
    cross_asset_transmission = {"score": tx_score, "signal": tx_signal, "items": tx_items}

    coverage = f"{total_assets}/{len(all_assets)}"

    return {
        "global_score":  global_score,
        "global_signal": global_signal,
        "global_color":  global_color,
        "strict_score":  strict_score,
        "strict_signal": strict_signal,
        "strict_color":  strict_color,
        "live_score":    global_score,
        "sync_q":        sync_q,
        "agree_q":       agree_q,
        "regions":       regions,
        "macro_stress":  macro_stress,
        "drivers":       drivers,
        "drags":         drags,
        "coverage":      coverage,
        "risk_on_count":  risk_on_count,
        "neutral_count":  neutral_count,
        "risk_off_count": risk_off_count,
        "cross_asset_transmission": cross_asset_transmission,
    }
