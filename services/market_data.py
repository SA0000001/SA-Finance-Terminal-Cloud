import math
import re
import ssl
import string
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

import pandas as pd
import requests
import streamlit as st
import streamlit.runtime as st_runtime
import yfinance as yf

from domain.parsers import parse_number
from domain.signals import build_orderbook_signal, clear_wall_levels, extract_wall_levels, save_wall_levels
from services.health import HealthRecorder
from services.http_utils import FetchError, safe_fetch_json, safe_fetch_text

HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
ETF_FLOW_COLUMNS = ("IBIT", "FBTC", "BITB", "ARKB", "BTCO", "EZBC", "BRRR", "HODL", "BTCW", "MSBT", "GBTC", "BTC", "TOTAL")
ETF_FLOW_LAYOUTS = (
    ETF_FLOW_COLUMNS,
    tuple(symbol for symbol in ETF_FLOW_COLUMNS if symbol != "MSBT"),
)
ETF_PLACEHOLDERS = {"", "-", "—"}
PLACEHOLDER = "—"
TEXT_ACCEPT = "text/plain, text/markdown, */*"
DATA_PARSE_EXCEPTIONS = (KeyError, TypeError, ValueError, IndexError, ZeroDivisionError)
YFINANCE_EXCEPTIONS = (KeyError, TypeError, ValueError, IndexError, requests.RequestException)
FAST_TTL = 30
MARKET_TTL = 300
SENTIMENT_TTL = 1800
MACRO_TTL = 21600
ETF_FLOW_DATE_RE = re.compile(r"^\d{2}\s+[A-Za-z]{3}\s+\d{4}$")

# ── TradingView WebSocket veri çekici ─────────────────────────────────────────
# altin_signal_bot.py'den adapte edildi.
# Günlük OHLCV çeker; fiyat ve değişim hesabı için kullanılır.

# TW sembol eşleme tablosu: terminal_key → (tv_symbol, para_birimi_suffix)
TV_SYMBOL_MAP: dict[str, tuple[str, str]] = {
    # Emtia
    "OIL":    ("NYMEX:CL1!",  "$"),   # WTI Crude — sürekli kontrat
    "GOLD":   ("COMEX:GC1!",  "$"),   # Altın
    "SILVER": ("COMEX:SI1!",  "$"),   # Gümüş
    "NATGAS": ("NYMEX:NG1!",  "$"),   # Doğalgaz
    "COPPER": ("COMEX:HG1!",  "$"),   # Bakır
    # Endeksler
    "SP500":  ("SP:SPX",      ""),
    "NASDAQ": ("NASDAQ:NDX",  ""),
    "DAX":    ("XETR:DAX",    ""),
    "NIKKEI": ("INDEX:NKY",   ""),
    "HSI":    ("HSI:HSI",     ""),
    "SHCOMP": ("SSE:000001",  ""),
    "BIST100":("BIST:XU100",  ""),
    # FX & Faiz
    "DXY":    ("TVC:DXY",     ""),
    "US10Y":  ("TVC:US10Y",   "%"),
    "EURUSD": ("FX:EURUSD",   ""),
    "GBPUSD": ("FX:GBPUSD",   ""),
    "USDJPY": ("FX:USDJPY",   ""),
    "USDTRY": ("FX:USDTRY",   ""),
    "USDCHF": ("FX:USDCHF",   ""),
    "AUDUSD": ("FX:AUDUSD",   ""),
}


def _tv_rand(k: int = 12) -> str:
    import random
    return "".join(random.choices(string.ascii_lowercase, k=k))


def _tv_msg(func: str, args: list) -> str:
    body = json.dumps({"m": func, "p": args}, separators=(",", ":"))
    return f"~m~{len(body)}~m~{body}"


def _tv_fetch_daily_bars(tv_symbol: str, n_bars: int = 3) -> list[dict]:
    """
    TradingView WebSocket'ten günlük bar çeker.
    Döner: [{"t": timestamp, "o": open, "h": high, "l": low, "c": close}, ...]
    """
    try:
        import websocket as _websocket
    except ImportError:
        return []

    bars: list[dict] = []
    cs = f"cs_{_tv_rand()}"
    qs = f"qs_{_tv_rand()}"
    done = {"ok": False}

    def on_message(ws, raw):
        if re.match(r"~m~\d+~m~~h~\d+", raw):
            ws.send(raw)
            return
        for part in re.findall(r"~m~\d+~m~(.+?)(?=~m~\d+~m~|$)", raw, re.DOTALL):
            try:
                msg = json.loads(part)
            except Exception:
                continue
            m = msg.get("m", "")
            if m in ("timescale_update", "du"):
                try:
                    for it in msg["p"][1]["sds_1"]["s"]:
                        v = it["v"]
                        bars.append({"t": v[0], "o": v[1], "h": v[2], "l": v[3], "c": v[4]})
                except Exception:
                    pass
            elif m == "series_completed":
                done["ok"] = True
                ws.close()

    def on_open(ws):
        ws.send(_tv_msg("set_auth_token",       ["unauthorized_user_token"]))
        ws.send(_tv_msg("chart_create_session", [cs, ""]))
        ws.send(_tv_msg("quote_create_session", [qs]))
        ws.send(_tv_msg("quote_add_symbols",    [qs, tv_symbol, {"flags": ["force_permission"]}]))
        ws.send(_tv_msg("resolve_symbol",       [cs, "sds_sym_1",
            f'={{"symbol":"{tv_symbol}","adjustment":"splits"}}']))
        ws.send(_tv_msg("create_series",        [cs, "sds_1", "s1", "sds_sym_1", "1D", n_bars]))

    try:
        _websocket.WebSocketApp(
            "wss://data.tradingview.com/socket.io/websocket?from=chart%2F&date=&type=chart",
            header={"Origin": "https://www.tradingview.com", "User-Agent": "Mozilla/5.0"},
            on_open=on_open,
            on_message=on_message,
            on_error=lambda ws, e: None,
            on_close=lambda ws, *a: None,
        ).run_forever(sslopt={"cert_reqs": ssl.CERT_NONE})
    except Exception:
        pass

    return bars


def _tv_quote(tv_symbol: str) -> dict | None:
    """
    TW'den son 2 günlük bar çeker, fiyat ve günlük değişim hesaplar.
    Döner: {"price": float, "change_pct": float} veya None
    """
    bars = _tv_fetch_daily_bars(tv_symbol, n_bars=3)
    if len(bars) < 2:
        return None
    bars_sorted = sorted(bars, key=lambda b: b["t"])
    last = bars_sorted[-1]
    prev = bars_sorted[-2]
    price = last["c"]
    prev_close = prev["c"]
    if not price or not prev_close or prev_close == 0:
        return None
    return {
        "price":      price,
        "change_pct": (price - prev_close) / prev_close * 100,
    }


def _load_tv_group(
    target: dict,
    recorder: HealthRecorder,
    source: str,
    keys: list[str],
    value_template: str,
) -> None:
    """
    TV_SYMBOL_MAP'teki sembolleri TradingView'den çeker.
    target'a {KEY: fiyat, KEY_C: değişim%} yazar.
    """
    started_at = time.perf_counter()
    successes = 0
    failures = []

    def fetch_one(key: str):
        entry = TV_SYMBOL_MAP.get(key)
        if not entry:
            raise ValueError(f"{key} TV_SYMBOL_MAP'te yok")
        tv_sym, _ = entry
        result = _tv_quote(tv_sym)
        if result is None:
            raise ValueError(f"{tv_sym} için veri alınamadı")
        return {
            key:          value_template.format(value=result["price"]),
            f"{key}_C":   f"{result['change_pct']:.2f}%",
        }

    with ThreadPoolExecutor(max_workers=min(4, len(keys))) as executor:
        future_map = {executor.submit(fetch_one, k): k for k in keys}
        for future in as_completed(future_map):
            key = future_map[future]
            try:
                target.update(future.result())
                successes += 1
            except Exception as exc:
                failures.append(f"{key}: {exc}")
                _set_defaults(target, {key: PLACEHOLDER, f"{key}_C": PLACEHOLDER})

    latency = _latency_ms(started_at)
    if successes:
        recorder.success(source, latency)
    else:
        recorder.failure(source, "; ".join(failures) or "No TV data", latency)




def _cache_data_headless_safe(*cache_args, **cache_kwargs):
    def decorator(func):
        if getattr(st_runtime, "exists", lambda: False)():
            return st.cache_data(*cache_args, **cache_kwargs)(func)
        return func

    return decorator


def _latency_ms(started_at: float) -> float:
    return (time.perf_counter() - started_at) * 1000


def _error_message(prefix: str, exc: Exception) -> str:
    return f"{prefix}: {exc}"


def _merge_health_maps(*maps: dict[str, dict] | None) -> dict[str, dict]:
    merged = {}
    for health_map in maps:
        if health_map:
            merged.update(health_map)
    return merged


def _merge_result_payloads(*payloads: dict | None) -> dict:
    merged = {}
    merged_health = {}
    for payload in payloads:
        if not payload or isinstance(payload, Exception):
            continue
        payload_data = dict(payload)
        payload_health = payload_data.pop("_health", {})
        merged.update(payload_data)
        merged_health = _merge_health_maps(merged_health, payload_health)
    if merged_health:
        merged["_health"] = merged_health
    return merged


def _task_failure_payload(task_name: str, exc: Exception) -> dict:
    recorder = HealthRecorder()
    source_map = {
        "base": "Base Market Pipeline",
        "derivatives": "Derivatives Pipeline",
        "market_cap": "Market Cap Pipeline",
    }
    recorder.failure(source_map.get(task_name, task_name), _error_message("Task error", exc))
    return {"_health": recorder.export()}


def _run_parallel_tasks(task_map: dict[str, object], *, max_workers: int = 4) -> dict[str, object]:
    if not task_map:
        return {}

    results = {}
    with ThreadPoolExecutor(max_workers=min(max_workers, len(task_map))) as executor:
        future_map = {executor.submit(task): name for name, task in task_map.items()}
        for future in as_completed(future_map):
            name = future_map[future]
            try:
                results[name] = future.result()
            except Exception as exc:
                results[name] = exc
    return results


def _record_fetch_error(
    recorder: HealthRecorder, source: str, exc: FetchError, *, stale_after_seconds: int | None = None
):
    recorder.failure(source, str(exc), exc.latency_ms, stale_after_seconds=stale_after_seconds)


def _record_parse_error(
    recorder: HealthRecorder,
    source: str,
    exc: Exception,
    *,
    latency_ms: float | None = None,
    stale_after_seconds: int | None = None,
):
    recorder.failure(source, _error_message("Parse error", exc), latency_ms, stale_after_seconds=stale_after_seconds)


def _history_with_latency(symbol: str, *, period: str):
    started_at = time.perf_counter()
    # auto_adjust=True: split/dividend düzeltmesi — vadeli işlemler için gerekli
    # back_adjust=False: geriye dönük fiyat bozulması önlenir (güncel fiyat doğru kalır)
    history = yf.Ticker(symbol).history(period=period, auto_adjust=True, back_adjust=False)
    return history, _latency_ms(started_at)


# Vadeli işlem rollover'ında günlük değişim bozulmasın diye intraday (1d/1m) kullan
_FUTURES_INTRADAY_CHANGE = {"CL=F", "GC=F", "SI=F", "NG=F", "HG=F", "ZW=F", "BZ=F"}


def _fetch_futures_daily_change(symbol: str) -> float | None:
    """
    Vadeli işlem sembolü için günlük değişim yüzdesini intraday veriden hesaplar.
    Rollover günlerinde eski-yeni kontrat fiyat farkından kaynaklanan
    yanlış değişim hesabını önler.
    """
    try:
        ticker = yf.Ticker(symbol)
        # 1 günlük 1 dakikalık bar — open ve son fiyat
        hist_1m = ticker.history(period="1d", interval="1m", auto_adjust=True)
        if hist_1m.empty or len(hist_1m) < 2:
            return None
        open_price = float(hist_1m["Open"].iloc[0])
        last_price = float(hist_1m["Close"].iloc[-1])
        if open_price <= 0:
            return None
        return (last_price - open_price) / open_price * 100
    except Exception:
        return None


def _download_with_latency(symbols, *, period: str):
    started_at = time.perf_counter()
    data = yf.download(symbols, period=period, progress=False)
    return data, _latency_ms(started_at)


def _set_defaults(target: dict, defaults: dict):
    target.update(defaults)


def _fetch_cnn_fng() -> int | None:
    """
    CNN Fear & Greed Index'i doğrudan CNN API'sinden çeker.
    Başarılı olursa 0-100 arası integer döner, başarısız olursa None.
    """
    try:
        resp = requests.get(
            "https://production.dataviz.cnn.io/index/fearandgreed/graphdata",
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": "https://edition.cnn.com/markets/fear-and-greed",
                "Accept": "application/json",
            },
            timeout=8,
        )
        if resp.status_code == 200:
            data = resp.json()
            score = data.get("fear_and_greed", {}).get("score")
            if score is not None:
                return int(round(float(score)))
    except Exception:
        pass
    return None


