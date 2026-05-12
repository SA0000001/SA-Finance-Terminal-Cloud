from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import requests

# Retry ayarları
_RETRY_COUNT = 3          # toplam deneme sayısı
_RETRY_BACKOFF = [1, 3]   # 1. retry öncesi 1s, 2. retry öncesi 3s bekle
_RETRYABLE_STATUS = {429, 500, 502, 503, 504}  # retry yapılacak HTTP kodları

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
    last_exc: Exception | None = None

    for attempt in range(_RETRY_COUNT):
        if attempt > 0:
            wait = _RETRY_BACKOFF[min(attempt - 1, len(_RETRY_BACKOFF) - 1)]
            LOGGER.info("%s retry %d/%d after %ds", source, attempt, _RETRY_COUNT - 1, wait)
            time.sleep(wait)
        try:
            response = session.get(url, headers=headers, timeout=timeout)
            if response.status_code in _RETRYABLE_STATUS and attempt < _RETRY_COUNT - 1:
                LOGGER.warning("%s HTTP %d, will retry", source, response.status_code)
                last_exc = requests.HTTPError(response=response)
                continue
            response.raise_for_status()
            payload = response.json()
            if attempt > 0:
                LOGGER.info("%s succeeded on attempt %d", source, attempt + 1)
            return FetchResponse(payload=payload, latency_ms=_latency_ms(started))
        except requests.Timeout as exc:
            LOGGER.warning("%s timed out (attempt %d)", source, attempt + 1)
            last_exc = exc
        except requests.HTTPError as exc:
            LOGGER.warning("%s HTTP error (attempt %d): %s", source, attempt + 1, exc)
            last_exc = exc
            if exc.response is not None and exc.response.status_code not in _RETRYABLE_STATUS:
                break  # 404 gibi kalıcı hatalar için retry yapma
        except requests.ConnectionError as exc:
            LOGGER.warning("%s connection error (attempt %d): %s", source, attempt + 1, exc)
            last_exc = exc
        except requests.RequestException as exc:
            LOGGER.warning("%s request error (attempt %d): %s", source, attempt + 1, exc)
            last_exc = exc
            break
        except ValueError as exc:
            LOGGER.warning("%s invalid JSON (attempt %d): %s", source, attempt + 1, exc)
            raise FetchError(source, f"Invalid JSON: {exc}", _latency_ms(started)) from exc

    session.close()
    latency = _latency_ms(started)
    LOGGER.error("%s failed after %d attempts (%.0f ms)", source, _RETRY_COUNT, latency)
    raise FetchError(source, f"Failed after {_RETRY_COUNT} attempts: {last_exc}", latency) from last_exc


def safe_fetch_text(
    source: str, url: str, *, timeout: int = 10, headers: dict | None = None, accept: str | None = None
) -> FetchResponse:
    session = requests.Session()
    session.trust_env = False
    request_headers = dict(headers or {})
    if accept:
        request_headers["Accept"] = accept

    started = time.perf_counter()
    last_exc: Exception | None = None

    for attempt in range(_RETRY_COUNT):
        if attempt > 0:
            wait = _RETRY_BACKOFF[min(attempt - 1, len(_RETRY_BACKOFF) - 1)]
            LOGGER.info("%s retry %d/%d after %ds", source, attempt, _RETRY_COUNT - 1, wait)
            time.sleep(wait)
        try:
            response = session.get(url, headers=request_headers or None, timeout=timeout)
            if response.status_code in _RETRYABLE_STATUS and attempt < _RETRY_COUNT - 1:
                LOGGER.warning("%s HTTP %d, will retry", source, response.status_code)
                last_exc = requests.HTTPError(response=response)
                continue
            response.raise_for_status()
            if attempt > 0:
                LOGGER.info("%s succeeded on attempt %d", source, attempt + 1)
            return FetchResponse(payload=response.text, latency_ms=_latency_ms(started))
        except requests.Timeout as exc:
            LOGGER.warning("%s timed out (attempt %d)", source, attempt + 1)
            last_exc = exc
        except requests.HTTPError as exc:
            LOGGER.warning("%s HTTP error (attempt %d): %s", source, attempt + 1, exc)
            last_exc = exc
            if exc.response is not None and exc.response.status_code not in _RETRYABLE_STATUS:
                break
        except requests.ConnectionError as exc:
            LOGGER.warning("%s connection error (attempt %d): %s", source, attempt + 1, exc)
            last_exc = exc
        except requests.RequestException as exc:
            LOGGER.warning("%s request error (attempt %d): %s", source, attempt + 1, exc)
            last_exc = exc
            break

    session.close()
    latency = _latency_ms(started)
    LOGGER.error("%s failed after %d attempts (%.0f ms)", source, _RETRY_COUNT, latency)
    raise FetchError(source, f"Failed after {_RETRY_COUNT} attempts: {last_exc}", latency) from last_exc
