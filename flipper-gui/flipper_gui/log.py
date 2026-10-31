"""Structured, configured logger for flipper_gui."""

from __future__ import annotations

import logging
import os
import sys

DEFAULT_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
LOG_ENV = "FLIPPER_GUI_LOG_LEVEL"


def get_logger(name: str, level: str | None = None) -> logging.Logger:
    """Return a named logger. Configures a single StreamHandler on first call."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        _configure(level)
    return logger


def _configure(level: str | None = None) -> None:
    if level is None:
        level = os.getenv(LOG_ENV, "INFO")
    numeric = getattr(logging, level.upper(), logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(DEFAULT_FORMAT))
    root = logging.getLogger("flipper_gui")
    root.setLevel(numeric)
    for h in list(root.handlers):
        root.removeHandler(h)
    root.addHandler(handler)
    root.propagate = False
