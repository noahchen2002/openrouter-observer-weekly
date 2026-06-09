"""Generate weekly Core Model Income Excel from model_income export.

Usage:
    python3 -m scripts.core_models_income --week 2026-05-11
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.core_models_income import (
    default_income_path,
    fill_core_models_income,
    output_path_for_week,
)
from pipeline.model_provider_price_uptime import load_monitored_models, parse_week_start


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate Core Model Income workbook from model_income export",
    )
    parser.add_argument(
        "--week",
        required=True,
        help="Target ISO week Monday, YYYY-MM-DD.",
    )
    parser.add_argument(
        "--income",
        default=None,
        help="Path to model_income export (default: data/input/model_income_{week}.xlsx).",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output directory (default: data/output/Core_Models).",
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
    models = load_monitored_models(Path(args.config)) if args.config else None
    income_path = Path(args.income) if args.income else default_income_path(week_start)
    output_dir = Path(args.output) if args.output else None

    path = fill_core_models_income(
        week_start,
        income_path=income_path,
        output_dir=output_dir,
        models=models,
    )
    print(f"Saved Core Model Income workbook: {path}")
    if output_dir is None:
        print(f"  (default path: {output_path_for_week(week_start)})")


if __name__ == "__main__":
    main()