def _compute_stock_fng() -> dict:
    """
    Stock Market Fear & Greed — CNN API öncelikli, yfinance fallback.

    CNN API çalışırsa doğrudan resmi skoru kullanır.
    Çalışmazsa CNN metodolojisine yakın 7 bileşenli yfinance hesabı:
      1. Market Momentum     (%14.3) — SPX vs 125d MA
      2. Stock Strength      (%14.3) — 52-week high/low oranı (RSP proxy)
      3. Stock Breadth       (%14.3) — RSP/SPY equal-weight spread
      4. Put/Call Ratio      (%14.3) — VIX/VXST oranı (short-term fear proxy)
      5. Market Volatility   (%14.3) — VIX seviyesi
      6. Safe Haven Demand   (%14.3) — TLT vs SPY relatif perf
      7. Junk Bond Demand    (%14.3) — HYG vs LQD spread (yield proxy)
    """
    import numpy as np

    def _label(s: int) -> str:
        if s >= 75: return "Extreme Greed"
        if s >= 56: return "Greed"
        if s >= 45: return "Neutral"
        if s >= 25: return "Fear"
        return "Extreme Fear"

    # --- 1. CNN API dene ---
    cnn_score = _fetch_cnn_fng()
    if cnn_score is not None:
        return {
            "STOCK_FNG_NUM":   cnn_score,
            "STOCK_FNG":       f"{cnn_score} ({_label(cnn_score)})",
            "STOCK_FNG_LABEL": _label(cnn_score),
            "STOCK_FNG_VIX":   0,
            "STOCK_FNG_MOM":   0,
            "STOCK_FNG_BRD":   0,
            "STOCK_FNG_SOURCE": "CNN",
        }

    # --- 2. yfinance fallback — CNN metodolojisine yakın hesap ---
    try:
        tickers = yf.download(
            ["^VIX", "^GSPC", "SPY", "RSP", "TLT", "HYG", "LQD"],
            period="130d", interval="1d", progress=False, auto_adjust=True,
        )
        close = tickers["Close"]

        # 1. Market Momentum — SPX vs 125d MA
        spx = close["^GSPC"].dropna()
        ma125 = float(spx.rolling(125).mean().iloc[-1])
        spx_now = float(spx.iloc[-1])
        spread_pct = (spx_now - ma125) / ma125 * 100  # -10%→0, 0%→50, +10%→100
        momentum_score = max(0, min(100, int(50 + spread_pct * 5)))

        # 2. Stock Price Strength — RSP 52-week high/low proximity proxy
        rsp = close["RSP"].dropna()
        rsp_now = float(rsp.iloc[-1])
        rsp_52h = float(rsp.iloc[-min(252, len(rsp)):].max())
        rsp_52l = float(rsp.iloc[-min(252, len(rsp)):].min())
        if rsp_52h > rsp_52l:
            strength_score = max(0, min(100, int((rsp_now - rsp_52l) / (rsp_52h - rsp_52l) * 100)))
        else:
            strength_score = 50

        # 3. Stock Price Breadth — RSP vs SPY 20g relatif performans
        spy = close["SPY"].dropna()
        rsp_ret = float(rsp.iloc[-1] / rsp.iloc[-20] - 1) * 100
        spy_ret = float(spy.iloc[-1] / spy.iloc[-20] - 1) * 100
        breadth_spread = rsp_ret - spy_ret
        breadth_score = max(0, min(100, int(50 + breadth_spread * 10)))

        # 4. Put/Call Ratio proxy — VIX seviyesi kısa vadeli (CNN: CBOE P/C ratio)
        #    VIX yüksekse korku → düşük skor; VIX düşükse açgözlülük → yüksek skor
        vix = close["^VIX"].dropna()
        vix_now = float(vix.iloc[-1])
        vix_ma20 = float(vix.rolling(20).mean().iloc[-1])
        # VIX'in kendi 20g ortalamasına göre relatif konumu
        vix_ratio = vix_now / vix_ma20 if vix_ma20 > 0 else 1.0
        pcr_score = max(0, min(100, int(100 - (vix_ratio - 0.5) / (2.0 - 0.5) * 100)))

        # 5. Market Volatility — VIX seviyesi (12→100, 20→50, 40→0)
        vix_score = max(0, min(100, int(100 - (vix_now - 12) / (40 - 12) * 100)))

        # 6. Safe Haven Demand — TLT vs SPY 20g relatif (uzun vadeli)
        tlt = close["TLT"].dropna()
        tlt_ret = float(tlt.iloc[-1] / tlt.iloc[-20] - 1) * 100
        spy_ret20 = float(spy.iloc[-1] / spy.iloc[-20] - 1) * 100
        safe_spread = tlt_ret - spy_ret20  # TLT outperform → fear
        safe_score = max(0, min(100, int(50 - safe_spread * 6)))

        # 7. Junk Bond Demand — HYG vs LQD spread (CNN: high-yield vs investment grade)
        hyg = close["HYG"].dropna()
        lqd = close["LQD"].dropna()
        hyg_ret = float(hyg.iloc[-1] / hyg.iloc[-20] - 1) * 100
        lqd_ret = float(lqd.iloc[-1] / lqd.iloc[-20] - 1) * 100
        junk_spread = hyg_ret - lqd_ret  # HYG outperform → greed
        junk_score = max(0, min(100, int(50 + junk_spread * 8)))

        # Composite — 7 eşit ağırlık (CNN metodolojisi)
        weight = 1 / 7
        composite = int(round(
            momentum_score * weight +
            strength_score * weight +
            breadth_score  * weight +
            pcr_score      * weight +
            vix_score      * weight +
            safe_score     * weight +
            junk_score     * weight
        ))

        return {
            "STOCK_FNG_NUM":    composite,
            "STOCK_FNG":        f"{composite} ({_label(composite)})",
            "STOCK_FNG_LABEL":  _label(composite),
            "STOCK_FNG_VIX":    vix_score,
            "STOCK_FNG_MOM":    momentum_score,
            "STOCK_FNG_BRD":    breadth_score,
            "STOCK_FNG_SOURCE": "yfinance",
        }
    except Exception:
        return {
            "STOCK_FNG_NUM":    0,
            "STOCK_FNG":        PLACEHOLDER,
            "STOCK_FNG_LABEL":  PLACEHOLDER,
            "STOCK_FNG_VIX":    0,
            "STOCK_FNG_MOM":    0,
            "STOCK_FNG_BRD":    0,
            "STOCK_FNG_SOURCE": "error",
        }


def _parse_calendar_timestamp(date_text: str, time_text: str):
    for candidate in (f"{date_text} {time_text}".strip(), str(date_text).strip()):
        if not candidate:
            continue
        parsed = pd.to_datetime(candidate, errors="coerce")
        if pd.notna(parsed):
            return parsed
    return None


def _normalize_calendar_events(events, now=None):
    if not isinstance(events, list):
        return []

    now = now or pd.Timestamp.now(tz="Europe/Istanbul")
    today = now.date()
    horizon = (now + pd.Timedelta(hours=36)).date()
    normalized = []

    for item in events:
        if not isinstance(item, dict):
            continue

        impact = str(item.get("impact", "")).strip()
        if "high" not in impact.lower():
            continue

        title = str(item.get("title", "")).strip()
        country = str(item.get("country", "")).strip()
        date_text = str(item.get("date", "")).strip()
        time_text = str(item.get("time", "")).strip()
        parsed = _parse_calendar_timestamp(date_text, time_text)
        if parsed is None:
            continue

        if today <= parsed.date() <= horizon:
            normalized.append(
                {
                    "title": title or PLACEHOLDER,
                    "country": country or PLACEHOLDER,
                    "impact": impact or "High",
                    "date": date_text or PLACEHOLDER,
                    "time": time_text or PLACEHOLDER,
                    "actual": str(item.get("actual", "")).strip() or PLACEHOLDER,
                    "forecast": str(item.get("forecast", "")).strip() or PLACEHOLDER,
                    "previous": str(item.get("previous", "")).strip() or PLACEHOLDER,
                    "_sort": parsed,
                }
            )

    normalized.sort(key=lambda item: item["_sort"])
    return [{key: value for key, value in event.items() if key != "_sort"} for event in normalized[:5]]


def format_flow_millions(value):
    number = parse_number(value)
    if number is None:
        return PLACEHOLDER
    sign = "+" if number > 0 else ""
    return f"{sign}{number:.1f}M $"


def build_etf_flow_df(data):
    return pd.DataFrame(
        [
            {
                "ETF": "Total" if symbol == "TOTAL" else symbol,
                "Netflow (US$m)": data.get(f"ETF_FLOW_{symbol}", PLACEHOLDER),
            }
            for symbol in ETF_FLOW_COLUMNS
        ]
    )


def _clean_etf_flow_cell(value):
    text = str(value or "").replace("\xa0", " ").strip()
    return re.sub(r"\s+", " ", text)


def _resolve_etf_flow_values(raw_values):
    cleaned = [_clean_etf_flow_cell(value) for value in raw_values]
    for layout in ETF_FLOW_LAYOUTS:
        if len(cleaned) != len(layout):
            continue

        resolved = {symbol: PLACEHOLDER for symbol in ETF_FLOW_COLUMNS}
        for symbol, raw_value in zip(layout, cleaned):
            resolved[symbol] = raw_value or PLACEHOLDER
        return [resolved[symbol] for symbol in ETF_FLOW_COLUMNS]

    return None


def _has_populated_etf_values(values):
    return sum(value not in ETF_PLACEHOLDERS for value in values[:-1]) > 0


def _parse_latest_etf_flow_pipe_row(flow_text):
    flow_rows = [
        line.strip()
        for line in flow_text.splitlines()
        if re.match(r"^\|\s*\d{2}\s+[A-Za-z]{3}\s+\d{4}\s*\|", line.strip())
    ]
    if not flow_rows:
        return None

    for row in reversed(flow_rows):
        parts = [_clean_etf_flow_cell(part) for part in row.split("|")[1:-1]]
        if len(parts) < 2:
            continue

        date_text = parts[0]
        values = _resolve_etf_flow_values(parts[1:])
        if not values or not _has_populated_etf_values(values):
            continue

        return date_text, values

    return None


def _parse_latest_etf_flow_flat_row(flow_text):
    lines = [_clean_etf_flow_cell(line) for line in flow_text.splitlines()]
    lines = [line for line in lines if line]
    if not lines:
        return None

    stop_markers = {"Total", "Average", "Maximum", "Minimum"}
    parsed_rows = []
    for index, line in enumerate(lines):
        if not ETF_FLOW_DATE_RE.match(line):
            continue

        next_index = len(lines)
        for probe in range(index + 1, len(lines)):
            candidate = lines[probe]
            if ETF_FLOW_DATE_RE.match(candidate) or candidate in stop_markers or candidate.startswith("Source:"):
                next_index = probe
                break

        values = _resolve_etf_flow_values(lines[index + 1 : next_index])
        if not values or not _has_populated_etf_values(values):
            continue

        parsed_rows.append((line, values))

    return parsed_rows[-1] if parsed_rows else None


def parse_latest_etf_flow_row(flow_text):
    return _parse_latest_etf_flow_pipe_row(flow_text) or _parse_latest_etf_flow_flat_row(flow_text)


def format_market_cap_short(value):
    if value is None:
        return PLACEHOLDER
    if value >= 1e12:
        return f"${value/1e12:.2f}T"
    if value >= 1e9:
        return f"${value/1e9:.1f}B"
    if value >= 1e6:
        return f"${value/1e6:.1f}M"
    return f"${value:,.0f}"


def parse_tradingview_market_cap(text):
    match = re.search(r"Market open\s+([0-9]+(?:\.[0-9]+)?)\s*([TBM])\s*R USD", text)
    if not match:
        match = re.search(r"Market closed\s+([0-9]+(?:\.[0-9]+)?)\s*([TBM])\s*R USD", text)
    if not match:
        raise ValueError("tradingview market cap not found")

    value = float(match.group(1))
    unit = match.group(2)
    multiplier = {"T": 1e12, "B": 1e9, "M": 1e6}[unit]
    return value * multiplier


def parse_tradingview_dominance(text):
    """TradingView CRYPTOCAP:BTC.D / ETH.D sayfasından dominance yüzdesini parse eder.
    Örnek: 'Market open 57.27% R' → 57.27
    """
    match = re.search(r"Market open\s+([0-9]+(?:\.[0-9]+)?)%\s*R", text)
    if not match:
        match = re.search(r"Market closed\s+([0-9]+(?:\.[0-9]+)?)%\s*R", text)
    if not match:
        # Alternatif format: "57.27% R USD"
        match = re.search(r"([0-9]+(?:\.[0-9]+)?)%\s*R\s*USD", text)
    if not match:
        raise ValueError("tradingview dominance not found")
    return float(match.group(1))


