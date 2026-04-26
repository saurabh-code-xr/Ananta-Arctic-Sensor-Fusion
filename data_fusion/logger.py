"""
Logging setup for the data_fusion package.

Call setup_logging() once at application start.
Each module then gets its own named logger via get_logger().
"""

import logging
import os
import sys

_SETUP_DONE = False


def setup_logging(
    level: str = "INFO",
    log_to_file: bool = False,
    log_file: str = "logs/fusion.log",
) -> None:
    """
    Configure root logger for the data_fusion namespace.
    Safe to call multiple times — only sets up once.
    """
    global _SETUP_DONE
    if _SETUP_DONE:
        return

    root = logging.getLogger("data_fusion")
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s — %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(fmt)
    root.addHandler(console)

    if log_to_file:
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        fh = logging.FileHandler(log_file)
        fh.setFormatter(fmt)
        root.addHandler(fh)
        root.info("Logging to file: %s", log_file)

    _SETUP_DONE = True


def get_logger(name: str) -> logging.Logger:
    """Return a named logger under the data_fusion namespace."""
    return logging.getLogger(f"data_fusion.{name}")
