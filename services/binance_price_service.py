from __future__ import annotations

import time

import requests


_FAPI_URL = "https://fapi.binance.com/fapi/v1/ticker/price"
_MAX_RETRIES = 3
_RETRY_DELAY = 2.0  # seconds, doubles on each attempt


def get_last_price(symbol: str = "BTCUSDT") -> float:
    """Fetch the latest mark price from Binance Futures.

    Retries up to _MAX_RETRIES times with exponential backoff on network errors
    or non-2xx responses.

    Raises:
        requests.RequestException: if all retries are exhausted.
        ValueError: if the response payload is missing the 'price' field.
    """
    params = {"symbol": symbol}
    delay = _RETRY_DELAY

    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            r = requests.get(_FAPI_URL, params=params, timeout=10)
            r.raise_for_status()
            data = r.json()
            return float(data["price"])
        except (requests.RequestException, KeyError, ValueError) as exc:
            if attempt == _MAX_RETRIES:
                raise
            print(f"[binance_price_service] attempt {attempt} failed ({exc}), retrying in {delay}s…")
            time.sleep(delay)
            delay *= 2