def _load_yfinance_etfs(target: dict, recorder: HealthRecorder):
    source = "yFinance ETFs"
    started_at = time.perf_counter()
    failures = []

    def fetch_symbol(sym: str):
        history, _ = _history_with_latency(sym, period="10d")
        if history.empty or len(history.index) < 2:
            raise ValueError(f"{sym} history is empty")

        curr = float(history["Close"].iloc[-1])
        prev = float(history["Close"].iloc[-2])
        return {
            f"{sym}_P": f"${curr:.2f}",
            f"{sym}_C": f"{(curr - prev) / prev * 100:.2f}%",
            f"{sym}_Vol": f"{int(history['Volume'].iloc[-1]):,}",
        }

    symbol_map = {sym: (lambda symbol=sym: fetch_symbol(symbol)) for sym in ["IBIT", "FBTC", "BITB", "ARKB"]}
    successes = 0
    with ThreadPoolExecutor(max_workers=min(4, len(symbol_map))) as executor:
        future_map = {executor.submit(task): sym for sym, task in symbol_map.items()}
        for future in as_completed(future_map):
            sym = future_map[future]
            try:
                target.update(future.result())
                successes += 1
            except YFINANCE_EXCEPTIONS as exc:
                failures.append(f"{sym}: {exc}")
                _set_defaults(
                    target,
                    {
                        f"{sym}_P": PLACEHOLDER,
                        f"{sym}_C": PLACEHOLDER,
                        f"{sym}_Vol": PLACEHOLDER,
                    },
                )

    latency = _latency_ms(started_at)
    if successes:
        recorder.success(source, latency)
    else:
        recorder.failure(source, "; ".join(failures) or "No ETF data", latency)


def _symbol_candidates(symbol):
    """Tek ticker veya (primary, fallback, ...) tuple — her ikisini de destekler."""
    if isinstance(symbol, (list, tuple)):
        return tuple(symbol)
    return (symbol,)


def _load_yfinance_change_group(
    target: dict, recorder: HealthRecorder, source: str, symbols: dict[str, object], *, period: str, value_template: str
):
    started_at = time.perf_counter()
    failures = []

    def fetch_symbol(key: str, sym):
        errors = []
        for candidate in _symbol_candidates(sym):
            try:
                history, _ = _history_with_latency(candidate, period=period)
                if history.empty or "Close" not in history:
                    raise ValueError(f"{candidate} history is empty")

                closes = history["Close"].dropna()
                if len(closes.index) < 2:
                    raise ValueError(f"{candidate} close history has fewer than 2 valid points")

                curr = float(closes.iloc[-1])
                prev = float(closes.iloc[-2])
                if not math.isfinite(curr) or not math.isfinite(prev) or prev == 0:
                    raise ValueError(f"{candidate} close history has invalid values")

                # Vadeli işlemler için rollover günü fiyat farkını önle:
                # intraday open→close değişimini kullan
                if candidate in _FUTURES_INTRADAY_CHANGE:
                    intraday_chg = _fetch_futures_daily_change(candidate)
                    pct = intraday_chg if intraday_chg is not None else (curr - prev) / prev * 100
                else:
                    pct = (curr - prev) / prev * 100

                return {
                    key: value_template.format(value=curr),
                    f"{key}_C": f"{pct:.2f}%",
                }
            except YFINANCE_EXCEPTIONS as exc:
                errors.append(f"{candidate}: {exc}")
        raise ValueError("; ".join(errors) or f"{key} history is invalid")

    successes = 0
    with ThreadPoolExecutor(max_workers=min(6, len(symbols))) as executor:
        future_map = {
            executor.submit(lambda key=key, sym=sym: fetch_symbol(key, sym)): key for key, sym in symbols.items()
        }
        for future in as_completed(future_map):
            key = future_map[future]
            try:
                target.update(future.result())
                successes += 1
            except YFINANCE_EXCEPTIONS as exc:
                failures.append(f"{key}: {exc}")
                _set_defaults(
                    target,
                    {
                        key: PLACEHOLDER,
                        f"{key}_C": PLACEHOLDER,
                    },
                )

    latency = _latency_ms(started_at)
    if successes:
        recorder.success(source, latency)
    else:
        recorder.failure(source, "; ".join(failures) or "No market data", latency)


def _load_orderbook_source(
    target: dict, recorder: HealthRecorder, *, source: str, prefix: str, url: str, bid_getter, ask_getter
):
    response = None
    try:
        response = safe_fetch_json(source, url, timeout=8, headers=HEADERS)
        bids = [(float(price), float(qty)) for price, qty, *_ in bid_getter(response.payload)]
        asks = [(float(price), float(qty)) for price, qty, *_ in ask_getter(response.payload)]
        save_wall_levels(target, prefix, extract_wall_levels(bids, asks))
        recorder.success(source, response.latency_ms, stale_after_seconds=300)
    except FetchError as exc:
        _record_fetch_error(recorder, source, exc, stale_after_seconds=300)
        clear_wall_levels(target, prefix)
    except DATA_PARSE_EXCEPTIONS as exc:
        _record_parse_error(
            recorder,
            source,
            exc,
            latency_ms=response.latency_ms if response else None,
            stale_after_seconds=300,
        )
        clear_wall_levels(target, prefix)


def _load_fred_series(*, series_id: str, api_key: str, limit: int, source: str):
    url = (
        "https://api.stlouisfed.org/fred/series/observations"
        f"?series_id={series_id}&api_key={api_key}&file_type=json&sort_order=desc&limit={limit}"
    )
    return safe_fetch_json(source, url, timeout=6)


@_cache_data_headless_safe(ttl=FAST_TTL)
def fetch_live_usdt_d():
    health = HealthRecorder()
    result = {"USDT_D": PLACEHOLDER, "USDT_D_SOURCE": PLACEHOLDER}

    tradingview_response = None
    try:
        tradingview_response = safe_fetch_text(
            "TradingView USDT.D",
            "https://r.jina.ai/http://www.tradingview.com/symbols/USDT.D/?exchange=CRYPTOCAP",
            timeout=20,
            headers=HEADERS,
            accept=TEXT_ACCEPT,
        )
        match = re.search(r"Market open\s+([0-9]+(?:\.[0-9]+)?)%R", tradingview_response.payload)
        if not match:
            match = re.search(r"USDT\.D Market open\s+([0-9]+(?:\.[0-9]+)?)\sR%", tradingview_response.payload)
        if not match:
            match = re.search(r"Market closed\s+([0-9]+(?:\.[0-9]+)?)%R", tradingview_response.payload)
        if not match:
            raise ValueError("tradingview usdt.d not found")

        result = {
            "USDT_D": f"%{float(match.group(1)):.2f}",
            "USDT_D_SOURCE": "TradingView",
        }
        health.success("TradingView USDT.D", tradingview_response.latency_ms, stale_after_seconds=300)
    except FetchError as exc:
        _record_fetch_error(health, "TradingView USDT.D", exc, stale_after_seconds=300)
    except (TypeError, ValueError) as exc:
        _record_parse_error(
            health,
            "TradingView USDT.D",
            exc,
            latency_ms=tradingview_response.latency_ms if tradingview_response else None,
            stale_after_seconds=300,
        )

    if result["USDT_D"] != PLACEHOLDER:
        result["_health"] = health.export()
        return result

    coingecko_response = None
    try:
        coingecko_response = safe_fetch_json(
            "CoinGecko Global",
            "https://api.coingecko.com/api/v3/global",
            timeout=6,
            headers=HEADERS,
        )
        payload = coingecko_response.payload["data"]
        result = {
            "USDT_D": f"%{payload['market_cap_percentage']['usdt']:.2f}",
            "USDT_D_SOURCE": "CoinGecko",
        }
        health.success("CoinGecko Global", coingecko_response.latency_ms)
    except FetchError as exc:
        _record_fetch_error(health, "CoinGecko Global", exc)
    except DATA_PARSE_EXCEPTIONS as exc:
        _record_parse_error(
            health,
            "CoinGecko Global",
            exc,
            latency_ms=coingecko_response.latency_ms if coingecko_response else None,
        )

    if result["USDT_D"] != PLACEHOLDER:
        result["_health"] = health.export()
        return result

    global_response = None
    ticker_response = None
    try:
        coinpaprika_results = _run_parallel_tasks(
            {
                "global": lambda: safe_fetch_json(
                    "Coinpaprika Global",
                    "https://api.coinpaprika.com/v1/global",
                    timeout=6,
                    headers=HEADERS,
                ),
                "usdt": lambda: safe_fetch_json(
                    "Coinpaprika USDT",
                    "https://api.coinpaprika.com/v1/tickers/usdt-tether",
                    timeout=6,
                    headers=HEADERS,
                ),
            },
            max_workers=2,
        )
        global_response = coinpaprika_results["global"]
        ticker_response = coinpaprika_results["usdt"]
        if isinstance(global_response, Exception):
            raise global_response
        if isinstance(ticker_response, Exception):
            raise ticker_response
        total_market_cap = float(global_response.payload["market_cap_usd"])
        usdt_market_cap = float(ticker_response.payload["quotes"]["USD"]["market_cap"])
        result = {
            "USDT_D": f"%{usdt_market_cap / total_market_cap * 100:.2f}",
            "USDT_D_SOURCE": "Coinpaprika",
        }
        health.success("Coinpaprika Global", global_response.latency_ms)
        health.success("Coinpaprika USDT", ticker_response.latency_ms)
    except FetchError as exc:
        _record_fetch_error(health, exc.source, exc)
    except DATA_PARSE_EXCEPTIONS as exc:
        latency = (
            ticker_response.latency_ms if ticker_response else global_response.latency_ms if global_response else None
        )
        _record_parse_error(health, "Coinpaprika USDT", exc, latency_ms=latency)

    result["_health"] = health.export()
    return result


@_cache_data_headless_safe(ttl=FAST_TTL)
def fetch_live_market_cap_segments():
    health = HealthRecorder()
    # Market cap sembolleri (parse_tradingview_market_cap kullanır)
    cap_symbols = {
        "TOTAL": "https://r.jina.ai/http://www.tradingview.com/symbols/TOTAL/",
        "TOTAL2": "https://r.jina.ai/http://www.tradingview.com/symbols/TOTAL2/",
        "TOTAL3": "https://r.jina.ai/http://www.tradingview.com/symbols/TOTAL3/",
        "OTHERS": "https://r.jina.ai/http://www.tradingview.com/symbols/OTHERS/?exchange=CRYPTOCAP",
    }
    # Dominance sembolleri (parse_tradingview_dominance kullanır)
    dom_symbols = {
        "BTC_D": "https://r.jina.ai/http://www.tradingview.com/symbols/BTC.D/?exchange=CRYPTOCAP",
        "ETH_D": "https://r.jina.ai/http://www.tradingview.com/symbols/ETH.D/?exchange=CRYPTOCAP",
    }
    result = {
        "TOTAL_CAP": PLACEHOLDER,
        "TOTAL2_CAP": PLACEHOLDER,
        "TOTAL3_CAP": PLACEHOLDER,
        "OTHERS_CAP": PLACEHOLDER,
        "TOTAL_CAP_NUM": None,
        "TOTAL2_CAP_NUM": None,
        "TOTAL3_CAP_NUM": None,
        "OTHERS_CAP_NUM": None,
        "TOTAL_CAP_SOURCE": PLACEHOLDER,
        # FIX 1: TradingView'dan doğrudan dominance değerleri
        "BTC_DOM_TV": PLACEHOLDER,
        "ETH_DOM_TV": PLACEHOLDER,
        "DOM_SOURCE": PLACEHOLDER,
    }

    tradingview_started_at = time.perf_counter()
    tradingview_parsed = {}
    dom_parsed = {}
    tradingview_failures = []

    all_fetches = {
        **{k: (k, "cap", url) for k, url in cap_symbols.items()},
        **{k: (k, "dom", url) for k, url in dom_symbols.items()},
    }

    with ThreadPoolExecutor(max_workers=min(6, len(all_fetches))) as executor:
        future_map = {
            executor.submit(
                lambda key=key, url=url: (
                    key,
                    safe_fetch_text("TradingView Market Cap", url, timeout=20, headers=HEADERS, accept=TEXT_ACCEPT),
                )
            ): (key, ftype)
            for key, (_, ftype, url) in all_fetches.items()
        }
        for future in as_completed(future_map):
            key, ftype = future_map[future]
            try:
                _, response = future.result()
                if ftype == "cap":
                    tradingview_parsed[key] = parse_tradingview_market_cap(response.payload)
                else:
                    dom_parsed[key] = parse_tradingview_dominance(response.payload)
            except FetchError as exc:
                tradingview_failures.append(str(exc))
            except (TypeError, ValueError) as exc:
                tradingview_failures.append(_error_message("Parse error", exc))

    # Dominance değerlerini kaydet (cap başarısız olsa bile)
    if "BTC_D" in dom_parsed:
        result["BTC_DOM_TV"] = f"%{dom_parsed['BTC_D']:.2f}"
        result["DOM_SOURCE"] = "TradingView"
    if "ETH_D" in dom_parsed:
        result["ETH_DOM_TV"] = f"%{dom_parsed['ETH_D']:.2f}"

    if len(tradingview_parsed) == len(cap_symbols):
        latency = _latency_ms(tradingview_started_at)
        result.update({
            "TOTAL_CAP": format_market_cap_short(tradingview_parsed["TOTAL"]),
            "TOTAL2_CAP": format_market_cap_short(tradingview_parsed["TOTAL2"]),
            "TOTAL3_CAP": format_market_cap_short(tradingview_parsed["TOTAL3"]),
            "OTHERS_CAP": format_market_cap_short(tradingview_parsed["OTHERS"]),
            "TOTAL_CAP_NUM": tradingview_parsed["TOTAL"],
            "TOTAL2_CAP_NUM": tradingview_parsed["TOTAL2"],
            "TOTAL3_CAP_NUM": tradingview_parsed["TOTAL3"],
            "OTHERS_CAP_NUM": tradingview_parsed["OTHERS"],
            "TOTAL_CAP_SOURCE": "TradingView",
        })
        health.success("TradingView Market Cap", latency, stale_after_seconds=300)
        result["_health"] = health.export()
        return result

    health.failure(
        "TradingView Market Cap",
        "; ".join(tradingview_failures) or "TradingView market cap fetch failed",
        _latency_ms(tradingview_started_at),
        stale_after_seconds=300,
    )

    global_response = None
    top10_response = None
    try:
        coingecko_results = _run_parallel_tasks(
            {
                "global": lambda: safe_fetch_json(
                    "CoinGecko Global",
                    "https://api.coingecko.com/api/v3/global",
                    timeout=6,
                    headers=HEADERS,
                ),
                "top10": lambda: safe_fetch_json(
                    "CoinGecko Top10",
                    "https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&order=market_cap_desc&per_page=10&page=1&sparkline=false",
                    timeout=8,
                    headers=HEADERS,
                ),
            },
            max_workers=2,
        )
        global_response = coingecko_results["global"]
        top10_response = coingecko_results["top10"]
        if isinstance(global_response, Exception):
            raise global_response
        if isinstance(top10_response, Exception):
            raise top10_response
        global_data = global_response.payload["data"]
        total_cap_num = float(global_data["total_market_cap"]["usd"])
        btc_d = float(global_data["market_cap_percentage"].get("btc", 0))
        eth_d = float(global_data["market_cap_percentage"].get("eth", 0))
        top10_sum = sum((item.get("market_cap") or 0) for item in top10_response.payload)
        total2_num = total_cap_num * (1 - btc_d / 100)
        total3_num = total_cap_num * (1 - (btc_d + eth_d) / 100)
        others_num = max(total_cap_num - top10_sum, 0)

        result = {
            "TOTAL_CAP": format_market_cap_short(total_cap_num),
            "TOTAL2_CAP": format_market_cap_short(total2_num),
            "TOTAL3_CAP": format_market_cap_short(total3_num),
            "OTHERS_CAP": format_market_cap_short(others_num),
            "TOTAL_CAP_NUM": total_cap_num,
            "TOTAL2_CAP_NUM": total2_num,
            "TOTAL3_CAP_NUM": total3_num,
            "OTHERS_CAP_NUM": others_num,
            "TOTAL_CAP_SOURCE": "CoinGecko fallback",
        }
        health.success("CoinGecko Global", global_response.latency_ms)
        health.success("CoinGecko Top10", top10_response.latency_ms)
    except FetchError as exc:
        _record_fetch_error(health, exc.source, exc)
    except DATA_PARSE_EXCEPTIONS as exc:
        latency = (
            top10_response.latency_ms if top10_response else global_response.latency_ms if global_response else None
        )
        _record_parse_error(health, "CoinGecko Top10", exc, latency_ms=latency)

    result["_health"] = health.export()
    return result


