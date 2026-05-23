"""
SA Finance Alpha Terminal — On-Chain Data Service
Cache-backed Coin Metrics CSV fetcher for BTC, USDT and USDC.

Cache policy:
  - First tries cache; returns source_status="cached" if fresh.
  - force_refresh=True → fetches remote regardless.
  - Remote failure → falls back to cache with source_status="fallback".
  - No cache + remote failure → source_status="unavailable", empty DataFrame.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd
import requests

LOGGER = logging.getLogger(__name__)

# ── URLs ─────────────────────────────────────────────────────────────────────
_BTC_URL  = "https://raw.githubusercontent.com/coinmetrics/data/master/csv/btc.csv"
_USDT_URL = "https://raw.githubusercontent.com/coinmetrics/data/master/csv/usdt.csv"
_USDC_URL = "https://raw.githubusercontent.com/coinmetrics/data/master/csv/usdc.csv"

# ── Cache paths ───────────────────────────────────────────────────────────────
_CACHE_DIR  = Path("runtime/cache")
_BTC_CACHE  = _CACHE_DIR / "coinmetrics_btc.csv"
_USDT_CACHE = _CACHE_DIR / "coinmetrics_usdt.csv"
_USDC_CACHE = _CACHE_DIR / "coinmetrics_usdc.csv"

# ── Required columns ─────────────────────────────────────────────────────────
_BTC_REQUIRED_COLS: list[str] = [
    "time", "CapMVRVCur", "AdrActCnt", "AdrBalCnt",
    "FlowInExNtv", "FlowOutExNtv", "SplyExNtv",
    "TxCnt", "TxTfrCnt", "HashRate", "FeeTotNtv",
    "ROI30d", "ROI1yr", "volume_reported_spot_usd_1d",
    "CapMrktCurUSD", "PriceUSD", "SplyCur", "IssTotUSD",
]
_STABLE_REQUIRED_COLS: list[str] = ["time", "CapMrktCurUSD"]

SOURCE_STATUS_LIVE      = "live"
SOURCE_STATUS_CACHED    = "cached"
SOURCE_STATUS_FALLBACK  = "fallback"
SOURCE_STATUS_PARTIAL   = "partial"
SOURCE_STATUS_UNAVAILABLE = "unavailable"


@dataclass
class OnchainDataResult:
    df: pd.DataFrame
    source_status: str
    missing_columns: list[str]
    latest_date: Optional[str]
    fetched_at: Optional[str]
    warnings: list[str] = field(default_factory=list)


def _ensure_cache_dir() -> None:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _fetch_remote(url: str, timeout: int = 30) -> Optional[str]:
    """Download CSV text from URL; returns None on any error."""
    try:
        resp = requests.get(url, timeout=timeout)
        resp.raise_for_status()
        return resp.text
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("Coin Metrics remote fetch failed (%s): %s", url, exc)
        return None


def _parse_csv_text(text: str) -> Optional[pd.DataFrame]:
    """Parse CSV string into DataFrame; returns None on parse error."""
    try:
        from io import StringIO
        return pd.read_csv(StringIO(text), low_memory=False)
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("CSV parse error: %s", exc)
        return None


def _load_cache(path: Path) -> Optional[pd.DataFrame]:
    """Load cached CSV; returns None if missing or corrupt."""
    if not path.exists():
        return None
    try:
        return pd.read_csv(path, low_memory=False)
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("Cache load error (%s): %s", path, exc)
        return None


def _save_cache(path: Path, df: pd.DataFrame) -> None:
    try:
        _ensure_cache_dir()
        df.to_csv(path, index=False)
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("Cache save error (%s): %s", path, exc)


def _check_missing(df: pd.DataFrame, required: list[str]) -> list[str]:
    return [c for c in required if c not in df.columns]


def _latest_date(df: pd.DataFrame) -> Optional[str]:
    if df.empty or "time" not in df.columns:
        return None
    try:
        series = pd.to_datetime(df["time"], errors="coerce").dropna()
        if series.empty:
            return None
        return series.max().strftime("%Y-%m-%d")
    except Exception:  # noqa: BLE001
        return None


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _fetch_one(
    url: str,
    cache_path: Path,
    required_cols: list[str],
    force_refresh: bool,
) -> OnchainDataResult:
    """
    Single-asset fetch with cache/fallback logic.
    Does NOT raise — always returns OnchainDataResult.
    """
    warnings: list[str] = []
    fetched_at = _now_utc()

    # ── Step 1: try remote if force_refresh or no cache ───────────────────
    df: Optional[pd.DataFrame] = None
    status = SOURCE_STATUS_UNAVAILABLE

    if force_refresh or not cache_path.exists():
        raw = _fetch_remote(url)
        if raw is not None:
            df = _parse_csv_text(raw)
            if df is not None:
                status = SOURCE_STATUS_LIVE
                _save_cache(cache_path, df)
            else:
                warnings.append(f"Remote CSV parse failed for {url}.")

    # ── Step 2: use cache if not yet resolved ──────────────────────────────
    if df is None and not force_refresh and cache_path.exists():
        df = _load_cache(cache_path)
        if df is not None:
            status = SOURCE_STATUS_CACHED

    # ── Step 3: fallback after failed remote refresh ───────────────────────
    if df is None and status == SOURCE_STATUS_UNAVAILABLE and cache_path.exists():
        df = _load_cache(cache_path)
        if df is not None:
            status = SOURCE_STATUS_FALLBACK
            warnings.append(f"Remote unreachable; using cached data from {cache_path.name}.")

    # ── Step 4: truly unavailable ─────────────────────────────────────────
    if df is None:
        warnings.append(f"No data available (remote + cache) for {cache_path.name}.")
        return OnchainDataResult(
            df=pd.DataFrame(),
            source_status=SOURCE_STATUS_UNAVAILABLE,
            missing_columns=required_cols,
            latest_date=None,
            fetched_at=fetched_at,
            warnings=warnings,
        )

    # ── Column validation ─────────────────────────────────────────────────
    missing = _check_missing(df, required_cols)
    if missing:
        warnings.append(f"Missing columns in {cache_path.name}: {missing}")
        if status == SOURCE_STATUS_LIVE:
            status = SOURCE_STATUS_PARTIAL

    return OnchainDataResult(
        df=df,
        source_status=status,
        missing_columns=missing,
        latest_date=_latest_date(df),
        fetched_at=fetched_at,
        warnings=warnings,
    )


def load_btc_onchain(force_refresh: bool = False) -> OnchainDataResult:
    """Load BTC Coin Metrics CSV with cache/fallback."""
    _ensure_cache_dir()
    return _fetch_one(_BTC_URL, _BTC_CACHE, _BTC_REQUIRED_COLS, force_refresh)


def load_usdt_onchain(force_refresh: bool = False) -> OnchainDataResult:
    """Load USDT Coin Metrics CSV with cache/fallback."""
    _ensure_cache_dir()
    return _fetch_one(_USDT_URL, _USDT_CACHE, _STABLE_REQUIRED_COLS, force_refresh)


def load_usdc_onchain(force_refresh: bool = False) -> OnchainDataResult:
    """Load USDC Coin Metrics CSV with cache/fallback."""
    _ensure_cache_dir()
    return _fetch_one(_USDC_URL, _USDC_CACHE, _STABLE_REQUIRED_COLS, force_refresh)


def load_all_onchain(force_refresh: bool = False) -> dict[str, OnchainDataResult]:
    """
    Load BTC + USDT + USDC in one call.
    Returns dict with keys: 'btc', 'usdt', 'usdc'.
    Never raises.
    """
    return {
        "btc":  load_btc_onchain(force_refresh=force_refresh),
        "usdt": load_usdt_onchain(force_refresh=force_refresh),
        "usdc": load_usdc_onchain(force_refresh=force_refresh),
    }
