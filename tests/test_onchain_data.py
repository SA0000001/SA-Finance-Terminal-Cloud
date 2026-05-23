"""
tests/test_onchain_data.py
Deterministic unit tests for services/onchain_data.py
Uses monkeypatching to avoid real network calls.
"""
from __future__ import annotations

import csv
import io
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from services.onchain_data import (
    SOURCE_STATUS_CACHED,
    SOURCE_STATUS_FALLBACK,
    SOURCE_STATUS_LIVE,
    SOURCE_STATUS_PARTIAL,
    SOURCE_STATUS_UNAVAILABLE,
    _BTC_REQUIRED_COLS,
    _STABLE_REQUIRED_COLS,
    _fetch_one,
    load_btc_onchain,
    load_usdc_onchain,
    load_usdt_onchain,
)

# ─── Helpers ──────────────────────────────────────────────────────────────────

def _make_csv(cols: list[str], n: int = 5) -> str:
    """Generate a minimal CSV string with given columns."""
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=cols)
    writer.writeheader()
    for i in range(n):
        row = {c: (f"2024-01-{i+1:02d}" if c == "time" else str(float(i * 1000))) for c in cols}
        writer.writerow(row)
    return buf.getvalue()


def _write_cache(path: Path, cols: list[str], n: int = 3) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_make_csv(cols, n), encoding="utf-8")


# ─── 1. Missing columns does not crash ────────────────────────────────────────

def test_csv_missing_columns_does_not_crash(tmp_path):
    """CSV with only 'time' should not crash; missing_columns should be populated."""
    csv_text = _make_csv(["time"])
    cache = tmp_path / "coinmetrics_btc.csv"

    with (
        patch("services.onchain_data._fetch_remote", return_value=csv_text),
        patch("services.onchain_data._BTC_CACHE", cache),
        patch("services.onchain_data._CACHE_DIR", tmp_path),
    ):
        result = _fetch_one(
            "http://fake.url/btc.csv",
            cache,
            _BTC_REQUIRED_COLS,
            force_refresh=True,
        )

    assert result.source_status in (SOURCE_STATUS_LIVE, SOURCE_STATUS_PARTIAL)
    # All required cols except 'time' should be missing
    expected_missing = [c for c in _BTC_REQUIRED_COLS if c != "time"]
    for col in expected_missing:
        assert col in result.missing_columns, f"{col} should be in missing_columns"
    assert not result.df.empty


# ─── 2. Cache fallback when remote fails ─────────────────────────────────────

def test_cache_fallback_logic(tmp_path):
    """When remote fails but cache exists, should return fallback status."""
    cache = tmp_path / "coinmetrics_btc.csv"
    _write_cache(cache, _BTC_REQUIRED_COLS, n=5)

    with (
        patch("services.onchain_data._fetch_remote", return_value=None),  # remote fails
        patch("services.onchain_data._BTC_CACHE", cache),
        patch("services.onchain_data._CACHE_DIR", tmp_path),
    ):
        result = _fetch_one(
            "http://fake.url/btc.csv",
            cache,
            _BTC_REQUIRED_COLS,
            force_refresh=True,  # tries remote first
        )

    assert result.source_status == SOURCE_STATUS_FALLBACK
    assert not result.df.empty


# ─── 3. Unavailable when no cache and remote fails ───────────────────────────

def test_unavailable_without_cache(tmp_path):
    """Remote fails + no cache → source_status='unavailable', empty df, no crash."""
    cache = tmp_path / "coinmetrics_btc_nonexistent.csv"
    # cache file does NOT exist

    with (
        patch("services.onchain_data._fetch_remote", return_value=None),
        patch("services.onchain_data._BTC_CACHE", cache),
        patch("services.onchain_data._CACHE_DIR", tmp_path),
    ):
        result = _fetch_one(
            "http://fake.url/btc.csv",
            cache,
            _BTC_REQUIRED_COLS,
            force_refresh=False,
        )

    assert result.source_status == SOURCE_STATUS_UNAVAILABLE
    assert result.df.empty
    assert len(result.warnings) > 0


# ─── 4. Latest date generated from valid CSV ─────────────────────────────────