@_cache_data_headless_safe(ttl=180)
def _legacy_veri_motoru(fred_api_key=""):
    data = {}
    health = HealthRecorder()

    btc_response = None
    try:
        btc_response = safe_fetch_json(
            "Coinpaprika BTC",
            "https://api.coinpaprika.com/v1/tickers/btc-bitcoin",
            timeout=8,
            headers=HEADERS,
        )
        usd_quote = btc_response.payload["quotes"]["USD"]
        data["BTC_P"] = f"${usd_quote['price']:,.0f}"
        data["BTC_C"] = f"{usd_quote['percent_change_24h']:.2f}%"
        data["BTC_7D"] = f"{usd_quote['percent_change_7d']:.2f}%"
        data["Vol_24h"] = f"${usd_quote['volume_24h']:,.0f}"
        data["BTC_MCap"] = f"${usd_quote['market_cap']/1e9:.0f}B"
        health.success("Coinpaprika BTC", btc_response.latency_ms)
    except FetchError as exc:
        _record_fetch_error(health, "Coinpaprika BTC", exc)
        _set_defaults(
            data,
            {
                "BTC_P": PLACEHOLDER,
                "BTC_C": PLACEHOLDER,
                "BTC_7D": PLACEHOLDER,
                "Vol_24h": PLACEHOLDER,
                "BTC_MCap": PLACEHOLDER,
            },
        )
    except DATA_PARSE_EXCEPTIONS as exc:
        _record_parse_error(
            health, "Coinpaprika BTC", exc, latency_ms=btc_response.latency_ms if btc_response else None
        )
        _set_defaults(
            data,
            {
                "BTC_P": PLACEHOLDER,
                "BTC_C": PLACEHOLDER,
                "BTC_7D": PLACEHOLDER,
                "Vol_24h": PLACEHOLDER,
                "BTC_MCap": PLACEHOLDER,
            },
        )

    alt_ids = {
        "ETH": "eth-ethereum",
        "SOL": "sol-solana",
        "BNB": "bnb-binance-coin",
        "XRP": "xrp-xrp",
        "ADA": "ada-cardano",
        "AVAX": "avax-avalanche",
        "DOT": "dot-polkadot",
        "LINK": "link-chainlink",
    }
    alt_started_at = time.perf_counter()
    alt_successes = 0
    alt_failures = []
    for sym, cid in alt_ids.items():
        try:
            response = safe_fetch_json(
                "Coinpaprika Altcoins",
                f"https://api.coinpaprika.com/v1/tickers/{cid}",
                timeout=6,
                headers=HEADERS,
            )
            usd_quote = response.payload["quotes"]["USD"]
            data[f"{sym}_P"] = f"${usd_quote['price']:,.2f}"
            data[f"{sym}_C"] = f"{usd_quote['percent_change_24h']:.2f}%"
            data[f"{sym}_7D"] = f"{usd_quote['percent_change_7d']:.2f}%"
            alt_successes += 1
        except FetchError as exc:
            alt_failures.append(f"{sym}: {exc}")
            _set_defaults(
                data,
                {
                    f"{sym}_P": PLACEHOLDER,
                    f"{sym}_C": PLACEHOLDER,
                    f"{sym}_7D": PLACEHOLDER,
                },
            )
        except DATA_PARSE_EXCEPTIONS as exc:
            alt_failures.append(f"{sym}: {_error_message('Parse error', exc)}")
            _set_defaults(
                data,
                {
                    f"{sym}_P": PLACEHOLDER,
                    f"{sym}_C": PLACEHOLDER,
                    f"{sym}_7D": PLACEHOLDER,
                },
            )

    alt_latency = _latency_ms(alt_started_at)
    if alt_successes:
        health.success("Coinpaprika Altcoins", alt_latency)
    else:
        health.failure("Coinpaprika Altcoins", "; ".join(alt_failures) or "No altcoin data", alt_latency)

    global_response = None
    try:
        global_response = safe_fetch_json(
            "Coinpaprika Global",
            "https://api.coinpaprika.com/v1/global",
            timeout=6,
            headers=HEADERS,
        )
        payload = global_response.payload
        data["Total_MCap_Num"] = payload["market_cap_usd"]
        data["Dom"] = f"%{payload['bitcoin_dominance_percentage']:.2f}"
        data["Total_MCap"] = f"${payload['market_cap_usd']/1e12:.2f}T"
        data["Total_Vol"] = f"${payload['volume_24h_usd']/1e9:.1f}B"
        health.success("Coinpaprika Global", global_response.latency_ms)
    except FetchError as exc:
        _record_fetch_error(health, "Coinpaprika Global", exc)
        _set_defaults(
            data,
            {
                "Dom": PLACEHOLDER,
                "Total_MCap": PLACEHOLDER,
                "Total_Vol": PLACEHOLDER,
                "Total_MCap_Num": None,
            },
        )
    except DATA_PARSE_EXCEPTIONS as exc:
        _record_parse_error(
            health, "Coinpaprika Global", exc, latency_ms=global_response.latency_ms if global_response else None
        )
        _set_defaults(
            data,
            {
                "Dom": PLACEHOLDER,
                "Total_MCap": PLACEHOLDER,
                "Total_Vol": PLACEHOLDER,
                "Total_MCap_Num": None,
            },
        )

    eth_dom_response = None
    try:
        eth_dom_response = safe_fetch_json(
            "Coinpaprika ETH Dominance",
            "https://api.coinpaprika.com/v1/tickers/eth-ethereum",
            timeout=5,
            headers=HEADERS,
        )
        dom_val = float(data["Dom"].replace("%", "")) if data.get("Dom") != PLACEHOLDER else 0
        total_mc = float(data["Total_MCap_Num"]) if data.get("Total_MCap_Num") else (
            float(data["BTC_MCap"].replace("$", "").replace("B", "")) * 1e9 / (dom_val / 100)
            if dom_val > 0 and data.get("BTC_MCap") != PLACEHOLDER else 0
        )
        if total_mc > 0:
            eth_market_cap = float(eth_dom_response.payload["quotes"]["USD"]["market_cap"])
            data["ETH_Dom"] = f"%{eth_market_cap/total_mc*100:.2f}"
        else:
            data["ETH_Dom"] = PLACEHOLDER
        health.success("Coinpaprika ETH Dominance", eth_dom_response.latency_ms)
    except FetchError as exc:
        _record_fetch_error(health, "Coinpaprika ETH Dominance", exc)
        data["ETH_Dom"] = PLACEHOLDER
    except DATA_PARSE_EXCEPTIONS as exc:
        _record_parse_error(
            health,
            "Coinpaprika ETH Dominance",
            exc,
            latency_ms=eth_dom_response.latency_ms if eth_dom_response else None,
        )
        data["ETH_Dom"] = PLACEHOLDER

    _load_yfinance_etfs(data, health)

    for symbol in ETF_FLOW_COLUMNS:
        data[f"ETF_FLOW_{symbol}"] = PLACEHOLDER
    data["ETF_FLOW_DATE"] = PLACEHOLDER
    data["ETF_FLOW_SOURCE"] = PLACEHOLDER

    flow_failures = []
    for flow_url in [
        "https://r.jina.ai/http://farside.co.uk/bitcoin-etf-flow-all-data/",
        "https://r.jina.ai/http://farside.co.uk/btc/",
        "https://farside.co.uk/bitcoin-etf-flow-all-data/",
    ]:
        try:
            response = safe_fetch_text("Farside ETF Flow", flow_url, timeout=20, headers=HEADERS, accept=TEXT_ACCEPT)
            latest_row = parse_latest_etf_flow_row(response.payload)
            if not latest_row:
                raise ValueError("No populated ETF flow row found")

            data["ETF_FLOW_DATE"] = latest_row[0]
            for symbol, raw_value in zip(ETF_FLOW_COLUMNS, latest_row[1]):
                data[f"ETF_FLOW_{symbol}"] = format_flow_millions(raw_value)
            data["ETF_FLOW_SOURCE"] = "Farside"
            health.success("Farside ETF Flow", response.latency_ms, stale_after_seconds=43200)
            break
        except FetchError as exc:
            flow_failures.append(str(exc))
        except (TypeError, ValueError) as exc:
            flow_failures.append(_error_message("Parse error", exc))
    else:
        health.failure(
            "Farside ETF Flow",
            "; ".join(flow_failures) or "ETF flow source unavailable",
            stale_after_seconds=43200,
        )

    # ── Endeksler: TradingView önce, yfinance fallback ───────────────────────
    _load_tv_group(
        data, health, "TradingView Indices",
        ["SP500", "NASDAQ", "DAX", "NIKKEI", "HSI", "SHCOMP", "BIST100"],
        value_template="{value:,.2f}",
    )
    # TW'den gelmeyen / eksik kalan semboller için yfinance fallback
    _tv_missing_indices = {k: v for k, v in {
        "SP500":   "^GSPC",
        "NASDAQ":  "^IXIC",
        "DOW":     "^DJI",
        "DAX":     "^GDAXI",
        "FTSE":    "^FTSE",
        "NIKKEI":  "^N225",
        "HSI":     "^HSI",
        "SHCOMP":  ("000001.SS", "^SSEC"),
        "BIST100": "XU100.IS",
        "VIX":     "^VIX",
    }.items() if data.get(k, PLACEHOLDER) == PLACEHOLDER}
    if _tv_missing_indices:
        _load_yfinance_change_group(
            data, health, "yFinance Indices (fallback)",
            _tv_missing_indices,
            period="10d",
            value_template="{value:,.2f}",
        )

    # ── Emtia: TradingView önce, yfinance fallback ───────────────────────────
    _load_tv_group(
        data, health, "TradingView Commodities",
        ["OIL", "GOLD", "SILVER", "NATGAS", "COPPER"],
        value_template="${value:,.2f}",
    )
    _tv_missing_comm = {k: v for k, v in {
        "GOLD":   "GC=F",
        "SILVER": "SI=F",
        "OIL":    "CL=F",
        "NATGAS": "NG=F",
        "COPPER": "HG=F",
        "WHEAT":  "ZW=F",
    }.items() if data.get(k, PLACEHOLDER) == PLACEHOLDER}
    if _tv_missing_comm:
        _load_yfinance_change_group(
            data, health, "yFinance Commodities (fallback)",
            _tv_missing_comm,
            period="5d",
            value_template="${value:,.2f}",
        )

    # ── FX & Faiz: TradingView önce, yfinance fallback ──────────────────────
    _load_tv_group(
        data, health, "TradingView FX",
        ["DXY", "EURUSD", "GBPUSD", "USDJPY", "USDTRY", "USDCHF", "AUDUSD", "US10Y"],
        value_template="{value:.4f}",
    )
    _tv_missing_fx = {k: v for k, v in {
        "DXY":    "DX-Y.NYB",
        "EURUSD": "EURUSD=X",
        "GBPUSD": "GBPUSD=X",
        "USDJPY": "JPY=X",
        "USDTRY": "TRY=X",
        "USDCHF": "CHF=X",
        "AUDUSD": "AUDUSD=X",
        "US10Y":  "^TNX",
    }.items() if data.get(k, PLACEHOLDER) == PLACEHOLDER}
    if _tv_missing_fx:
        _load_yfinance_change_group(
            data, health, "yFinance FX (fallback)",
            _tv_missing_fx,
            period="5d",
            value_template="{value:.4f}",
        )


    correlation_payload = None
    correlation_latency = None
    try:
        correlation_payload, correlation_latency = _download_with_latency(["BTC-USD", "^GSPC", "GC=F"], period="30d")
        closes = correlation_payload["Close"]
        if closes.empty:
            raise ValueError("correlation series is empty")
        correlation_matrix = closes.corr()
        data["Corr_SP500"] = round(correlation_matrix.loc["BTC-USD", "^GSPC"], 2)
        data["Corr_Gold"] = round(correlation_matrix.loc["BTC-USD", "GC=F"], 2)
        health.success("yFinance Correlation", correlation_latency)
    except YFINANCE_EXCEPTIONS as exc:
        health.failure("yFinance Correlation", str(exc), correlation_latency)
        data["Corr_SP500"] = PLACEHOLDER
        data["Corr_Gold"] = PLACEHOLDER

    _load_orderbook_source(
        data,
        health,
        source="Kraken Order Book",
        prefix="",
        url="https://api.kraken.com/0/public/Depth?pair=XBTUSD&count=500",
        bid_getter=lambda payload: payload["result"][list(payload["result"].keys())[0]]["bids"],
        ask_getter=lambda payload: payload["result"][list(payload["result"].keys())[0]]["asks"],
    )
    _load_orderbook_source(
        data,
        health,
        source="OKX Order Book",
        prefix="OKX",
        url="https://www.okx.com/api/v5/market/books?instId=BTC-USDT&sz=400",
        bid_getter=lambda payload: payload["data"][0]["bids"],
        ask_getter=lambda payload: payload["data"][0]["asks"],
    )
    _load_orderbook_source(
        data,
        health,
        source="KuCoin Order Book",
        prefix="KUCOIN",
        url="https://api.kucoin.com/api/v1/market/orderbook/level2_100?symbol=BTC-USDT",
        bid_getter=lambda payload: payload["data"]["bids"],
        ask_getter=lambda payload: payload["data"]["asks"],
    )
    _load_orderbook_source(
        data,
        health,
        source="Gate.io Order Book",
        prefix="GATE",
        url="https://api.gateio.ws/api/v4/spot/order_book?currency_pair=BTC_USDT&limit=200&with_id=true",
        bid_getter=lambda payload: payload["bids"],
        ask_getter=lambda payload: payload["asks"],
    )
    _load_orderbook_source(
        data,
        health,
        source="Coinbase Order Book",
        prefix="COINBASE",
        url="https://api.exchange.coinbase.com/products/BTC-USD/book?level=2",
        bid_getter=lambda payload: payload["bids"],
        ask_getter=lambda payload: payload["asks"],
    )

    orderbook_signal = build_orderbook_signal(data)
    data["ORDERBOOK_SIGNAL"] = orderbook_signal["title"]
    data["ORDERBOOK_SIGNAL_DETAIL"] = orderbook_signal["detail"]
    data["ORDERBOOK_SIGNAL_BADGE"] = orderbook_signal["badge"]
    data["ORDERBOOK_SIGNAL_CLASS"] = orderbook_signal["class"]
    data["ORDERBOOK_SOURCES"] = "Kraken · OKX · KuCoin · Gate.io · Coinbase"

    stablecoin_response = None
    try:
        stablecoin_response = safe_fetch_json(
            "DeFiLlama Stablecoins",
            "https://stablecoins.llama.fi/stablecoins?includePrices=true",
            timeout=8,
            headers=HEADERS,
        )
        pegged_assets = stablecoin_response.payload["peggedAssets"]
        total = sum(item.get("circulating", {}).get("peggedUSD", 0) for item in pegged_assets)

        def stablecoin_cap(symbol):
            coin = next((item for item in pegged_assets if item["symbol"].upper() == symbol), None)
            return coin["circulating"]["peggedUSD"] if coin else 0

        usdt_cap = stablecoin_cap("USDT")
        usdc_cap = stablecoin_cap("USDC")
        dai_cap = stablecoin_cap("DAI")
        data["Total_Stable_Num"] = total
        data["Total_Stable"] = f"${total/1e9:.1f}B"
        data["USDT_MCap"] = f"${usdt_cap/1e9:.1f}B"
        data["USDC_MCap"] = f"${usdc_cap/1e9:.1f}B"
        data["DAI_MCap"] = f"${dai_cap/1e9:.1f}B"
        data["USDT_Dom_Stable"] = f"%{usdt_cap/total*100:.1f}" if total > 0 else PLACEHOLDER
        data["STABLE_C_D"] = f"%{total/data['Total_MCap_Num']*100:.2f}" if data.get("Total_MCap_Num") else PLACEHOLDER
        health.success("DeFiLlama Stablecoins", stablecoin_response.latency_ms, stale_after_seconds=21600)
    except FetchError as exc:
        _record_fetch_error(health, "DeFiLlama Stablecoins", exc, stale_after_seconds=21600)
        _set_defaults(
            data,
            {
                "Total_Stable": PLACEHOLDER,
                "USDT_MCap": PLACEHOLDER,
                "USDC_MCap": PLACEHOLDER,
                "DAI_MCap": PLACEHOLDER,
                "USDT_Dom_Stable": PLACEHOLDER,
                "Total_Stable_Num": None,
                "STABLE_C_D": PLACEHOLDER,
            },
        )
    except DATA_PARSE_EXCEPTIONS as exc:
        _record_parse_error(
            health,
            "DeFiLlama Stablecoins",
            exc,
            latency_ms=stablecoin_response.latency_ms if stablecoin_response else None,
            stale_after_seconds=21600,
        )
        _set_defaults(
            data,
            {
                "Total_Stable": PLACEHOLDER,
                "USDT_MCap": PLACEHOLDER,
                "USDC_MCap": PLACEHOLDER,
                "DAI_MCap": PLACEHOLDER,
                "USDT_Dom_Stable": PLACEHOLDER,
                "Total_Stable_Num": None,
                "STABLE_C_D": PLACEHOLDER,
            },
        )

    usdt_data = fetch_live_usdt_d()
    usdt_health = usdt_data.pop("_health", {})
    data.update(usdt_data)

    data["OI"] = PLACEHOLDER
    data["FR"] = PLACEHOLDER
    data["Taker"] = PLACEHOLDER
    data["LS_Ratio"] = PLACEHOLDER
    data["Long_Pct"] = PLACEHOLDER
    data["Short_Pct"] = PLACEHOLDER
    data["LS_Signal"] = PLACEHOLDER

    if fred_api_key:
        m2_response = None
        try:
            m2_response = _load_fred_series(
                series_id="M2SL",
                api_key=fred_api_key,
                limit=13,
                source="FRED M2",
            )
            observations = m2_response.payload["observations"]
            latest = float(observations[0]["value"])
            baseline = float(observations[12]["value"])
            data["M2"] = f"%{(latest - baseline) / baseline * 100:.2f}"
            health.success("FRED M2", m2_response.latency_ms, stale_after_seconds=21600)
        except FetchError as exc:
            _record_fetch_error(health, "FRED M2", exc, stale_after_seconds=21600)
            data["M2"] = PLACEHOLDER
        except DATA_PARSE_EXCEPTIONS as exc:
            _record_parse_error(
                health,
                "FRED M2",
                exc,
                latency_ms=m2_response.latency_ms if m2_response else None,
                stale_after_seconds=21600,
            )
            data["M2"] = PLACEHOLDER

        fed_response = None
        try:
            fed_response = _load_fred_series(
                series_id="FEDFUNDS",
                api_key=fred_api_key,
                limit=1,
                source="FRED FEDFUNDS",
            )
            observations = fed_response.payload["observations"]
            data["FED"] = f"%{observations[0]['value']}"
            health.success("FRED FEDFUNDS", fed_response.latency_ms, stale_after_seconds=21600)
        except FetchError as exc:
            _record_fetch_error(health, "FRED FEDFUNDS", exc, stale_after_seconds=21600)
            data["FED"] = PLACEHOLDER
        except DATA_PARSE_EXCEPTIONS as exc:
            _record_parse_error(
                health,
                "FRED FEDFUNDS",
                exc,
                latency_ms=fed_response.latency_ms if fed_response else None,
                stale_after_seconds=21600,
            )
            data["FED"] = PLACEHOLDER
    else:
        data["M2"] = PLACEHOLDER
        data["FED"] = PLACEHOLDER
        health.failure("FRED M2", "FRED_API_KEY missing", stale_after_seconds=21600)
        health.failure("FRED FEDFUNDS", "FRED_API_KEY missing", stale_after_seconds=21600)

    fng_response = None
    try:
        fng_response = safe_fetch_json(
            "Alternative.me FNG",
            "https://api.alternative.me/fng/?limit=2",
            timeout=5,
            headers=HEADERS,
        )
        fng = fng_response.payload["data"]
        data["FNG"] = f"{fng[0]['value']} ({fng[0]['value_classification']})"
        data["FNG_PREV"] = f"{fng[1]['value']} ({fng[1]['value_classification']})"
        data["FNG_NUM"] = int(fng[0]["value"])
        health.success("Alternative.me FNG", fng_response.latency_ms, stale_after_seconds=1800)
    except FetchError as exc:
        _record_fetch_error(health, "Alternative.me FNG", exc, stale_after_seconds=1800)
        _set_defaults(data, {"FNG": PLACEHOLDER, "FNG_PREV": PLACEHOLDER, "FNG_NUM": 0})
    except DATA_PARSE_EXCEPTIONS as exc:
        _record_parse_error(
            health,
            "Alternative.me FNG",
            exc,
            latency_ms=fng_response.latency_ms if fng_response else None,
            stale_after_seconds=1800,
        )
        _set_defaults(data, {"FNG": PLACEHOLDER, "FNG_PREV": PLACEHOLDER, "FNG_NUM": 0})

    # Stock Market Fear & Greed (yfinance bazlı composite)
    try:
        stock_fng = _compute_stock_fng()
        data.update(stock_fng)
    except Exception:
        _set_defaults(data, {
            "STOCK_FNG_NUM": 0, "STOCK_FNG": PLACEHOLDER,
            "STOCK_FNG_LABEL": PLACEHOLDER, "STOCK_FNG_VIX": 0,
            "STOCK_FNG_MOM": 0, "STOCK_FNG_BRD": 0,
        })

    coindesk_response = None
    try:
        coindesk_response = safe_fetch_text(
            "CoinDesk News",
            "https://www.coindesk.com/arc/outboundfeeds/rss/",
            timeout=8,
            headers=HEADERS,
            accept=TEXT_ACCEPT,
        )
        titles = re.findall(r"<title><!\[CDATA\[(.*?)\]\]></title>", coindesk_response.payload)[1:11]
        links = re.findall(r"<link>(https://www\.coindesk\.com.*?)</link>", coindesk_response.payload)[:10]
        dates = re.findall(r"<pubDate>(.*?)</pubDate>", coindesk_response.payload)[:10]
        if not titles:
            raise ValueError("CoinDesk RSS is empty")

        data["NEWS"] = [
            {
                "title": title,
                "url": links[i] if i < len(links) else "#",
                "source": "CoinDesk",
                "time": dates[i][:16] if i < len(dates) else "",
            }
            for i, title in enumerate(titles)
        ]
        health.success("CoinDesk News", coindesk_response.latency_ms, stale_after_seconds=1800)
    except FetchError as exc:
        _record_fetch_error(health, "CoinDesk News", exc, stale_after_seconds=1800)
        data["NEWS"] = []
    except (TypeError, ValueError) as exc:
        _record_parse_error(
            health,
            "CoinDesk News",
            exc,
            latency_ms=coindesk_response.latency_ms if coindesk_response else None,
            stale_after_seconds=1800,
        )
        data["NEWS"] = []

    if not data.get("NEWS"):
        cryptocompare_response = None
        try:
            cryptocompare_response = safe_fetch_json(
                "CryptoCompare News",
                "https://min-api.cryptocompare.com/data/v2/news/?lang=EN&sortOrder=latest&limit=10",
                timeout=6,
                headers=HEADERS,
            )
            data["NEWS"] = [
                {
                    "title": news["title"],
                    "url": news["url"],
                    "source": news["source_info"]["name"],
                    "time": pd.Timestamp(news["published_on"], unit="s").strftime("%d %b %H:%M"),
                }
                for news in cryptocompare_response.payload["Data"][:10]
            ]
            health.success("CryptoCompare News", cryptocompare_response.latency_ms, stale_after_seconds=1800)
        except FetchError as exc:
            _record_fetch_error(health, "CryptoCompare News", exc, stale_after_seconds=1800)
            data["NEWS"] = []
        except DATA_PARSE_EXCEPTIONS as exc:
            _record_parse_error(
                health,
                "CryptoCompare News",
                exc,
                latency_ms=cryptocompare_response.latency_ms if cryptocompare_response else None,
                stale_after_seconds=1800,
            )
            data["NEWS"] = []

    data["_health"] = _merge_health_maps(health.export(), usdt_health)
    return data


