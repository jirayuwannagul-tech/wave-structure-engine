import inspect

import analysis.pivot_detector
import analysis.swing_builder
import analysis.wave_detector
import analysis.corrective_detector
import analysis.rule_validator
import analysis.fibonacci_engine


def test_no_duplicate_public_function_names():
    modules = [
        analysis.pivot_detector,
        analysis.swing_builder,
        analysis.wave_detector,
        analysis.corrective_detector,
        analysis.rule_validator,
        analysis.fibonacci_engine,
    ]

    seen = set()

    for module in modules:
        for name, obj in inspect.getmembers(module):
            if not inspect.isfunction(obj):
                continue
            if obj.__module__ != module.__name__:
                continue
            if name.startswith("_"):
                continue

            assert name not in seen, f"Duplicate public function detected: {name}"
            seen.add(name)