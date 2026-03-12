import requests


def get_last_price(symbol: str = "BTCUSDT") -> float:
    url = "https://fapi.binance.com/fapi/v1/ticker/price"
    params = {"symbol": symbol}
    r = requests.get(url, params=params, timeout=10)
    r.raise_for_status()
    data = r.json()
    return float(data["price"])