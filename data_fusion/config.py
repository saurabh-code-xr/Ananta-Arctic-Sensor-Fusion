"""
Configuration loader.

Loads config.yaml on first access. All modules use get() to
read tunable parameters so hardware integrators only change one file.

Override the config path via FUSION_CONFIG env var:
    FUSION_CONFIG=/path/to/custom.yaml python run_experiment.py ...
"""

import os
import yaml
from data_fusion.logger import get_logger

logger = get_logger("config")

_CONFIG: dict | None = None
_DEFAULT_PATH = "config.yaml"


def load(path: str | None = None) -> dict:
    """Load configuration from a YAML file and cache it."""
    global _CONFIG
    path = path or os.environ.get("FUSION_CONFIG", _DEFAULT_PATH)
    try:
        with open(path) as f:
            _CONFIG = yaml.safe_load(f)
        logger.info("Config loaded from %s", path)
    except FileNotFoundError:
        logger.warning("Config file not found at '%s' — using built-in defaults.", path)
        _CONFIG = {}
    except yaml.YAMLError as e:
        logger.error("Failed to parse config file '%s': %s — using defaults.", path, e)
        _CONFIG = {}
    return _CONFIG


def get() -> dict:
    """Return the loaded config, loading from disk if not yet cached."""
    if _CONFIG is None:
        load()
    return _CONFIG


def reload(path: str | None = None) -> dict:
    """Force a fresh load — useful in tests or when config changes at runtime."""
    global _CONFIG
    _CONFIG = None
    return load(path)
