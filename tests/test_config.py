"""
Tests for data_fusion.config and data_fusion.logger.
"""

import os
import tempfile
import pytest
import yaml

from data_fusion import config as cfg_module


@pytest.fixture(autouse=True)
def reset_config():
    """Reset config singleton between tests."""
    cfg_module.reload.__doc__  # ensure module loaded
    yield
    cfg_module._CONFIG = None


def write_temp_config(data: dict) -> str:
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False)
    yaml.dump(data, f)
    f.close()
    return f.name


# ── Loading ───────────────────────────────────────────────────────────────────

def test_load_valid_config():
    path = write_temp_config({"system": {"name": "test"}, "fusion": {"detection_threshold": 0.5}})
    try:
        config = cfg_module.load(path)
        assert config["system"]["name"] == "test"
        assert config["fusion"]["detection_threshold"] == 0.5
    finally:
        os.unlink(path)


def test_load_missing_file_returns_empty_dict():
    config = cfg_module.load("/nonexistent/path/config.yaml")
    assert config == {}


def test_load_invalid_yaml_returns_empty_dict(tmp_path):
    bad_yaml = tmp_path / "bad.yaml"
    bad_yaml.write_text("{invalid: yaml: content: [}")
    config = cfg_module.load(str(bad_yaml))
    assert config == {}


def test_get_loads_on_first_call(tmp_path):
    good = tmp_path / "config.yaml"
    good.write_text("system:\n  name: auto-loaded\n")
    os.environ["FUSION_CONFIG"] = str(good)
    try:
        cfg_module._CONFIG = None
        config = cfg_module.get()
        assert config.get("system", {}).get("name") == "auto-loaded"
    finally:
        del os.environ["FUSION_CONFIG"]


def test_get_caches_after_first_load():
    cfg_module._CONFIG = {"cached": True}
    config = cfg_module.get()
    assert config == {"cached": True}


def test_reload_forces_fresh_load(tmp_path):
    f = tmp_path / "config.yaml"
    f.write_text("system:\n  name: first\n")
    cfg_module.load(str(f))
    assert cfg_module.get()["system"]["name"] == "first"

    f.write_text("system:\n  name: second\n")
    cfg_module.reload(str(f))
    assert cfg_module.get()["system"]["name"] == "second"


# ── Threshold extraction ──────────────────────────────────────────────────────

def test_confidence_thresholds_from_config():
    from data_fusion.confidence_engine import _thresholds_from_config
    config = {
        "confidence": {
            "thresholds": {
                "high": {"min_score": 0.9, "min_quality": 0.85, "max_latency_ms": 150},
                "medium": {"min_score": 0.6, "min_quality": 0.60, "max_latency_ms": 400},
            },
            "sensor_flags": {"low_quality_threshold": 0.4, "high_latency_threshold": 500},
        }
    }
    t = _thresholds_from_config(config)
    assert t["high_score"] == 0.9
    assert t["high_quality"] == 0.85
    assert t["high_latency_ceiling"] == 150
    assert t["medium_score"] == 0.6
    assert t["low_quality_threshold"] == 0.4
    assert t["high_latency_threshold"] == 500


def test_thresholds_fall_back_to_defaults_when_config_empty():
    from data_fusion.confidence_engine import _thresholds_from_config, DEFAULT_THRESHOLDS
    t = _thresholds_from_config({})
    assert t == DEFAULT_THRESHOLDS
