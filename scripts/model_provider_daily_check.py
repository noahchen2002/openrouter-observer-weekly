"""Post-run checker for the daily Core Models launchd job.

This script is designed to run as a separate launchd job after the main
`scripts/model_provider_daily.py` job. It verifies that the pipeline finished
for the expected UTC snapshot date and that key output artifacts exist.
When data-quality anomalies are detected, it attempts auto-repair and only
notifies on repair failure or remaining issues.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.core_models_dashboard import dashboard_output_path
from pipeline.core_models_income import output_path_for_week as income_output_path_for_week
from pipeline.core_models_provider import output_path_for_week as provider_output_path_for_week
from pipeline.core_models_usage import output_path_for_week as usage_output_path_for_week
from pipeline.daily_summary import build_daily_summary_text
from pipeline.data_quality import DataQualityReport, check_data_quality
from pipeline.data_repair import RepairReport, repair_data_quality
from pipeline.logger import get_logger
from scripts.feishu_notify import FeishuNotifyError, send_html_file, send_text_message

logger = get_logger()


def utc_yesterday(now: datetime | None = None) -> date:
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.astimezone(timezone.utc).date() - timedelta(days=1)


def iso_week_start(target_date: date) -> date:
    return target_date - timedelta(days=target_date.weekday())


def _read_text(path: Path, *, max_bytes: int = 2_000_000) -> str:
    if not path.exists():
        return ""
    data = path.read_bytes()
    if len(data) > max_bytes:
        data = data[-max_bytes:]
    return data.decode("utf-8", errors="replace")


def _tail_lines(text: str, limit: int = 80) -> str:
    lines = text.splitlines()
    if len(lines) <= limit:
        return "\n".join(lines)
    return "\n".join(lines[-limit:])


@dataclass(frozen=True)
class CheckResult:
    ok: bool
    message: str
    exit_code: int
    quality: DataQualityReport | None = None
    repair: RepairReport | None = None


def _wait_for_finished_marker(out_log: Path, marker: str, wait_minutes: float) -> str:
    """Poll the stdout log until the pipeline's finished marker appears.

    The check job fires at a fixed time (09:00), but the main scrape pipeline can
    run 30-60+ minutes. Rather than crying failure when it merely hasn't finished
    yet, wait up to wait_minutes (polling every 30s) so the daily report still goes
    out once the pipeline completes, only a few minutes late at worst.
    """
    out_text = _read_text(out_log)
    if marker in out_text or wait_minutes <= 0:
        return out_text
    deadline_polls = int(wait_minutes * 2)  # 30s per poll
    logger.info("Pipeline not finished yet; waiting up to %.0f min for completion", wait_minutes)
    for _ in range(deadline_polls):
        time.sleep(30)
        out_text = _read_text(out_log)
        if marker in out_text:
            logger.info("Pipeline finished marker detected; proceeding with check")
            break
    return out_text


def check_daily_run(
    *,
    expected_date: date,
    out_log: Path,
    err_log: Path,
    require_income: bool,
    include_quality: bool = True,
    wait_minutes: float = 0.0,
) -> CheckResult:
    week_start = iso_week_start(expected_date)

    finished_marker = f"Finished daily Core Models pipeline: date={expected_date.isoformat()} week_start={week_start.isoformat()}"
    out_text = _wait_for_finished_marker(out_log, finished_marker, wait_minutes)
    err_text = _read_text(err_log)

    if finished_marker not in out_text:
        detail = []
        if err_text.strip():
            detail.append("stderr tail:\n" + _tail_lines(err_text))
        if out_text.strip():
            detail.append("stdout tail:\n" + _tail_lines(out_text))
        body = "\n\n".join(detail) if detail else "(no launchd logs found yet)"
        return CheckResult(
            ok=False,
            exit_code=2,
            message=(
                "Daily pipeline did NOT finish successfully.\n"
                f"Expected marker:\n{finished_marker}\n\n"
                f"Logs:\n{body}\n"
            ),
        )

    expected_paths: list[tuple[str, Path, bool]] = [
        ("Usage workbook", usage_output_path_for_week(week_start), True),
        ("Provider workbook", provider_output_path_for_week(week_start), True),
        ("Income workbook", income_output_path_for_week(week_start), require_income),
        ("Dashboard HTML", dashboard_output_path(week_start), True),
    ]

    missing_required: list[str] = []
    missing_optional: list[str] = []
    for label, path, required in expected_paths:
        if not path.exists():
            (missing_required if required else missing_optional).append(f"{label}: {path}")

    if missing_required:
        msg = (
            "Daily pipeline finished marker is present, but required artifacts are missing.\n"
            f"Expected UTC date={expected_date.isoformat()} week_start={week_start.isoformat()}\n\n"
            "Missing required:\n- "
            + "\n- ".join(missing_required)
        )
        if missing_optional:
            msg += "\n\nMissing optional:\n- " + "\n- ".join(missing_optional)
        return CheckResult(ok=False, exit_code=3, message=msg + "\n")

    msg = (
        "Daily pipeline check OK.\n"
        f"UTC date={expected_date.isoformat()} week_start={week_start.isoformat()}\n"
        + "\n".join([f"- {label}: {path}" for label, path, _ in expected_paths if path.exists()])
        + "\n"
    )
    quality: DataQualityReport | None = None
    if include_quality:
        quality = check_data_quality(week_start, through_date=expected_date)
        if not quality.ok:
            return CheckResult(
                ok=False,
                exit_code=4,
                message=msg + quality.format_summary(),
                quality=quality,
            )
        msg += quality.format_summary()
    return CheckResult(ok=True, exit_code=0, message=msg, quality=quality)


def _apply_repair(
    *,
    expected_date: date,
    result: CheckResult,
    repair_enabled: bool,
) -> CheckResult:
    week_start = iso_week_start(expected_date)
    quality = result.quality
    if not repair_enabled:
        return result
    if quality is None or quality.ok:
        return result
    if result.exit_code not in {4}:
        return result

    logger.info(
        "Data quality anomalies detected (%d issue(s)); starting auto-repair",
        len(quality.issues),
    )
    repair_report = repair_data_quality(week_start, through_date=expected_date, quality=quality)
    quality_after = repair_report.quality_after
    if quality_after is None:
        return result

    base_msg = result.message.split("Data quality anomalies detected.")[0].rstrip() + "\n"
    if repair_report.ok:
        msg = (
            base_msg
            + f"Auto-repaired {repair_report.issues_fixed} data quality issue(s).\n"
            + quality_after.format_summary()
        )
        return CheckResult(ok=True, exit_code=0, message=msg, quality=quality_after, repair=repair_report)

    msg = base_msg + repair_report.format_summary()
    return CheckResult(
        ok=False,
        exit_code=4,
        message=msg,
        quality=quality_after,
        repair=repair_report,
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check whether daily Core Models launchd job finished.")
    parser.add_argument(
        "--date",
        default=None,
        help="Expected UTC snapshot date (YYYY-MM-DD). Defaults to yesterday in UTC.",
    )
    parser.add_argument(
        "--out-log",
        default=str(PROJECT_ROOT / "data" / "debug" / "launchd" / "model_provider_daily.out.log"),
        help="Path to the main launchd stdout log.",
    )
    parser.add_argument(
        "--err-log",
        default=str(PROJECT_ROOT / "data" / "debug" / "launchd" / "model_provider_daily.err.log"),
        help="Path to the main launchd stderr log.",
    )
    parser.add_argument(
        "--require-income",
        action="store_true",
        help="Fail if income workbook is missing (default: optional).",
    )
    parser.add_argument(
        "--chat-id",
        default=None,
        help="Feishu group chat_id to notify. Defaults to env FEISHU_CHAT_ID.",
    )
    parser.add_argument(
        "--notify",
        action="store_true",
        help="Send Feishu notification (default off unless env FEISHU_NOTIFY=1/true).",
    )
    repair_group = parser.add_mutually_exclusive_group()
    repair_group.add_argument(
        "--repair",
        action="store_true",
        help="Attempt auto-repair when data quality anomalies are detected.",
    )
    repair_group.add_argument(
        "--no-repair",
        action="store_true",
        help="Skip auto-repair even when AUTO_REPAIR=1 is set.",
    )
    parser.add_argument(
        "--wait-minutes",
        type=float,
        default=None,
        help=(
            "If the pipeline hasn't finished yet, wait up to this many minutes "
            "(polling every 30s) before checking. Defaults to env CHECK_WAIT_MINUTES, "
            "else 30."
        ),
    )
    return parser.parse_args()


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


def _truthy_env(name: str) -> bool:
    value = (os.getenv(name) or "").strip().lower()
    return value in {"1", "true", "yes", "y", "on"}


def _notify_enabled(args: argparse.Namespace) -> bool:
    return bool(getattr(args, "notify", False)) or _truthy_env("FEISHU_NOTIFY")


def _repair_enabled(args: argparse.Namespace) -> bool:
    if getattr(args, "no_repair", False):
        return False
    if getattr(args, "repair", False):
        return True
    return _truthy_env("AUTO_REPAIR")


def _notify_chat_id(args: argparse.Namespace) -> str | None:
    return (getattr(args, "chat_id", None) or os.getenv("FEISHU_CHAT_ID") or "").strip() or None


def _wait_minutes(args: argparse.Namespace) -> float:
    cli = getattr(args, "wait_minutes", None)
    if cli is not None:
        return max(0.0, float(cli))
    env = (os.getenv("CHECK_WAIT_MINUTES") or "").strip()
    if env:
        try:
            return max(0.0, float(env))
        except ValueError:
            logger.warning("Invalid CHECK_WAIT_MINUTES=%r; falling back to default", env)
    return 30.0


def _format_feishu_text(*, expected_date: date, result: CheckResult) -> str:
    if result.ok and result.repair and result.repair.issues_fixed > 0:
        status = "✅ 已自动修复"
    elif result.ok:
        status = "✅ 成功"
    elif result.exit_code == 4:
        status = "⚠️ 数据异常"
    else:
        status = "❌ 失败"
    header = f"[CoreModels Daily] {status} | UTC date={expected_date.isoformat()}"
    if result.ok and result.repair and result.repair.issues_fixed > 0:
        header += f" | 修复 {result.repair.issues_fixed} 项"
    body = result.message.strip()
    if len(body) > 3000:
        body = body[-3000:]
    return header + "\n" + body


def _build_notification_text(*, expected_date: date, result: CheckResult) -> str:
    """Success → readable daily data digest; failure → check/alert message."""
    if not result.ok:
        return _format_feishu_text(expected_date=expected_date, result=result)

    week_start = iso_week_start(expected_date)
    try:
        text = build_daily_summary_text(week_start, expected_date)
    except Exception:
        logger.exception("Failed to build daily summary; falling back to check message")
        return _format_feishu_text(expected_date=expected_date, result=result)

    if result.repair and result.repair.issues_fixed > 0:
        text += f"\n\n（注：今晨自动修复了 {result.repair.issues_fixed} 项数据异常）"
    return text


def _send_feishu_notification(*, chat_id: str, expected_date: date, result: CheckResult) -> None:
    text = _build_notification_text(expected_date=expected_date, result=result)
    logger.info("Sending Feishu notification to chat_id=%s (ok=%s)", chat_id, result.ok)
    resp = send_text_message(chat_id=chat_id, text=text)
    msg_id = (((resp.get("data") or {}).get("message_id")) or "").strip()
    if msg_id:
        logger.info("Feishu text message sent (message_id=%s)", msg_id)

    if not result.ok:
        return

    week_start = iso_week_start(expected_date)
    html_path = dashboard_output_path(week_start)
    if not html_path.exists():
        logger.warning("Dashboard HTML missing, skip file upload: %s", html_path)
        return
    try:
        send_html_file(chat_id=chat_id, html_path=html_path)
        logger.info("Feishu HTML file sent: %s", html_path)
    except FeishuNotifyError as exc:
        logger.error("Feishu HTML file upload failed (%s): %s", html_path, exc)
        raise


def main() -> None:
    args = _parse_args()
    expected = _parse_date(args.date) if args.date else utc_yesterday()
    result = check_daily_run(
        expected_date=expected,
        out_log=Path(args.out_log),
        err_log=Path(args.err_log),
        require_income=bool(args.require_income),
        wait_minutes=_wait_minutes(args),
    )
    result = _apply_repair(
        expected_date=expected,
        result=result,
        repair_enabled=_repair_enabled(args),
    )
    if _notify_enabled(args):
        chat_id = _notify_chat_id(args)
        if not chat_id:
            logger.error("Feishu notify enabled but chat_id missing (set FEISHU_CHAT_ID or pass --chat-id).")
        else:
            try:
                _send_feishu_notification(chat_id=chat_id, expected_date=expected, result=result)
            except FeishuNotifyError as exc:
                logger.error("Feishu notification failed: %s", exc)
            except Exception:
                logger.exception("Feishu notification crashed")
    if result.ok:
        logger.info(result.message.strip())
        print(result.message)
    else:
        logger.error(result.message.strip())
        print(result.message, file=sys.stderr)
    raise SystemExit(result.exit_code)


if __name__ == "__main__":
    main()
