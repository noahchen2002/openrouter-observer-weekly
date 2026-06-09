"""Build Core Models HTML dashboard from weekly Usage / Provider / Income Excel files.

Usage:
    python3 -m scripts.build_core_models_dashboard --week 2026-05-18
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.core_models_dashboard import (
    dashboard_output_path,
    generate_core_models_dashboard,
)
from pipeline.model_provider_price_uptime import parse_week_start


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build Core Models HTML dashboard from weekly Excel outputs",
    )
    parser.add_argument(
        "--week",
        required=True,
        help="Target ISO week Monday, YYYY-MM-DD.",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output directory (default: data/output/Core_Models).",
    )
    parser.add_argument("--usage", default=None, help="Path to Core Model Usage xlsx.")
    parser.add_argument("--provider", default=None, help="Path to Core Model Provider xlsx.")
    parser.add_argument("--income", default=None, help="Path to Core Model Income xlsx.")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    week_start = parse_week_start(args.week)
    output_dir = Path(args.output) if args.output else None

    path = generate_core_models_dashboard(
        week_start,
        output_dir=output_dir,
        usage_path=Path(args.usage) if args.usage else None,
        provider_path=Path(args.provider) if args.provider else None,
        income_path=Path(args.income) if args.income else None,
    )
    print(f"Saved Core Models dashboard: {path}")
    if output_dir is None:
        print(f"  (default path: {dashboard_output_path(week_start)})")


if __name__ == "__main__":
    main()
