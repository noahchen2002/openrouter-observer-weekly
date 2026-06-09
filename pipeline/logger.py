"""Unified logging for the OpenRouter observer pipeline."""

from __future__ import annotations

import logging
import sys


LOGGER_NAME = "openrouter_pipeline"


class SecretFilter(logging.Filter):
    SECRET_MARKERS = ("OPENROUTER_API_KEY", "api_key", "authorization", "bearer ")

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage().lower()
        return not any(marker.lower() in message for marker in self.SECRET_MARKERS)


def get_logger(name: str = LOGGER_NAME) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(logging.INFO)
        handler.addFilter(SecretFilter())
        handler.setFormatter(
            logging.Formatter(
                fmt="%(asctime)s | %(levelname)s | %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger
