from __future__ import annotations

import json
import websocket


class LivePriceStream:

    def __init__(self, symbol: str = "btcusdt"):
        self.symbol = symbol.lower()
        self.price = None

    def _on_message(self, ws, message):
        data = json.loads(message)
        self.price = float(data["p"])

    def _on_error(self, ws, error):
        print("WS error:", error)

    def _on_close(self, ws, close_status_code, close_msg):
        print("WS closed")

    def start(self):
        url = f"wss://fstream.binance.com/ws/{self.symbol}@trade"

        ws = websocket.WebSocketApp(
            url,
            on_message=self._on_message,
            on_error=self._on_error,
            on_close=self._on_close,
        )

        ws.run_forever()