from __future__ import annotations


class LiveWaveState:

    def __init__(self):
        self.structure = None
        self.bias = None
        self.last_price = None

    def update(self, structure: str, bias: str, price: float):
        self.structure = structure
        self.bias = bias
        self.last_price = price

    def snapshot(self):
        return {
            "structure": self.structure,
            "bias": self.bias,
            "price": self.last_price,
        }