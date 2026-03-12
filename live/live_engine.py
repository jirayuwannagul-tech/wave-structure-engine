from __future__ import annotations

import pandas as pd

from live.live_wave_state import LiveWaveState
from live.scenario_monitor import ScenarioMonitor
from live.wave_recount_engine import recount_wave


class LiveWaveEngine:

    def __init__(self):
        self.state = LiveWaveState()
        self.monitor = ScenarioMonitor()

    def process_dataframe(self, df: pd.DataFrame):

        result = recount_wave(df)

        if result is None:
            return None

        structure = result["structure"]
        bias = result["bias"]

        price = float(df.iloc[-1]["close"])

        self.state.update(structure, bias, price)

        self.monitor.update(bias)

        return self.state.snapshot()