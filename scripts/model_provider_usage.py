"""Generate weekly model provider Usage monitoring workbooks.

Usage:
    python -m scripts.model_provider_usage --week 2026-05-18
    python -m scripts.model_provider_usage --week 2026-05-18 --date 2026-05-18
    python -m scripts.model_provider_usage --week 2026-05-18 --all-week
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.model_provider_price_uptime import parse_snapshot_date, parse_week_start
from pipeline.model_provider_usage import generate_usage_workbooks, week_dates


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate model provider Usage workbooks")
    parser.add_argument(
        "--week",
        required=True,
        help="Target ISO week Monday, YYYY-MM-DD. This decides the weekly workbook.",
    )
    parser.add_argument(
        "--date",
        default=None,
        help="Snapshot date for the daily tab, YYYY-MM-DD. Defaults to today in single-day mode.",
    )
    parser.add_argument(
        "--all-week",
        action="store_true",
        help="Generate all 7 daily tabs for the target week.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    week_start = parse_week_start(args.week)
    target_dates = week_dates(week_start) if args.all_week else [parse_snapshot_date(args.date)]
    paths = generate_usage_workbooks(week_start, target_dates)
    for path in paths:
        print(f"Updated Price&Uptime workbook with Usage data: {path}")


if __name__ == "__main__":
    main()
