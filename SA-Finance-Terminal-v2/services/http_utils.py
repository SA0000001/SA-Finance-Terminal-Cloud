from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import requests

LOGGER = logging.getLogger("sa_finance_terminal.data")
if not LOGGER.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    LOGGER.addHandler(handler)
LOGGER.setLevel(logging.INFO)


@dataclass
class FetchResponse:
    payload: object
    latency_ms: float


class FetchError(RuntimeError):
    def __init__(self, source: str, message: str, latency_ms: float | None = None):
        super().__init__(message)
        self.source = source
        self.latency_ms = latency_ms


def _latency_ms(start_time: float) -> float:
    return (time.perf_counter() - start_time) * 1000


def safe_fetch_json(source: str, url: str, *, timeout: int = 10, headers: dict | None = None) -> FetchResponse:
    session = requests.Session()
    session.trust_env = False
    started = time.perf_counter()
    try:
        response = session.get(url, headers=headers, timeout=timeout)
        response.raise_for_status()
        payload = response.json()
        return FetchResponse(payload=payload, latency_ms=_latency_ms(started))
    except requests.Timeout as exc:
        latency = _latency_ms(started)
        LOGGER.warning("%s timed out after %.0f ms", source, latency)
        raise FetchError(source, f"Timeout: {exc}", latency) from exc
    except requests.HTTPError as exc:
        latency = _latency_ms(started)
        LOGGER.warning("%s returned HTTP error after %.0f ms: %s", source, latency, exc)
        raise FetchError(source, f"HTTP error: {exc}", latency) from exc
    except requests.ConnectionError as exc:
        latency = _latency_ms(started)
        LOGGER.warning("%s connection error after %.0f ms: %s", source, latency, exc)
        raise FetchError(source, f"Connection error: {exc}", latency) from exc
    except requests.RequestException as exc:
        latency = _latency_ms(started)
        LOGGER.warning("%s request error after %.0f ms: %s", source, latency, exc)
        raise FetchError(source, f"Request error: {exc}", latency) from exc
    except ValueError as exc:
        latency = _latency_ms(started)
        LOGGER.warning("%s returned invalid JSON after %.0f ms: %s", source, latency, exc)
        raise FetchError(source, f"Invalid JSON: {exc}", latency) from exc
    finally:
        session.close()


def safe_fetch_text(
    source: str, url: str, *, timeout: int = 10, headers: dict | None = None, accept: str | None = None
) -> FetchResponse:
    session = requests.Session()
    session.trust_env = False
    request_headers = dict(headers or {})
    if accept:
        request_headers["Accept"] = accept

    started = time.perf_counter()
    try:
        response = session.get(url, headers=request_headers or None, timeout=timeout)
        response.raise_for_status()
        return FetchResponse(payload=response.text, latency_ms=_latency_ms(started))
    except requests.Timeout as exc:
        latency = _latency_ms(started)
        LOGGER.warning("%s timed out after %.0f ms", source, latency)
        raise FetchError(source, f"Timeout: {exc}", latency) from exc
    except requests.HTTPError as exc:
        latency = _latency_ms(started)
        LOGGER.warning("%s returned HTTP error after %.0f ms: %s", source, latency, exc)
        raise FetchError(source, f"HTTP error: {exc}", latency) from exc
    except requests.ConnectionError as exc:
        latency = _latency_ms(started)
        LOGGER.warning("%s connection error after %.0f ms: %s", source, latency, exc)
        raise FetchError(source, f"Connection error: {exc}", latency) from exc
    except requests.RequestException as exc:
        latency = _latency_ms(started)
        LOGGER.warning("%s request error after %.0f ms: %s", source, latency, exc)
        raise FetchError(source, f"Request error: {exc}", latency) from exc
    finally:
        session.close()
