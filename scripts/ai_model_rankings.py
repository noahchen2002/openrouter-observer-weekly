"""Generate the weekly AI Model Rankings Excel workbook.

Usage:
    python -m scripts.ai_model_rankings
    python -m scripts.ai_model_rankings --week 2026-05-04
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.model_ranking_weekly import (
    generate_ai_model_rankings_excel,
    parse_week_start,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate AI Model Rankings Excel")
    parser.add_argument(
        "--week",
        type=str,
        default=None,
        help="Data week start date, YYYY-MM-DD Monday. Defaults to the previous complete ISO week.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    week_start = parse_week_start(args.week)
    path = generate_ai_model_rankings_excel(week_start)
    print(f"Saved AI Model Rankings Excel: {path}")


if __name__ == "__main__":
    main()
