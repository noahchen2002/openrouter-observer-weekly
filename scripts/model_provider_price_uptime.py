"""Generate weekly model provider Price&Uptime monitoring workbooks.

Usage:
    python -m scripts.model_provider_price_uptime --week 2026-05-18
    python -m scripts.model_provider_price_uptime --week 2026-05-18 --date 2026-05-18
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.model_provider_price_uptime import (
    generate_price_uptime_workbooks,
    parse_snapshot_date,
    parse_week_start,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate model provider Price&Uptime workbooks")
    parser.add_argument(
        "--week",
        required=True,
        help="Target ISO week Monday, YYYY-MM-DD. This decides the weekly workbook.",
    )
    parser.add_argument(
        "--date",
        default=None,
        help="Snapshot date for the daily tab, YYYY-MM-DD. Defaults to today.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    week_start = parse_week_start(args.week)
    snapshot_date = parse_snapshot_date(args.date)
    paths = generate_price_uptime_workbooks(week_start, snapshot_date)
    for path in paths:
        print(f"Saved Price&Uptime workbook: {path}")


if __name__ == "__main__":
    main()
