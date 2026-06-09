"""Intraday refresh of TODAY's (in-progress UTC day) Core Models data.

Unlike scripts/model_provider_daily.py (which finalizes UTC *yesterday* with a
full-history scrape), this targets UTC *today* and uses the fast "latest bars
only" scrape so it can run cheaply every hour. The numbers it produces are
NOT settled — today's UTC day is still accumulating — so the dashboard/report
must label them as provisional ("截至 HH:MM").

Steps (mirrors the daily pipeline but today-only + fast):
  2.   Core Model Usage (Activity API; includes today's partial total)
  3.1  Price&Uptime today tab — only scraped if missing (prices are ~stable intraday)
  3.2  Provider Usage for today — fast latest-bar scrape
  agg  Core Model Provider workbook + Dashboard HTML (current ISO week)
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.core_models_dashboard import generate_core_models_dashboard
from pipeline.core_models_provider import generate_core_models_provider_excel
from pipeline.core_models_usage import generate_core_models_usage_excel
from pipeline.logger import get_logger
from pipeline.model_provider_price_uptime import (
    generate_price_uptime_workbooks,
    list_missing_snapshot_pairs,
    parse_snapshot_date,
)
from pipeline.model_provider_usage import generate_usage_workbooks

logger = get_logger()

# Only hover the rightmost few bars (today + a small cushion) instead of all ~90.
INTRADAY_LATEST_N = 3


def utc_today(now: datetime | None = None) -> date:
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.astimezone(timezone.utc).date()


def iso_week_start(target_date: date) -> date:
    return target_date - timedelta(days=target_date.weekday())


def run_intraday(target_date: date | None = None, *, latest_n: int = INTRADAY_LATEST_N) -> int:
    day = target_date or utc_today()
    week_start = iso_week_start(day)
    logger.info("Intraday refresh start: date=%s week_start=%s latest_n=%s", day, week_start, latest_n)

    try:
        logger.info("Step 2: Core Model Usage (Activity API) for week %s", week_start.isoformat())
        generate_core_models_usage_excel(week_start)
    except Exception:
        logger.exception("Intraday Step 2 (usage activity) failed")
        return 1

    try:
        missing_today = [
            pair for pair in list_missing_snapshot_pairs(week_start, through_date=day) if pair[1] == day
        ]
        if missing_today:
            logger.info(
                "Price&Uptime today tab missing for %d model(s); scraping prices once",
                len(missing_today),
            )
            generate_price_uptime_workbooks(week_start, day)
        else:
            logger.info("Price&Uptime today tab already present; skipping price scrape")
    except Exception:
        logger.exception("Intraday Step 3.1 (price&uptime) failed")
        return 1

    try:
        logger.info("Step 3.2: fast Provider Usage scrape for %s (latest_n=%s)", day.isoformat(), latest_n)
        generate_usage_workbooks(week_start, [day], latest_n=latest_n, skip_noncore_fallback=True)
    except Exception:
        logger.exception("Intraday Step 3.2 (provider usage) failed")
        return 1

    try:
        generate_core_models_provider_excel(week_start)
        generate_core_models_dashboard(week_start)
    except Exception:
        logger.exception("Intraday aggregate/dashboard rebuild failed")
        return 1

    # Publish to the public Netlify site (non-fatal; self-skips without a token).
    if _deploy_enabled():
        try:
            from scripts.deploy_dashboard import maybe_deploy_dashboard
            maybe_deploy_dashboard()
        except Exception:
            logger.exception("Public deploy step crashed (ignored)")

    logger.info("Intraday refresh done: date=%s week_start=%s", day.isoformat(), week_start.isoformat())
    return 0


def _deploy_enabled() -> bool:
    val = (os.getenv("DEPLOY_NETLIFY") or "").strip().lower()
    return val not in {"0", "false", "no", "off"}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Intraday (hourly) refresh of today's Core Models data.")
    parser.add_argument(
        "--date",
        default=None,
        help="Target UTC date (YYYY-MM-DD). Defaults to today in UTC.",
    )
    parser.add_argument(
        "--latest-n",
        type=int,
        default=INTRADAY_LATEST_N,
        help=f"How many rightmost chart bars to hover per provider. Default: {INTRADAY_LATEST_N}.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    target_date = parse_snapshot_date(args.date) if args.date else None
    raise SystemExit(run_intraday(target_date, latest_n=max(1, int(args.latest_n))))


if __name__ == "__main__":
    main()
