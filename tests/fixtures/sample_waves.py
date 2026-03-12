from analysis.pivot_detector import Pivot


def sample_bullish_abc():
    return [
        Pivot(index=188, price=63030.0, type="L", timestamp="2026-02-28"),
        Pivot(index=192, price=74050.0, type="H", timestamp="2026-03-04"),
        Pivot(index=196, price=65618.49, type="L", timestamp="2026-03-08"),
    ]


def sample_bearish_impulse():
    return [
        Pivot(index=152, price=91224.99, type="H", timestamp="2026-01-23"),
        Pivot(index=154, price=86074.72, type="L", timestamp="2026-01-25"),
        Pivot(index=157, price=90600.0, type="H", timestamp="2026-01-28"),
        Pivot(index=166, price=60000.0, type="L", timestamp="2026-02-06"),
        Pivot(index=168, price=72271.41, type="H", timestamp="2026-02-08"),
        Pivot(index=172, price=65118.0, type="L", timestamp="2026-02-12"),
    ]