@_cache_data_headless_safe(ttl=MARKET_TTL)
def _fetch_market_snapshot():
    data = {}
    health = HealthRecorder()

    btc_response = None
    try:
        btc_response = safe_fetch_json(
            "Coinpaprika BTC", "https://api.coinpaprika.com/v1/tickers/btc-bitcoin", timeout=8, headers=HEADERS
        )
        usd_quote = btc_response.payload["quotes"]["USD"]
        data["BTC_P"] = f"${usd_quote['price']:,.0f}"
        data["BTC_C"] = f"{usd_quote['percent_change_24h']:.2f}%"
        data["BTC_7D"] = f"{usd_quote['percent_change_7d']:.2f}%"
        data["Vol_24h"] = f"${usd_quote['volume_24h']:,.0f}"
        data["BTC_MCap"] = f"${usd_quote['market_cap']/1e9:.0f}B"
        health.success("Coinpaprika BTC", btc_response.latency_ms)
    except FetchError as exc:
        _record_fetch_error(health, "Coinpaprika BTC", exc)
        _set_defaults(
            data,
            {
                "BTC_P": PLACEHOLDER,
                "BTC_C": PLACEHOLDER,
                "BTC_7D": PLACEHOLDER,
                "Vol_24h": PLACEHOLDER,
                "BTC_MCap": PLACEHOLDER,
            },
        )
    except DATA_PARSE_EXCEPTIONS as exc:
        _record_parse_error(
            health, "Coinpaprika BTC", exc, latency_ms=btc_response.latency_ms if btc_response else None
        )
        _set_defaults(
            data,
            {
                "BTC_P": PLACEHOLDER,
                "BTC_C": PLACEHOLDER,
                "BTC_7D": PLACEHOLDER,
                "Vol_24h": PLACEHOLDER,
                "BTC_MCap": PLACEHOLDER,
            },
        )

    alt_ids = {
        "ETH": "eth-ethereum",
        "SOL": "sol-solana",
        "BNB": "bnb-binance-coin",
        "XRP": "xrp-xrp",
        "ADA": "ada-cardano",
        "AVAX": "avax-avalanche",
        "DOT": "dot-polkadot",
        "LINK": "link-chainlink",
    }
    alt_started_at = time.perf_counter()
    alt_successes = 0
    alt_failures = []
    with ThreadPoolExecutor(max_workers=min(6, len(alt_ids))) as executor:
        future_map = {
            executor.submit(
                lambda sym=sym, cid=cid: (
                    sym,
                    safe_fetch_json(
                        "Coinpaprika Altcoins",
                        f"https://api.coinpaprika.com/v1/tickers/{cid}",
                        timeout=6,
                        headers=HEADERS,
                    ),
                )
            ): sym
            for sym, cid in alt_ids.items()
        }
        for future in as_completed(future_map):
            sym = future_map[future]
            try:
                _, response = future.result()
                usd_quote = response.payload["quotes"]["USD"]
                data[f"{sym}_P"] = f"${usd_quote['price']:,.2f}"
                data[f"{sym}_C"] = f"{usd_quote['percent_change_24h']:.2f}%"
                data[f"{sym}_7D"] = f"{usd_quote['percent_change_7d']:.2f}%"
                alt_successes += 1
            except FetchError as exc:
                alt_failures.append(f"{sym}: {exc}")
                _set_defaults(data, {f"{sym}_P": PLACEHOLDER, f"{sym}_C": PLACEHOLDER, f"{sym}_7D": PLACEHOLDER})
            except DATA_PARSE_EXCEPTIONS as exc:
                alt_failures.append(f"{sym}: {_error_message('Parse error', exc)}")
                _set_defaults(data, {f"{sym}_P": PLACEHOLDER, f"{sym}_C": PLACEHOLDER, f"{sym}_7D": PLACEHOLDER})

    alt_latency = _latency_ms(alt_started_at)
    if alt_successes:
        health.success("Coinpaprika Altcoins", alt_latency)
    else:
        health.failure("Coinpaprika Altcoins", "; ".join(alt_failures) or "No altcoin data", alt_latency)

    global_response = None
    try:
        global_response = safe_fetch_json(
            "Coinpaprika Global", "https://api.coinpaprika.com/v1/global", timeout=6, headers=HEADERS
        )
        payload = global_response.payload
        data["Total_MCap_Num"] = payload["market_cap_usd"]
        data["Dom"] = f"%{payload['bitcoin_dominance_percentage']:.2f}"
        data["Total_MCap"] = f"${payload['market_cap_usd']/1e12:.2f}T"
        data["Total_Vol"] = f"${payload['volume_24h_usd']/1e9:.1f}B"
        health.success("Coinpaprika Global", global_response.latency_ms)
    except FetchError as exc:
        _record_fetch_error(health, "Coinpaprika Global", exc)
        _set_defaults(
            data, {"Dom": PLACEHOLDER, "Total_MCap": PLACEHOLDER, "Total_Vol": PLACEHOLDER, "Total_MCap_Num": None}
        )
    except DATA_PARSE_EXCEPTIONS as exc:
        _record_parse_error(
            health, "Coinpaprika Global", exc, latency_ms=global_response.latency_ms if global_response else None
        )
        _set_defaults(
            data, {"Dom": PLACEHOLDER, "Total_MCap": PLACEHOLDER, "Total_Vol": PLACEHOLDER, "Total_MCap_Num": None}
        )

    eth_dom_response = None
    try:
        eth_dom_response = safe_fetch_json(
            "Coinpaprika ETH Dominance",
            "https://api.coinpaprika.com/v1/tickers/eth-ethereum",
            timeout=5,
            headers=HEADERS,
        )
        dom_val = float(data["Dom"].replace("%", "")) if data.get("Dom") != PLACEHOLDER else 0
        total_mc = float(data["Total_MCap_Num"]) if data.get("Total_MCap_Num") else (
            float(data["BTC_MCap"].replace("$", "").replace("B", "")) * 1e9 / (dom_val / 100)
            if dom_val > 0 and data.get("BTC_MCap") != PLACEHOLDER else 0
        )
        if total_mc > 0:
            data["ETH_Dom"] = f"%{float(eth_dom_response.payload['quotes']['USD']['market_cap'])/total_mc*100:.2f}"
        else:
            data["ETH_Dom"] = PLACEHOLDER
        health.success("Coinpaprika ETH Dominance", eth_dom_response.latency_ms)
    except FetchError as exc:
        _record_fetch_error(health, "Coinpaprika ETH Dominance", exc)
        data["ETH_Dom"] = PLACEHOLDER
    except DATA_PARSE_EXCEPTIONS as exc:
        _record_parse_error(
            health,
            "Coinpaprika ETH Dominance",
            exc,
            latency_ms=eth_dom_response.latency_ms if eth_dom_response else None,
        )
        data["ETH_Dom"] = PLACEHOLDER

    yfinance_tasks = {
        "etfs": lambda: _load_yfinance_etfs(data, health),
        "indices": lambda: _load_tv_group(
            data, health, "TradingView Indices",
            ["SP500", "NASDAQ", "DAX", "NIKKEI", "HSI", "SHCOMP", "BIST100"],
            value_template="{value:,.2f}",
        ) or _load_yfinance_change_group(
            data, health, "yFinance Indices (fallback)",
            {k: v for k, v in {
                "SP500": "^GSPC", "NASDAQ": "^IXIC", "DOW": "^DJI",
                "DAX": "^GDAXI", "FTSE": "^FTSE", "NIKKEI": "^N225",
                "HSI": "^HSI", "SHCOMP": ("000001.SS", "^SSEC"),
                "BIST100": "XU100.IS", "VIX": "^VIX",
            }.items() if data.get(k, PLACEHOLDER) == PLACEHOLDER},
            period="10d", value_template="{value:,.2f}",
        ) if any(data.get(k, PLACEHOLDER) == PLACEHOLDER for k in ["SP500","NASDAQ","DAX","NIKKEI","HSI"]) else None,
        "commodities": lambda: _load_tv_group(
            data, health, "TradingView Commodities",
            ["OIL", "GOLD", "SILVER", "NATGAS", "COPPER"],
            value_template="${value:,.2f}",
        ) or _load_yfinance_change_group(
            data, health, "yFinance Commodities (fallback)",
            {k: v for k, v in {
                "GOLD": "GC=F", "SILVER": "SI=F", "OIL": "CL=F",
                "NATGAS": "NG=F", "COPPER": "HG=F", "WHEAT": "ZW=F",
            }.items() if data.get(k, PLACEHOLDER) == PLACEHOLDER},
            period="5d", value_template="${value:,.2f}",
        ) if any(data.get(k, PLACEHOLDER) == PLACEHOLDER for k in ["OIL","GOLD","SILVER"]) else None,
        "fx": lambda: _load_tv_group(
            data, health, "TradingView FX",
            ["DXY", "EURUSD", "GBPUSD", "USDJPY", "USDTRY", "USDCHF", "AUDUSD", "US10Y"],
            value_template="{value:.4f}",
        ) or _load_yfinance_change_group(
            data, health, "yFinance FX (fallback)",
            {k: v for k, v in {
                "DXY": "DX-Y.NYB", "EURUSD": "EURUSD=X", "GBPUSD": "GBPUSD=X",
                "USDJPY": "JPY=X", "USDTRY": "TRY=X", "USDCHF": "CHF=X",
                "AUDUSD": "AUDUSD=X", "US10Y": "^TNX",
            }.items() if data.get(k, PLACEHOLDER) == PLACEHOLDER},
            period="5d", value_template="{value:.4f}",
        ) if any(data.get(k, PLACEHOLDER) == PLACEHOLDER for k in ["DXY","EURUSD","US10Y"]) else None,
        "breadth": lambda: _load_yfinance_change_group(
            data,
            health,
            "yFinance Breadth Proxies",
            {
                "SPY": "SPY",
                "RSP": "RSP",
                "QQQ": "QQQ",
                "IWM": "IWM",
                "XLK": "XLK",
                "XLF": "XLF",
                "XLI": "XLI",
                "XLE": "XLE",
                "XLY": "XLY",
            },
            period="5d",
            value_template="${value:,.2f}",
        ),
    }
    _run_parallel_tasks(yfinance_tasks, max_workers=5)

    correlation_payload = None
    correlation_latency = None
    try:
        correlation_payload, correlation_latency = _download_with_latency(["BTC-USD", "^GSPC", "GC=F"], period="30d")
        closes = correlation_payload["Close"]
        if closes.empty:
            raise ValueError("correlation series is empty")
        correlation_matrix = closes.corr()
        data["Corr_SP500"] = round(correlation_matrix.loc["BTC-USD", "^GSPC"], 2)
        data["Corr_Gold"] = round(correlation_matrix.loc["BTC-USD", "GC=F"], 2)
        health.success("yFinance Correlation", correlation_latency)
    except YFINANCE_EXCEPTIONS as exc:
        health.failure("yFinance Correlation", str(exc), correlation_latency)
        data["Corr_SP500"] = PLACEHOLDER
        data["Corr_Gold"] = PLACEHOLDER

    for symbol in ETF_FLOW_COLUMNS:
        data[f"ETF_FLOW_{symbol}"] = PLACEHOLDER
    data["ETF_FLOW_DATE"] = PLACEHOLDER
    data["ETF_FLOW_SOURCE"] = PLACEHOLDER
    flow_failures = []
    for flow_url in [
        "https://r.jina.ai/http://farside.co.uk/bitcoin-etf-flow-all-data/",
        "https://r.jina.ai/http://farside.co.uk/btc/",
        "https://farside.co.uk/bitcoin-etf-flow-all-data/",
    ]:
        try:
            response = safe_fetch_text("Farside ETF Flow", flow_url, timeout=20, headers=HEADERS, accept=TEXT_ACCEPT)
            latest_row = parse_latest_etf_flow_row(response.payload)
            if not latest_row:
                raise ValueError("No populated ETF flow row found")
            data["ETF_FLOW_DATE"] = latest_row[0]
            for symbol, raw_value in zip(ETF_FLOW_COLUMNS, latest_row[1]):
                data[f"ETF_FLOW_{symbol}"] = format_flow_millions(raw_value)
            data["ETF_FLOW_SOURCE"] = "Farside"
            health.success("Farside ETF Flow", response.latency_ms, stale_after_seconds=43200)
            break
        except FetchError as exc:
            flow_failures.append(str(exc))
        except (TypeError, ValueError) as exc:
            flow_failures.append(_error_message("Parse error", exc))
    else:
        health.failure(
            "Farside ETF Flow", "; ".join(flow_failures) or "ETF flow source unavailable", stale_after_seconds=43200
        )

    data["_health"] = health.export()
    return data


