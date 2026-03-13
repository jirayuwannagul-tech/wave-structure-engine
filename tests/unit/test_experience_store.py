import json

from storage.experience_store import (
    build_experience_payload,
    clear_experience_store_cache,
    get_pattern_edge,
    save_experience_store,
)


def test_build_experience_payload_aggregates_by_symbol_timeframe_pattern_and_side():
    payload = build_experience_payload(
        [
            {
                "symbol": "SOLUSDT",
                "timeframe": "4H",
                "pattern": "RUNNING_FLAT",
                "side": "SHORT",
                "reward_r": 1.2,
            },
            {
                "symbol": "SOLUSDT",
                "timeframe": "4H",
                "pattern": "RUNNING_FLAT",
                "side": "SHORT",
                "reward_r": -0.4,
            },
        ]
    )

    item = payload["patterns"]["SOLUSDT|4H|RUNNING_FLAT|SHORT"]
    assert item == {
        "sample_count": 2,
        "win_count": 1,
        "loss_count": 1,
        "win_rate": 0.5,
        "avg_r": 0.4,
        "total_r": 0.8,
    }


def test_get_pattern_edge_reads_saved_payload(tmp_path, monkeypatch):
    path = tmp_path / "experience_store.json"
    monkeypatch.setenv("EXPERIENCE_STORE_PATH", str(path))
    clear_experience_store_cache()

    save_experience_store(
        {
            "version": 1,
            "patterns": {
                "ETHUSDT|4H|IMPULSE|LONG": {
                    "sample_count": 6,
                    "win_count": 3,
                    "loss_count": 3,
                    "win_rate": 0.5,
                    "avg_r": 0.21,
                    "total_r": 1.26,
                }
            },
        }
    )

    edge = get_pattern_edge("ETHUSDT", "4H", "IMPULSE", "LONG")

    assert edge is not None
    assert edge.sample_count == 6
    assert edge.positive is True
    assert edge.negative is False
    assert json.loads(path.read_text())["patterns"]["ETHUSDT|4H|IMPULSE|LONG"]["avg_r"] == 0.21

