from __future__ import annotations


class ScenarioMonitor:

    def __init__(self):
        self.active_bias = None

    def update(self, bias: str):
        if bias != self.active_bias:
            print("Scenario change ->", bias)

        self.active_bias = bias

    def get_bias(self):
        return self.active_bias