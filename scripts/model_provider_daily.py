"""Daily pipeline for Core Models monitoring (README sections 2-5).

By default uses UTC yesterday as the snapshot date and the ISO week containing
that date. Runs README sections in order: 2, 3.1, 3.2, Provider aggregate, 4, 5.
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
from pipeline.core_models_income import (
    default_income_path,
    generate_core_models_income_excel,
    output_path_for_week as income_output_path_for_week,
)
from pipeline.core_models_provider import generate_core_models_provider_excel
from pipeline.core_models_usage import generate_core_models_usage_excel
from pipeline.logger import get_logger
from pipeline.model_provider_price_uptime import (
    generate_price_uptime_workbook_for_model,
    generate_price_uptime_workbooks,
    list_missing_snapshot_pairs,
    parse_snapshot_date,
)
from pipeline.model_provider_usage import (
    generate_usage_workbooks,
    list_incomplete_usage_snapshot_dates,
)

logger = get_logger()


def _daily_latest_n() -> int | None:
    """How many right-most chart bars to hover per provider (None = full history).

    Default 8 covers the current ISO week (yesterday + same-week backfill) and keeps
    each provider scrape to a few seconds. Override with DAILY_LATEST_N; 0/empty
    means hover the full ~90-bar history (slow; only for special backfills).
    """
    raw = (os.getenv("DAILY_LATEST_N") or "").strip()
    if raw == "":
        return 8
    try:
        n = int(raw)
    except ValueError:
        return 8
    return n if n > 0 else None


def utc_yesterday(now: datetime | None = None) -> date:
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.astimezone(timezone.utc).date() - timedelta(days=1)


def iso_week_start(target_date: date) -> date:
    return target_date - timedelta(days=target_date.weekday())


def run_daily_pipeline(target_date: date | None = None) -> int:
    """Run README sections 2-5 for UTC yesterday (or target_date). Returns exit code."""
    day = target_date or utc_yesterday()
    week_start = iso_week_start(day)

    logger.info(
        "Starting daily Core Models pipeline: date=%s week_start=%s",
        day.isoformat(),
        week_start.isoformat(),
    )

    try:
        logger.info("Step 2: Core Model Usage for week %s", week_start.isoformat())
        usage_path = generate_core_models_usage_excel(week_start)
        logger.info("Saved Core Model Usage Excel: %s", usage_path)
        print(f"Saved Core Model Usage Excel: {usage_path}")
    except Exception:
        logger.exception("Step 2 Core Model Usage failed")
        return 1

    try:
        logger.info("Step 3.1: Price&Uptime for %s", day.isoformat())
        price_paths = generate_price_uptime_workbooks(week_start, day)
        for path in price_paths:
            logger.info("Saved Price&Uptime workbook: %s", path)
            print(f"Saved Price&Uptime workbook: {path}")
        backfill_pairs = [
            pair
            for pair in list_missing_snapshot_pairs(week_start, through_date=day)
            if pair[1] != day
        ]
        if backfill_pairs:
            logger.info(
                "Step 3.1 backfill: %d missing day tab(s) in week through %s",
                len(backfill_pairs),
                day.isoformat(),
            )
        for monitored_model, snap_date in backfill_pairs:
            logger.info(
                "Step 3.1 backfill: %s for %s",
                monitored_model.model_slug,
                snap_date.isoformat(),
            )
            path = generate_price_uptime_workbook_for_model(monitored_model, week_start, snap_date)
            logger.info("Saved Price&Uptime workbook: %s", path)
            print(f"Saved Price&Uptime workbook (backfill): {path}")
    except Exception:
        logger.exception("Step 3.1 failed")
        return 1

    try:
        backfill_days = list_incomplete_usage_snapshot_dates(week_start, through_date=day)
        target_days = sorted({day, *backfill_days})
        if backfill_days:
            logger.info(
                "Step 3.2 backfill: also filling incomplete usage for %s",
                ", ".join(d.isoformat() for d in backfill_days),
            )
        # Only the recent days are ever targeted (yesterday + same-week backfill),
        # so hovering all ~90 history bars per provider is wasteful and too slow on
        # CI runners. DAILY_LATEST_N caps how many right-most bars to hover; default
        # 8 covers the current ISO week. Set to 0/empty to hover the full history.
        latest_n = _daily_latest_n()
        logger.info(
            "Step 3.2: Provider Usage for %s (latest_n=%s)",
            ", ".join(d.isoformat() for d in target_days),
            latest_n,
        )
        usage_paths = generate_usage_workbooks(week_start, target_days, latest_n=latest_n)
        for path in usage_paths:
            logger.info("Updated Price&Uptime workbook with Usage: %s", path)
            print(f"Updated Price&Uptime workbook with Usage data: {path}")
    except Exception:
        logger.exception("Step 3.2 failed")
        return 1

    try:
        logger.info("Step Provider aggregate for week %s", week_start.isoformat())
        provider_path = generate_core_models_provider_excel(week_start)
        logger.info("Saved Core Model Provider workbook: %s", provider_path)
        print(f"Saved Core Model Provider workbook: {provider_path}")
    except Exception:
        logger.exception("Provider aggregate failed")
        return 1

    income_input = default_income_path(week_start)
    income_output = income_output_path_for_week(week_start)
    if income_input.exists():
        try:
            logger.info("Step 4: Core Model Income from %s", income_input)
            income_path = generate_core_models_income_excel(week_start, income_path=income_input)
            logger.info("Saved Core Model Income Excel: %s", income_path)
            print(f"Saved Core Model Income workbook: {income_path}")
        except Exception:
            logger.exception("Step 4 Core Model Income failed")
            return 1
    else:
        logger.warning(
            "Income input missing (%s); skipping Income regeneration, using existing workbook if any",
            income_input,
        )
        if income_output.exists():
            logger.info("Using existing Core Model Income workbook: %s", income_output)
        else:
            logger.warning(
                "No existing Core Model Income workbook at %s; dashboard may fail",
                income_output,
            )

    try:
        logger.info("Step 5: Core Models Dashboard for week %s", week_start.isoformat())
        dashboard_path = generate_core_models_dashboard(week_start)
        logger.info("Saved Core Models dashboard: %s", dashboard_path)
        print(f"Saved Core Models dashboard: {dashboard_path}")
    except Exception:
        logger.exception("Step 5 dashboard failed")
        return 1

    # Step 6: per-model 429 (rate-limit) counts from the provider dashboard, via the
    # always-on debug Chrome over CDP (non-fatal; the card self-degrades if the
    # browser is down or the Clerk session expired — then re-login in that Chrome).
    try:
        from pipeline.openrouter_status import (
            AuthExpired,
            BrowserUnavailable,
            save_status_snapshot,
            send_maintenance_alert,
        )
        counts = save_status_snapshot(day)
        logger.info("Step 6: saved status(429/502/504) snapshot for %s: %s", day.isoformat(), counts)
        print(f"Saved status snapshot for {day.isoformat()}: {counts}")
    except AuthExpired:
        logger.warning("Step 6 status: dashboard session expired — re-login in the debug Chrome (port 9222)")
        send_maintenance_alert(
            "⚠️ OpenRouter 错误码抓取失败（429/502/504）：登录会话已过期。\n"
            "请在本机常开的 OpenRouter Chrome 窗口里重新登录一次（它一直开着）。\n"
            f"在修复前，每日日报将不含错误码统计。数据日期 {day.isoformat()}。"
        )
    except BrowserUnavailable:
        logger.warning("Step 6 status: debug Chrome not reachable on CDP 9222 — is the keep-alive browser running?")
        send_maintenance_alert(
            "⚠️ OpenRouter 错误码抓取失败（429/502/504）：常驻调试 Chrome 未运行（CDP 9222 不可达）。\n"
            "请检查 launchd 任务 com.openrouter-observer.cdp-browser。\n"
            f"在修复前，每日日报将不含错误码统计。数据日期 {day.isoformat()}。"
        )
    except Exception:
        logger.exception("Step 6 status fetch crashed (ignored)")

    # Publish the password-encrypted dashboard to GitHub Pages (non-fatal; self-skips
    # without a token, or when DEPLOY_GHPAGES is falsey). github.io is the most
    # China-reachable host; Netlify was retired (credit-blocked + GFW IP issues).
    if (os.getenv("DEPLOY_GHPAGES") or "1").strip().lower() not in {"0", "false", "no", "off"}:
        try:
            from scripts.deploy_github_pages import maybe_deploy_github_pages
            maybe_deploy_github_pages()
        except Exception:
            logger.exception("GitHub Pages deploy step crashed (ignored)")

    # Legacy Netlify deploy: off by default; only runs if DEPLOY_NETLIFY is truthy.
    if (os.getenv("DEPLOY_NETLIFY") or "0").strip().lower() not in {"0", "false", "no", "off"}:
        try:
            from scripts.deploy_dashboard import maybe_deploy_dashboard
            maybe_deploy_dashboard()
        except Exception:
            logger.exception("Public deploy step crashed (ignored)")

    logger.info(
        "Finished daily Core Models pipeline: date=%s week_start=%s",
        day.isoformat(),
        week_start.isoformat(),
    )
    return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Daily Core Models pipeline (README sections 2-5, UTC yesterday)",
    )
    parser.add_argument(
        "--date",
        default=None,
        help="Target UTC data date, YYYY-MM-DD. Defaults to yesterday in UTC.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    target_date = parse_snapshot_date(args.date) if args.date else None
    raise SystemExit(run_daily_pipeline(target_date))


if __name__ == "__main__":
    main()
