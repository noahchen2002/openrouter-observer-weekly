"""Aggregate weekly Price&Uptime&Usage workbooks into Core Model Provider Excel.

Usage:
    python3 -m scripts.core_models_provider --week 2026-05-18
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.core_models_provider import (
    generate_core_models_provider_excel,
    output_path_for_week,
)
from pipeline.model_provider_price_uptime import load_monitored_models, parse_week_start


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Aggregate Price&Uptime&Usage weekly workbooks into Core Model Provider Excel",
    )
    parser.add_argument(
        "--week",
        required=True,
        help="Target ISO week Monday, YYYY-MM-DD.",
    )
    parser.add_argument(
        "--input",
        default=None,
        help="Price&Uptime&Usage root directory (default: data/output/Price&Uptime&Usage).",
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
    input_dir = Path(args.input) if args.input else None
    output_dir = Path(args.output) if args.output else None

    path = generate_core_models_provider_excel(
        week_start,
        models=models,
        price_uptime_dir=input_dir,
        output_dir=output_dir,
    )
    print(f"Saved Core Model Provider workbook: {path}")
    if output_dir is None:
        print(f"  (default path: {output_path_for_week(week_start)})")


if __name__ == "__main__":
    main()