def test_latest_date_generated(tmp_path):
    """Valid CSV with time column should produce a non-None latest_date."""
    csv_text = _make_csv(_BTC_REQUIRED_COLS, n=10)
    cache = tmp_path / "coinmetrics_btc.csv"

    with (
        patch("services.onchain_data._fetch_remote", return_value=csv_text),
        patch("services.onchain_data._BTC_CACHE", cache),
        patch("services.onchain_data._CACHE_DIR", tmp_path),
    ):
        result = _fetch_one(
            "http://fake.url/btc.csv",
            cache,
            _BTC_REQUIRED_COLS,
            force_refresh=True,
        )

    assert result.latest_date is not None
    # Should be a date string in YYYY-MM-DD format
    assert len(result.latest_date) == 10
    assert result.latest_date.startswith("2024")


# ─── 5. force_refresh uses remote when available ─────────────────────────────

def test_force_refresh_uses_remote_when_available(tmp_path):
    """force_refresh=True should attempt remote fetch and return live status."""
    csv_text = _make_csv(_BTC_REQUIRED_COLS, n=5)
    cache = tmp_path / "coinmetrics_btc.csv"

    remote_called = {"called": False}
    original_csv = csv_text

    def mock_remote(url, timeout=30):
        remote_called["called"] = True
        return original_csv

    with (
        patch("services.onchain_data._fetch_remote", side_effect=mock_remote),
        patch("services.onchain_data._BTC_CACHE", cache),
        patch("services.onchain_data._CACHE_DIR", tmp_path),
    ):
        result = _fetch_one(
            "http://fake.url/btc.csv",
            cache,
            _BTC_REQUIRED_COLS,
            force_refresh=True,
        )

    assert remote_called["called"], "Remote fetch should have been called"
    assert result.source_status in (SOURCE_STATUS_LIVE, SOURCE_STATUS_PARTIAL)


# ─── 6. Cache hit (no remote) ────────────────────────────────────────────────

def test_cache_hit_does_not_call_remote(tmp_path):
    """When cache exists and force_refresh=False, remote should not be called."""
    cache = tmp_path / "coinmetrics_btc.csv"
    _write_cache(cache, _BTC_REQUIRED_COLS, n=3)

    remote_called = {"called": False}

    def mock_remote(url, timeout=30):
        remote_called["called"] = True
        return None

    with (
        patch("services.onchain_data._fetch_remote", side_effect=mock_remote),
        patch("services.onchain_data._BTC_CACHE", cache),
        patch("services.onchain_data._CACHE_DIR", tmp_path),
    ):
        result = _fetch_one(
            "http://fake.url/btc.csv",
            cache,
            _BTC_REQUIRED_COLS,
            force_refresh=False,
        )

    assert not remote_called["called"], "Remote should not be called when cache exists"
    assert result.source_status == SOURCE_STATUS_CACHED
    assert not result.df.empty


# ─── 7. load_all_onchain smoke ───────────────────────────────────────────────

def test_load_all_onchain_does_not_raise(tmp_path):
    """load_all_onchain must not raise even if remote fails and no cache."""
    from services.onchain_data import load_all_onchain

    with (
        patch("services.onchain_data._fetch_remote", return_value=None),
        patch("services.onchain_data._BTC_CACHE", tmp_path / "btc.csv"),
        patch("services.onchain_data._USDT_CACHE", tmp_path / "usdt.csv"),
        patch("services.onchain_data._USDC_CACHE", tmp_path / "usdc.csv"),
        patch("services.onchain_data._CACHE_DIR", tmp_path),
    ):
        results = load_all_onchain(force_refresh=False)

    assert "btc" in results
    assert "usdt" in results
    assert "usdc" in results
    # All should be unavailable
    for key, r in results.items():
        assert r.source_status == SOURCE_STATUS_UNAVAILABLE


# ─── 8. Stable cols validated ────────────────────────────────────────────────

def test_stable_csv_missing_cap_column(tmp_path):
    """USDT CSV missing CapMrktCurUSD → missing_columns populated."""
    csv_text = _make_csv(["time"], n=3)  # no CapMrktCurUSD
    cache = tmp_path / "coinmetrics_usdt.csv"

    with (
        patch("services.onchain_data._fetch_remote", return_value=csv_text),
        patch("services.onchain_data._USDT_CACHE", cache),
        patch("services.onchain_data._CACHE_DIR", tmp_path),
    ):
        result = _fetch_one(
            "http://fake.url/usdt.csv",
            cache,
            _STABLE_REQUIRED_COLS,
            force_refresh=True,
        )

    assert "CapMrktCurUSD" in result.missing_columns