@_cache_data_headless_safe(ttl=FAST_TTL)
def _fetch_orderbook_snapshot():
    data = {}
    health = HealthRecorder()
    _run_parallel_tasks(
        {
            "kraken": lambda: _load_orderbook_source(
                data,
                health,
                source="Kraken Order Book",
                prefix="",
                url="https://api.kraken.com/0/public/Depth?pair=XBTUSD&count=500",
                bid_getter=lambda payload: payload["result"][list(payload["result"].keys())[0]]["bids"],
                ask_getter=lambda payload: payload["result"][list(payload["result"].keys())[0]]["asks"],
            ),
            "okx": lambda: _load_orderbook_source(
                data,
                health,
                source="OKX Order Book",
                prefix="OKX",
                url="https://www.okx.com/api/v5/market/books?instId=BTC-USDT&sz=400",
                bid_getter=lambda payload: payload["data"][0]["bids"],
                ask_getter=lambda payload: payload["data"][0]["asks"],
            ),
            "kucoin": lambda: _load_orderbook_source(
                data,
                health,
                source="KuCoin Order Book",
                prefix="KUCOIN",
                url="https://api.kucoin.com/api/v1/market/orderbook/level2_100?symbol=BTC-USDT",
                bid_getter=lambda payload: payload["data"]["bids"],
                ask_getter=lambda payload: payload["data"]["asks"],
            ),
            "gate": lambda: _load_orderbook_source(
                data,
                health,
                source="Gate.io Order Book",
                prefix="GATE",
                url="https://api.gateio.ws/api/v4/spot/order_book?currency_pair=BTC_USDT&limit=200&with_id=true",
                bid_getter=lambda payload: payload["bids"],
                ask_getter=lambda payload: payload["asks"],
            ),
            "coinbase": lambda: _load_orderbook_source(
                data,
                health,
                source="Coinbase Order Book",
                prefix="COINBASE",
                url="https://api.exchange.coinbase.com/products/BTC-USD/book?level=2",
                bid_getter=lambda payload: payload["bids"],
                ask_getter=lambda payload: payload["asks"],
            ),
        },
        max_workers=5,
    )
    signal = build_orderbook_signal(data)
    data["ORDERBOOK_SIGNAL"] = signal["title"]
    data["ORDERBOOK_SIGNAL_DETAIL"] = signal["detail"]
    data["ORDERBOOK_SIGNAL_BADGE"] = signal["badge"]
    data["ORDERBOOK_SIGNAL_CLASS"] = signal["class"]
    data["ORDERBOOK_SOURCES"] = "Kraken · OKX · KuCoin · Gate.io · Coinbase"
    data["_health"] = health.export()
    return data


