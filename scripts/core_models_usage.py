"""Generate weekly Core Model Usage Excel for models in config/core_models.json.

Usage:
    python3 -m scripts.core_models_usage --week 2026-05-18
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.core_models_usage import generate_core_models_usage_excel
from pipeline.model_provider_price_uptime import load_monitored_models, parse_week_start


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate Core Model Usage Excel")
    parser.add_argument(
        "--week",
        required=True,
        help="Target ISO week Monday, YYYY-MM-DD.",
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Path to core models JSON list (default: config/core_models.json).",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    week_start = parse_week_start(args.week)
    models = None
    if args.config:
        models = load_monitored_models(Path(args.config))
    path = generate_core_models_usage_excel(week_start, models=models)
    print(f"Saved Core Model Usage Excel: {path}")


if __name__ == "__main__":
    main()
