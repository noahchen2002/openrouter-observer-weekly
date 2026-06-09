"""Unified configuration for the OpenRouter observer pipeline."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
OUTPUT_DIR = DATA_DIR / "output"
DEBUG_DIR = DATA_DIR / "debug"

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY") or None
HEADLESS = os.getenv("HEADLESS", "true").lower() in {"1", "true", "yes", "y", "on"}

RANKINGS_URL = "https://openrouter.ai/rankings"
API_BASE_URL = "https://openrouter.ai/api/v1"


def ensure_dirs() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    DEBUG_DIR.mkdir(parents=True, exist_ok=True)