@_cache_data_headless_safe(ttl=MARKET_TTL)  # FIX 4: 6 saat (MACRO_TTL) → 5 dakika (MARKET_TTL)
def _fetch_stablecoin_snapshot():
    data = {}
    health = HealthRecorder()
    stablecoin_response = None
    try:
        stablecoin_response = safe_fetch_json(
            "DeFiLlama Stablecoins",
            "https://stablecoins.llama.fi/stablecoins?includePrices=true",
            timeout=8,
            headers=HEADERS,
        )
        pegged_assets = stablecoin_response.payload["peggedAssets"]
        total = sum(item.get("circulating", {}).get("peggedUSD", 0) for item in pegged_assets)

        def stablecoin_cap(symbol):
            coin = next((item for item in pegged_assets if item["symbol"].upper() == symbol), None)
            return coin["circulating"]["peggedUSD"] if coin else 0

        usdt_cap = stablecoin_cap("USDT")
        usdc_cap = stablecoin_cap("USDC")
        dai_cap = stablecoin_cap("DAI")
        data["Total_Stable_Num"] = total
        data["Total_Stable"] = f"${total/1e9:.1f}B"
        data["USDT_MCap"] = f"${usdt_cap/1e9:.1f}B"
        data["USDC_MCap"] = f"${usdc_cap/1e9:.1f}B"
        data["DAI_MCap"] = f"${dai_cap/1e9:.1f}B"
        data["USDT_Dom_Stable"] = f"%{usdt_cap/total*100:.1f}" if total > 0 else PLACEHOLDER
        data["STABLE_C_D"] = PLACEHOLDER
        health.success("DeFiLlama Stablecoins", stablecoin_response.latency_ms, stale_after_seconds=300)
    except FetchError as exc:
        _record_fetch_error(health, "DeFiLlama Stablecoins", exc, stale_after_seconds=300)
        _set_defaults(
            data,
            {
                "Total_Stable": PLACEHOLDER,
                "USDT_MCap": PLACEHOLDER,
                "USDC_MCap": PLACEHOLDER,
                "DAI_MCap": PLACEHOLDER,
                "USDT_Dom_Stable": PLACEHOLDER,
                "Total_Stable_Num": None,
                "STABLE_C_D": PLACEHOLDER,
            },
        )
    except DATA_PARSE_EXCEPTIONS as exc:
        _record_parse_error(
            health,
            "DeFiLlama Stablecoins",
            exc,
            latency_ms=stablecoin_response.latency_ms if stablecoin_response else None,
            stale_after_seconds=300,
        )
        _set_defaults(
            data,
            {
                "Total_Stable": PLACEHOLDER,
                "USDT_MCap": PLACEHOLDER,
                "USDC_MCap": PLACEHOLDER,
                "DAI_MCap": PLACEHOLDER,
                "USDT_Dom_Stable": PLACEHOLDER,
                "Total_Stable_Num": None,
                "STABLE_C_D": PLACEHOLDER,
            },
        )
    data["_health"] = health.export()
    return data


@_cache_data_headless_safe(ttl=MACRO_TTL)
def _fetch_macro_snapshot(fred_api_key=""):
    data = {}
    health = HealthRecorder()
    if not fred_api_key:
        data["M2"] = PLACEHOLDER
        data["FED"] = PLACEHOLDER
        health.failure("FRED M2", "FRED_API_KEY missing", stale_after_seconds=21600)
        health.failure("FRED FEDFUNDS", "FRED_API_KEY missing", stale_after_seconds=21600)
        data["_health"] = health.export()
        return data

    task_map = {
        "m2": lambda: _load_fred_series(series_id="M2SL", api_key=fred_api_key, limit=13, source="FRED M2"),
        "fed": lambda: _load_fred_series(series_id="FEDFUNDS", api_key=fred_api_key, limit=1, source="FRED FEDFUNDS"),
    }
    results = _run_parallel_tasks(task_map, max_workers=2)

    m2_response = results["m2"]
    fed_response = results["fed"]
    if isinstance(m2_response, FetchError):
        _record_fetch_error(health, "FRED M2", m2_response, stale_after_seconds=21600)
        data["M2"] = PLACEHOLDER
    elif isinstance(m2_response, Exception):
        _record_parse_error(health, "FRED M2", m2_response, stale_after_seconds=21600)
        data["M2"] = PLACEHOLDER
    else:
        try:
            observations = m2_response.payload["observations"]
            latest = float(observations[0]["value"])
            baseline = float(observations[12]["value"])
            data["M2"] = f"%{(latest - baseline) / baseline * 100:.2f}"
            health.success("FRED M2", m2_response.latency_ms, stale_after_seconds=21600)
        except DATA_PARSE_EXCEPTIONS as exc:
            _record_parse_error(health, "FRED M2", exc, latency_ms=m2_response.latency_ms, stale_after_seconds=21600)
            data["M2"] = PLACEHOLDER

    if isinstance(fed_response, FetchError):
        _record_fetch_error(health, "FRED FEDFUNDS", fed_response, stale_after_seconds=21600)
        data["FED"] = PLACEHOLDER
    elif isinstance(fed_response, Exception):
        _record_parse_error(health, "FRED FEDFUNDS", fed_response, stale_after_seconds=21600)
        data["FED"] = PLACEHOLDER
    else:
        try:
            observations = fed_response.payload["observations"]
            data["FED"] = f"%{observations[0]['value']}"
            health.success("FRED FEDFUNDS", fed_response.latency_ms, stale_after_seconds=21600)
        except DATA_PARSE_EXCEPTIONS as exc:
            _record_parse_error(
                health, "FRED FEDFUNDS", exc, latency_ms=fed_response.latency_ms, stale_after_seconds=21600
            )
            data["FED"] = PLACEHOLDER

    data["_health"] = health.export()
    return data


@_cache_data_headless_safe(ttl=3600)
def _fetch_onchain_snapshot():
    # blockchain.info erişim sorunu (403) — veri kaynağı devre dışı
    return {"_health": HealthRecorder().export()}


@_cache_data_headless_safe(ttl=SENTIMENT_TTL)
def _fetch_sentiment_snapshot():
    data = {}
    health = HealthRecorder()
    fng_response = None
    try:
        fng_response = safe_fetch_json(
            "Alternative.me FNG", "https://api.alternative.me/fng/?limit=2", timeout=5, headers=HEADERS
        )
        fng = fng_response.payload["data"]
        data["FNG"] = f"{fng[0]['value']} ({fng[0]['value_classification']})"
        data["FNG_PREV"] = f"{fng[1]['value']} ({fng[1]['value_classification']})"
        data["FNG_NUM"] = int(fng[0]["value"])
        health.success("Alternative.me FNG", fng_response.latency_ms, stale_after_seconds=1800)
    except FetchError as exc:
        _record_fetch_error(health, "Alternative.me FNG", exc, stale_after_seconds=1800)
        _set_defaults(data, {"FNG": PLACEHOLDER, "FNG_PREV": PLACEHOLDER, "FNG_NUM": 0})
    except DATA_PARSE_EXCEPTIONS as exc:
        _record_parse_error(
            health,
            "Alternative.me FNG",
            exc,
            latency_ms=fng_response.latency_ms if fng_response else None,
            stale_after_seconds=1800,
        )
        _set_defaults(data, {"FNG": PLACEHOLDER, "FNG_PREV": PLACEHOLDER, "FNG_NUM": 0})

    # Stock Market Fear & Greed (yfinance bazlı composite)
    try:
        stock_fng = _compute_stock_fng()
        data.update(stock_fng)
    except Exception:
        _set_defaults(data, {
            "STOCK_FNG_NUM": 0, "STOCK_FNG": PLACEHOLDER,
            "STOCK_FNG_LABEL": PLACEHOLDER, "STOCK_FNG_VIX": 0,
            "STOCK_FNG_MOM": 0, "STOCK_FNG_BRD": 0,
        })

    coindesk_response = None
    try:
        coindesk_response = safe_fetch_text(
            "CoinDesk News",
            "https://www.coindesk.com/arc/outboundfeeds/rss/",
            timeout=8,
            headers=HEADERS,
            accept=TEXT_ACCEPT,
        )
        titles = re.findall(r"<title><!\[CDATA\[(.*?)\]\]></title>", coindesk_response.payload)[1:11]
        links = re.findall(r"<link>(https://www\.coindesk\.com.*?)</link>", coindesk_response.payload)[:10]
        dates = re.findall(r"<pubDate>(.*?)</pubDate>", coindesk_response.payload)[:10]
        if not titles:
            raise ValueError("CoinDesk RSS is empty")
        data["NEWS"] = [
            {
                "title": title,
                "url": links[i] if i < len(links) else "#",
                "source": "CoinDesk",
                "time": dates[i][:16] if i < len(dates) else "",
            }
            for i, title in enumerate(titles)
        ]
        health.success("CoinDesk News", coindesk_response.latency_ms, stale_after_seconds=1800)
    except FetchError as exc:
        _record_fetch_error(health, "CoinDesk News", exc, stale_after_seconds=1800)
        data["NEWS"] = []
    except (TypeError, ValueError) as exc:
        _record_parse_error(
            health,
            "CoinDesk News",
            exc,
            latency_ms=coindesk_response.latency_ms if coindesk_response else None,
            stale_after_seconds=1800,
        )
        data["NEWS"] = []

    if not data.get("NEWS"):
        cryptocompare_response = None
        try:
            cryptocompare_response = safe_fetch_json(
                "CryptoCompare News",
                "https://min-api.cryptocompare.com/data/v2/news/?lang=EN&sortOrder=latest&limit=10",
                timeout=6,
                headers=HEADERS,
            )
            data["NEWS"] = [
                {
                    "title": news["title"],
                    "url": news["url"],
                    "source": news["source_info"]["name"],
                    "time": pd.Timestamp(news["published_on"], unit="s").strftime("%d %b %H:%M"),
                }
                for news in cryptocompare_response.payload["Data"][:10]
            ]
            health.success("CryptoCompare News", cryptocompare_response.latency_ms, stale_after_seconds=1800)
        except FetchError as exc:
            _record_fetch_error(health, "CryptoCompare News", exc, stale_after_seconds=1800)
            data["NEWS"] = []
        except DATA_PARSE_EXCEPTIONS as exc:
            _record_parse_error(
                health,
                "CryptoCompare News",
                exc,
                latency_ms=cryptocompare_response.latency_ms if cryptocompare_response else None,
                stale_after_seconds=1800,
            )
            data["NEWS"] = []

    data["_health"] = health.export()
    return data


@_cache_data_headless_safe(ttl=SENTIMENT_TTL)
def _fetch_economic_calendar_snapshot():
    data = {"ECONOMIC_CALENDAR": [], "ECONOMIC_CALENDAR_SOURCE": PLACEHOLDER}
    health = HealthRecorder()
    response = None
    try:
        response = safe_fetch_json(
            "FairEconomy Calendar",
            "https://nfs.faireconomy.media/ff_calendar_thisweek.json",
            timeout=8,
            headers=HEADERS,
        )
        data["ECONOMIC_CALENDAR"] = _normalize_calendar_events(response.payload)
        data["ECONOMIC_CALENDAR_SOURCE"] = "FairEconomy"
        health.success("FairEconomy Calendar", response.latency_ms, stale_after_seconds=3600)
    except FetchError as exc:
        _record_fetch_error(health, "FairEconomy Calendar", exc, stale_after_seconds=3600)
    except DATA_PARSE_EXCEPTIONS as exc:
        _record_parse_error(
            health,
            "FairEconomy Calendar",
            exc,
            latency_ms=response.latency_ms if response else None,
            stale_after_seconds=3600,
        )

    data["_health"] = health.export()
    return data


def veri_motoru(fred_api_key=""):
    payloads = _run_parallel_tasks(
        {
            "market": _fetch_market_snapshot,
            "orderbook": _fetch_orderbook_snapshot,
            "stable": _fetch_stablecoin_snapshot,
            "usdt": fetch_live_usdt_d,
            "macro": lambda: _fetch_macro_snapshot(fred_api_key),
            "onchain": _fetch_onchain_snapshot,
            "sentiment": _fetch_sentiment_snapshot,
            "calendar": _fetch_economic_calendar_snapshot,
        },
        max_workers=8,
    )
    data = _merge_result_payloads(*payloads.values())
    data.setdefault("OI", PLACEHOLDER)
    data.setdefault("FR", PLACEHOLDER)
    data.setdefault("Taker", PLACEHOLDER)
    data.setdefault("LS_Ratio", PLACEHOLDER)
    data.setdefault("Long_Pct", PLACEHOLDER)
    data.setdefault("Short_Pct", PLACEHOLDER)
    data.setdefault("LS_Signal", PLACEHOLDER)
    data.setdefault("OI_NOTIONAL", PLACEHOLDER)
    data.setdefault("ECONOMIC_CALENDAR", [])
    data.setdefault("ECONOMIC_CALENDAR_SOURCE", PLACEHOLDER)
    # NOTE: STABLE_C_D final computation is done in load_terminal_data using
    # TOTAL_CAP_NUM (TradingView/CoinGecko) which is more accurate than
    # Coinpaprika Total_MCap_Num. Do not compute here to avoid silent override confusion.
    return data


def load_terminal_data(fred_api_key=""):
    task_map = {
        "base": lambda: veri_motoru(fred_api_key),
        "derivatives": turev_cek,
        "market_cap": fetch_live_market_cap_segments,
    }
    payloads = _run_parallel_tasks(task_map, max_workers=3)
    normalized_payloads = [
        (
            payloads[task_name]
            if not isinstance(payloads[task_name], Exception)
            else _task_failure_payload(task_name, payloads[task_name])
        )
        for task_name in ("base", "market_cap", "derivatives")
    ]
    data = _merge_result_payloads(*normalized_payloads)

    # ── FIX 3: BTC.D / ETH.D → TradingView değerleriyle override ──────────────
    # Coinpaprika'nın hesabı TradingView'dan 0.1–0.5% sapabilir.
    # fetch_live_market_cap_segments'ten gelen BTC_DOM_TV / ETH_DOM_TV varsa öncelikli kullan.
    if data.get("BTC_DOM_TV") and data["BTC_DOM_TV"] != PLACEHOLDER:
        data["Dom"] = data["BTC_DOM_TV"]
        data["DOM_SOURCE"] = "TradingView"
    if data.get("ETH_DOM_TV") and data["ETH_DOM_TV"] != PLACEHOLDER:
        data["ETH_Dom"] = data["ETH_DOM_TV"]

    # ── FIX 4: STABLE_C_D → tutarlı kaynak ────────────────────────────────────
    # DeFiLlama stable / TradingView TOTAL (her ikisi de aynı kaynak grubundan).
    # USDT_D zaten fetch_live_usdt_d'den TradingView scrape ile geliyor;
    # Stable.C.D için de TOTAL_CAP_NUM'u (TradingView) referans alıyoruz.
    if data.get("Total_Stable_Num") and data.get("TOTAL_CAP_NUM"):
        data["STABLE_C_D"] = f"%{data['Total_Stable_Num']/data['TOTAL_CAP_NUM']*100:.2f}"
        data["STABLE_C_D_SOURCE"] = "DeFiLlama / TradingView TOTAL"

    # OI Notional: oiCcy (BTC) * BTC fiyatı → $B
    try:
        oi_btc = float(str(data.get("OI", "")).replace(",", "").replace(" BTC", "").strip())
        btc_price = float(str(data.get("BTC_P", "")).replace("$", "").replace(",", "").strip())
        if oi_btc > 0 and btc_price > 0:
            notional_b = oi_btc * btc_price / 1e9
            data["OI_NOTIONAL"] = f"${notional_b:.2f}B"
        else:
            data["OI_NOTIONAL"] = PLACEHOLDER
    except (ValueError, TypeError):
        data["OI_NOTIONAL"] = PLACEHOLDER
    return data


@_cache_data_headless_safe(ttl=FAST_TTL)
def turev_cek():
    data = {}
    health = HealthRecorder()

    funding_response = None
    try:
        funding_response = safe_fetch_json(
            "OKX Funding",
            "https://www.okx.com/api/v5/public/funding-rate?instId=BTC-USDT-SWAP",
            timeout=6,
            headers=HEADERS,
        )
        data["FR"] = f"%{float(funding_response.payload['data'][0]['fundingRate'])*100:.4f}"
        health.success("OKX Funding", funding_response.latency_ms, stale_after_seconds=300)
    except FetchError as exc:
        _record_fetch_error(health, "OKX Funding", exc, stale_after_seconds=300)
        data["FR"] = PLACEHOLDER
    except DATA_PARSE_EXCEPTIONS as exc:
        _record_parse_error(
            health,
            "OKX Funding",
            exc,
            latency_ms=funding_response.latency_ms if funding_response else None,
            stale_after_seconds=300,
        )
        data["FR"] = PLACEHOLDER

    open_interest_response = None
    try:
        open_interest_response = safe_fetch_json(
            "OKX Open Interest",
            "https://www.okx.com/api/v5/public/open-interest?instType=SWAP&instId=BTC-USDT-SWAP",
            timeout=6,
            headers=HEADERS,
        )
        data["OI"] = f"{float(open_interest_response.payload['data'][0]['oiCcy']):,.2f} BTC"
        health.success("OKX Open Interest", open_interest_response.latency_ms, stale_after_seconds=300)
    except FetchError as exc:
        _record_fetch_error(health, "OKX Open Interest", exc, stale_after_seconds=300)
        data["OI"] = PLACEHOLDER
    except DATA_PARSE_EXCEPTIONS as exc:
        _record_parse_error(
            health,
            "OKX Open Interest",
            exc,
            latency_ms=open_interest_response.latency_ms if open_interest_response else None,
            stale_after_seconds=300,
        )
        data["OI"] = PLACEHOLDER

    taker_response = None
    try:
        taker_response = safe_fetch_json(
            "OKX Taker Volume",
            "https://www.okx.com/api/v5/rubik/stat/taker-volume?ccy=BTC&instType=CONTRACTS&period=1H",
            timeout=6,
            headers=HEADERS,
        )
        buy_volume = float(taker_response.payload["data"][0][1])
        sell_volume = float(taker_response.payload["data"][0][2])
        data["Taker"] = f"{buy_volume/sell_volume:.3f}" if sell_volume > 0 else "1.000"
        health.success("OKX Taker Volume", taker_response.latency_ms, stale_after_seconds=300)
    except FetchError as exc:
        _record_fetch_error(health, "OKX Taker Volume", exc, stale_after_seconds=300)
        data["Taker"] = "1.000"
    except DATA_PARSE_EXCEPTIONS as exc:
        _record_parse_error(
            health,
            "OKX Taker Volume",
            exc,
            latency_ms=taker_response.latency_ms if taker_response else None,
            stale_after_seconds=300,
        )
        data["Taker"] = "1.000"

    ls_done = False
    ls_response = None
    for url in [
        "https://www.okx.com/api/v5/rubik/stat/contracts/long-short-account-ratio-contract-top-trader?instId=BTC-USDT-SWAP&period=1H",
        "https://www.okx.com/api/v5/rubik/stat/contracts/long-short-account-ratio?ccy=BTC&period=1H",
    ]:
        try:
            ls_response = safe_fetch_json("OKX Long/Short", url, timeout=6, headers=HEADERS)
            ratio_data = ls_response.payload.get("data", [])
            if not ratio_data:
                raise ValueError("OKX long/short data empty")

            first = ratio_data[0]
            if isinstance(first, dict) and "longRatio" in first:
                long_pct = float(first["longRatio"]) * 100
                short_pct = float(first["shortRatio"]) * 100
                ratio = long_pct / short_pct if short_pct > 0 else 1
            else:
                ratio = float(first[1]) if isinstance(first, list) else 1
                long_pct = ratio / (1 + ratio) * 100
                short_pct = 100 - long_pct

            data["LS_Ratio"] = f"{ratio:.3f}"
            data["Long_Pct"] = f"%{long_pct:.1f}"
            data["Short_Pct"] = f"%{short_pct:.1f}"
            data["LS_Signal"] = "Long ağırlıklı" if ratio > 1 else "Short ağırlıklı"
            health.success("OKX Long/Short", ls_response.latency_ms, stale_after_seconds=300)
            ls_done = True
            break
        except FetchError as exc:
            _record_fetch_error(health, "OKX Long/Short", exc, stale_after_seconds=300)
        except DATA_PARSE_EXCEPTIONS as exc:
            _record_parse_error(
                health,
                "OKX Long/Short",
                exc,
                latency_ms=ls_response.latency_ms if ls_response else None,
                stale_after_seconds=300,
            )

    if not ls_done:
        gate_response = None
        try:
            gate_response = safe_fetch_json(
                "Gate.io Long/Short",
                "https://api.gateio.ws/api/v4/futures/usdt/contract_stats?contract=BTC_USDT&interval=1h&limit=1",
                timeout=6,
                headers=HEADERS,
            )
            ratio = float(gate_response.payload[0].get("lsr_taker", 1))
            long_pct = ratio / (1 + ratio) * 100
            data["LS_Ratio"] = f"{ratio:.3f}"
            data["Long_Pct"] = f"%{long_pct:.1f}"
            data["Short_Pct"] = f"%{100-long_pct:.1f}"
            data["LS_Signal"] = "Long ağırlıklı" if ratio > 1 else "Short ağırlıklı"
            health.success("Gate.io Long/Short", gate_response.latency_ms, stale_after_seconds=300)
            ls_done = True
        except FetchError as exc:
            _record_fetch_error(health, "Gate.io Long/Short", exc, stale_after_seconds=300)
        except DATA_PARSE_EXCEPTIONS as exc:
            _record_parse_error(
                health,
                "Gate.io Long/Short",
                exc,
                latency_ms=gate_response.latency_ms if gate_response else None,
                stale_after_seconds=300,
            )

    if not ls_done:
        data["LS_Ratio"] = PLACEHOLDER
        data["Long_Pct"] = PLACEHOLDER
        data["Short_Pct"] = PLACEHOLDER
        data["LS_Signal"] = PLACEHOLDER

    data["_health"] = health.export()
    return data
