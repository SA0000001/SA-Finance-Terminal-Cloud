PLACEHOLDER = "-"


def badge_class(text: str):
    text = (text or "").lower()
    if any(word in text for word in ["long", "guclu", "risk", "destek", "akiyor", "pozitif"]):
        return "signal-long"
    if any(word in text for word in ["short", "baski", "direnc", "savunmaci", "negatif"]):
        return "signal-short"
    return "signal-neutral"


def extract_wall_levels(bids, asks, noise=250, bucket_size=100):
    if not bids or not asks:
        raise ValueError("order book is empty")

    current_price = bids[0][0]
    max_distance = current_price * 0.08
    sane_bids = [
        (price, qty) for price, qty in bids if 0 < price <= current_price and (current_price - price) <= max_distance
    ] or bids
    sane_asks = [
        (price, qty) for price, qty in asks if price >= current_price and (price - current_price) <= max_distance
    ] or asks

    filtered_bids = [(price, qty) for price, qty in sane_bids if price < current_price - noise] or sane_bids[
        len(sane_bids) // 2 :
    ]
    filtered_asks = [(price, qty) for price, qty in sane_asks if price > current_price + noise] or sane_asks[
        len(sane_asks) // 2 :
    ]

    def strongest_bucket(levels, bucket_fn):
        buckets = {}
        for price, qty in levels:
            bucket_key = bucket_fn(price)
            buckets[bucket_key] = buckets.get(bucket_key, 0.0) + qty
        return max(buckets.items(), key=lambda item: item[1])

    support_price, support_volume = strongest_bucket(
        filtered_bids, lambda price: int(price / bucket_size) * bucket_size
    )
    resistance_price, resistance_volume = strongest_bucket(
        filtered_asks,
        lambda price: int((price / bucket_size) + 1) * bucket_size,
    )

    distance_support = current_price - support_price
    distance_resistance = resistance_price - current_price
    if distance_resistance < distance_support:
        status = "Dirence yakin"
    elif distance_support < distance_resistance:
        status = "Destege yakin"
    else:
        status = "Kanal ortasi"

    return {
        "current_price": current_price,
        "support_price": support_price,
        "support_volume": support_volume,
        "resistance_price": resistance_price,
        "resistance_volume": resistance_volume,
        "status": status,
    }


def wall_field(prefix, field):
    return f"{prefix}_{field}" if prefix else field


def format_btc_volume(volume):
    if volume is None:
        return PLACEHOLDER
    if volume >= 10:
        return f"{volume:,.0f} BTC"
    if volume >= 1:
        return f"{volume:,.1f} BTC"
    return f"{volume:,.3f} BTC"


def save_wall_levels(target, prefix, levels):
    target[wall_field(prefix, "Sup_Wall")] = f"${levels['support_price']:,}"
    target[wall_field(prefix, "Sup_Vol")] = format_btc_volume(levels["support_volume"])
    target[wall_field(prefix, "Res_Wall")] = f"${levels['resistance_price']:,}"
    target[wall_field(prefix, "Res_Vol")] = format_btc_volume(levels["resistance_volume"])
    target[wall_field(prefix, "Wall_Status")] = levels["status"]
    target[wall_field(prefix, "BTC_Now")] = f"${levels['current_price']:,.0f}"


def clear_wall_levels(target, prefix):
    target[wall_field(prefix, "Sup_Wall")] = PLACEHOLDER
    target[wall_field(prefix, "Sup_Vol")] = PLACEHOLDER
    target[wall_field(prefix, "Res_Wall")] = PLACEHOLDER
    target[wall_field(prefix, "Res_Vol")] = PLACEHOLDER
    target[wall_field(prefix, "Wall_Status")] = PLACEHOLDER
    target[wall_field(prefix, "BTC_Now")] = PLACEHOLDER


def build_orderbook_signal(data):
    exchanges = [
        ("Kraken", ""),
        ("OKX", "OKX"),
        ("KuCoin", "KUCOIN"),
        ("Gate.io", "GATE"),
        ("Coinbase", "COINBASE"),
    ]
    snapshots = []
    for name, prefix in exchanges:
        snapshots.append(
            {
                "name": name,
                "status": data.get(wall_field(prefix, "Wall_Status"), PLACEHOLDER),
                "support": data.get(wall_field(prefix, "Sup_Wall"), PLACEHOLDER),
                "resistance": data.get(wall_field(prefix, "Res_Wall"), PLACEHOLDER),
            }
        )

    support_names = [item["name"] for item in snapshots if "Dest" in item["status"]]
    resistance_names = [item["name"] for item in snapshots if "Diren" in item["status"]]

    if len(support_names) >= 2 and len(support_names) > len(resistance_names):
        detail = " | ".join(
            f"{item['name']} {item['support']}"
            for item in snapshots
            if item["name"] in support_names and item["support"] != PLACEHOLDER
        )
        return {
            "title": "Ortak destek guclu",
            "detail": detail or "Coklu borsa destegi goruluyor.",
            "badge": "SUPPORT",
            "class": "signal-long",
        }

    if len(resistance_names) >= 2 and len(resistance_names) > len(support_names):
        detail = " | ".join(
            f"{item['name']} {item['resistance']}"
            for item in snapshots
            if item["name"] in resistance_names and item["resistance"] != PLACEHOLDER
        )
        return {
            "title": "Ortak direnc guclu",
            "detail": detail or "Coklu borsa direnci goruluyor.",
            "badge": "RESISTANCE",
            "class": "signal-short",
        }

    detail = " | ".join(
        f"{item['name']} {item['support']} / {item['resistance']}"
        for item in snapshots
        if item["support"] != PLACEHOLDER or item["resistance"] != PLACEHOLDER
    )
    return {
        "title": "Seviyeler karisik",
        "detail": detail or "Coklu borsa teyidi henuz yok.",
        "badge": "MIXED",
        "class": "signal-neutral",
    }
