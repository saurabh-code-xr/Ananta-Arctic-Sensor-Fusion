"""
Tests for input validation and error handling in data_fusion.utils.
"""

import pytest
from data_fusion.utils import validate_sensor_reading, validate_sensor_list, freshness_factor


# ── validate_sensor_reading ───────────────────────────────────────────────────

def test_valid_reading_returns_no_errors():
    reading = {"sensor": "A", "detected": True, "quality": 0.85, "latency": 120}
    assert validate_sensor_reading(reading) == []


def test_missing_required_field():
    reading = {"sensor": "A", "detected": True, "quality": 0.85}  # missing latency
    errors = validate_sensor_reading(reading)
    assert any("latency" in e for e in errors)


def test_missing_multiple_fields():
    reading = {"sensor": "A"}
    errors = validate_sensor_reading(reading)
    assert len(errors) > 0


def test_quality_out_of_range_high():
    reading = {"sensor": "A", "detected": True, "quality": 1.5, "latency": 100}
    errors = validate_sensor_reading(reading)
    assert any("quality" in e for e in errors)


def test_quality_out_of_range_low():
    reading = {"sensor": "A", "detected": True, "quality": -0.1, "latency": 100}
    errors = validate_sensor_reading(reading)
    assert any("quality" in e for e in errors)


def test_quality_at_boundary_values_valid():
    for q in (0.0, 1.0):
        reading = {"sensor": "A", "detected": True, "quality": q, "latency": 100}
        assert validate_sensor_reading(reading) == []


def test_negative_latency():
    reading = {"sensor": "A", "detected": True, "quality": 0.8, "latency": -10}
    errors = validate_sensor_reading(reading)
    assert any("latency" in e for e in errors)


def test_non_numeric_quality():
    reading = {"sensor": "A", "detected": True, "quality": "high", "latency": 100}
    errors = validate_sensor_reading(reading)
    assert any("quality" in e for e in errors)


def test_non_numeric_latency():
    reading = {"sensor": "A", "detected": True, "quality": 0.8, "latency": "fast"}
    errors = validate_sensor_reading(reading)
    assert any("latency" in e for e in errors)


def test_empty_sensor_name():
    reading = {"sensor": "", "detected": True, "quality": 0.8, "latency": 100}
    errors = validate_sensor_reading(reading)
    assert any("sensor" in e for e in errors)


# ── validate_sensor_list ──────────────────────────────────────────────────────

def test_valid_list_does_not_raise():
    data = [
        {"sensor": "A", "detected": True, "quality": 0.85, "latency": 120},
        {"sensor": "B", "detected": False, "quality": 0.70, "latency": 200},
    ]
    validate_sensor_list(data)  # should not raise


def test_non_list_raises_value_error():
    with pytest.raises(ValueError, match="must be a list"):
        validate_sensor_list({"sensor": "A"})


def test_empty_list_does_not_raise():
    validate_sensor_list([])  # empty is valid — fusion_engine handles empty case


# ── freshness_factor ──────────────────────────────────────────────────────────

def test_freshness_zero_latency():
    assert freshness_factor(0) == 1.0


def test_freshness_exactly_at_bracket_boundary():
    assert freshness_factor(100) == 1.0
    assert freshness_factor(200) == 0.9
    assert freshness_factor(300) == 0.75


def test_freshness_above_all_brackets():
    assert freshness_factor(99999) == 0.2
    assert freshness_factor(100000) == 0.2


def test_freshness_negative_latency_clamped():
    # Should not crash — negative latency treated as 0
    result = freshness_factor(-50)
    assert result == 1.0


def test_freshness_respects_custom_config():
    config = {
        "fusion": {
            "freshness_brackets": [
                {"max_latency_ms": 50, "factor": 1.0},
                {"max_latency_ms": 99999, "factor": 0.5},
            ]
        }
    }
    assert freshness_factor(50, config=config) == 1.0
    assert freshness_factor(100, config=config) == 0.5


# ── CSV adapter parsing ───────────────────────────────────────────────────────

def test_csv_adapter_parses_valid_file(tmp_path):
    from data_fusion.adapters.csv_adapter import CSVAdapter
    csv_file = tmp_path / "sensors.csv"
    csv_file.write_text(
        "timestamp,sensor_id,detected,quality,latency_ms\n"
        "2024-01-01T00:00:00,A,True,0.85,120\n"
        "2024-01-01T00:00:00,B,False,0.70,200\n"
        "2024-01-01T00:01:00,A,True,0.80,130\n"
    )
    adapter = CSVAdapter(str(csv_file))
    steps = adapter.fetch()
    assert len(steps) == 2                 # 2 unique timestamps
    assert len(steps[0]) == 2             # 2 sensors at first timestamp
    assert steps[0][0]["sensor"] in ("A", "B")
    assert isinstance(steps[0][0]["detected"], bool)
    assert isinstance(steps[0][0]["quality"], float)
    assert isinstance(steps[0][0]["latency"], float)


def test_csv_adapter_handles_missing_file():
    from data_fusion.adapters.csv_adapter import CSVAdapter
    adapter = CSVAdapter("/nonexistent/sensors.csv")
    steps = adapter.fetch()
    assert steps == []


def test_csv_adapter_handles_empty_file(tmp_path):
    from data_fusion.adapters.csv_adapter import CSVAdapter
    empty = tmp_path / "empty.csv"
    empty.write_text("timestamp,sensor_id,detected,quality,latency_ms\n")
    adapter = CSVAdapter(str(empty))
    steps = adapter.fetch()
    assert steps == []
