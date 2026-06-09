"""Local 09:00 push: wait for the 08:05 scrape to finish, verify, then send the
AI competitor card to the Feishu group via lark-cli (bot identity).

Designed to run as a launchd job on the always-on local "server". Unlike the
cloud path (scripts.feishu_app_push, which talks to Feishu OpenAPI with an app
secret in env), this sends through lark-cli `--as bot`, so the app secret stays
in the macOS keychain and never lands in a plist on disk.

Flow:
  1. Resolve the expected UTC snapshot date (yesterday).
  2. Wait (poll) for the 08:05 pipeline's "finished" marker, then verify the
     day's artifacts exist (reuses scripts.model_provider_daily_check).
  3. Optional auto-repair when AUTO_REPAIR=1 and a data-quality issue is found.
  4. On success: run AI analysis + build the competitor card, send via lark-cli.
     On failure: send a plain-text alert instead.

Every run is logged (success included) to data/debug/launchd/local_daily_push.log
to avoid the silent-success trap this project hit before.

Env:
  FEISHU_CHAT_ID         required — target group chat_id (oc_...)
  DASHBOARD_URL          optional — button link (default: public Netlify site)
  CHECK_WAIT_MINUTES     optional — how long to wait for the scrape (default 45)
  AUTO_REPAIR            optional — "1" to auto-repair data-quality anomalies
  REPORT_DATE            optional — YYYY-MM-DD; default = UTC yesterday
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.ai_analysis import generate_ai_analysis
from pipeline.competitor_summary import build_competitor_card
from pipeline.logger import get_logger
from scripts.model_provider_daily_check import (
    CheckResult,
    _apply_repair,
    check_daily_run,
    utc_yesterday,
)
from scripts.send_daily_card import send_card

logger = get_logger()

DEFAULT_DASHBOARD_URL = "https://noahchen2002.github.io/openrouter-observer-weekly/"
LAUNCHD_DIR = PROJECT_ROOT / "data" / "debug" / "launchd"
LOG_PATH = LAUNCHD_DIR / "local_daily_push.log"


def _log_line(message: str) -> None:
    """Append a timestamped line to the dedicated push log AND the app logger.

    The project's earlier failure mode was a silently successful run with no
    trace, so we record every outcome here regardless of success/failure.
    """
    LAUNCHD_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(f"[{stamp}] {message}\n")
    logger.info(message)


def _chat_id() -> str:
    chat_id = (os.getenv("FEISHU_CHAT_ID") or "").strip()
    if not chat_id:
        _log_line("FAILED: FEISHU_CHAT_ID not set")
        raise SystemExit(2)
    return chat_id


def _receive_id_type(chat_id: str) -> str:
    rid = (os.getenv("FEISHU_RECEIVE_ID_TYPE") or "").strip()
    if rid:
        return rid
    return "open_id" if chat_id.startswith("ou_") else "chat_id"


def _wait_minutes() -> float:
    raw = (os.getenv("CHECK_WAIT_MINUTES") or "").strip()
    if not raw:
        return 45.0
    try:
        return max(0.0, float(raw))
    except ValueError:
        return 45.0


def _truthy(name: str) -> bool:
    return (os.getenv(name) or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def _send_alert(chat_id: str, rid_type: str, text: str) -> dict:
    """Send a plain-text alert to the group via lark-cli (bot identity)."""
    content = json.dumps({"text": text}, ensure_ascii=False)
    data = json.dumps(
        {"receive_id": chat_id, "msg_type": "text", "content": content},
        ensure_ascii=False,
    )
    env = {**os.environ, "LARK_CLI_NO_PROXY": "1"}
    proc = subprocess.run(
        [
            "lark-cli", "api", "POST", "/open-apis/im/v1/messages",
            "--params", json.dumps({"receive_id_type": rid_type}),
            "--data", data, "--as", "bot",
        ],
        capture_output=True, text=True, env=env,
    )
    try:
        return json.loads(proc.stdout.strip())
    except Exception:
        return {"_returncode": proc.returncode, "_stdout": proc.stdout[:500], "_stderr": proc.stderr[:500]}


def _resp_ok(resp: dict) -> bool:
    return isinstance(resp, dict) and resp.get("code") == 0


def main() -> None:
    chat_id = _chat_id()
    rid_type = _receive_id_type(chat_id)
    url = (os.getenv("DASHBOARD_URL") or DEFAULT_DASHBOARD_URL).strip()

    rd = (os.getenv("REPORT_DATE") or "").strip()
    day = date.fromisoformat(rd) if rd else utc_yesterday()

    _log_line(f"START local push for UTC date={day.isoformat()} (wait≤{_wait_minutes():.0f}min)")

    result: CheckResult = check_daily_run(
        expected_date=day,
        out_log=LAUNCHD_DIR / "daily_scrape.out.log",
        err_log=LAUNCHD_DIR / "daily_scrape.err.log",
        require_income=False,
        wait_minutes=_wait_minutes(),
    )
    result = _apply_repair(expected_date=day, result=result, repair_enabled=_truthy("AUTO_REPAIR"))

    if not result.ok:
        alert = (
            "⚠️ OpenRouter 监控日报今晨未就绪（本机）。\n"
            f"UTC date={day.isoformat()}，退出码 {result.exit_code}。\n"
            "请检查 launchd 抓取任务与 data/debug/launchd 日志。看板数据可能未更新。"
        )
        resp = _send_alert(chat_id, rid_type, alert)
        _log_line(f"FAILED (exit={result.exit_code}); alert sent ok={_resp_ok(resp)} resp={json.dumps(resp, ensure_ascii=False)[:300]}")
        raise SystemExit(result.exit_code)

    as_of = datetime.now().strftime("%m-%d %H:%M")
    ai_text = generate_ai_analysis(day)
    card = build_competitor_card(day, url, as_of=as_of, provisional=False, ai_text=ai_text)
    resp = send_card(card, chat_id, rid_type)

    if _resp_ok(resp):
        msg_id = (((resp.get("data") or {}).get("message_id")) or "").strip()
        _log_line(f"OK card sent for {day.isoformat()} (ai={bool(ai_text)}, message_id={msg_id})")
    else:
        _log_line(f"FAILED to send card for {day.isoformat()}: {json.dumps(resp, ensure_ascii=False)[:400]}")
        raise SystemExit(5)


if __name__ == "__main__":
    main()
