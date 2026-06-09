"""Push the daily Core Models card to a Feishu group via the app (bot) identity.

Used by GitHub Actions (reuses the existing "Noah 飞书 CLI" app credential). Sends
the SiliconFlow-focused interactive card to FEISHU_CHAT_ID. In alert mode (env
FEISHU_ALERT set) it sends a plain-text failure notice instead.

Env:
  FEISHU_APP_ID / FEISHU_APP_SECRET   required — app credential (-> tenant token)
  FEISHU_CHAT_ID                      required — target group chat_id
  DASHBOARD_URL                       optional — button link (default: public site)
  REPORT_DATE                         optional — YYYY-MM-DD; default = UTC yesterday
  REPORT_PROVISIONAL                  optional — "1" to mark data not-yet-settled
  FEISHU_ALERT                        optional — if set, send this text instead of the card
"""

from __future__ import annotations

import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.ai_analysis import generate_ai_analysis
from pipeline.competitor_summary import build_competitor_card
from pipeline.logger import get_logger
from scripts.feishu_notify import send_interactive_card, send_text_message

logger = get_logger()

DEFAULT_DASHBOARD_URL = "https://noahchen2002.github.io/openrouter-observer-weekly/"


def utc_yesterday() -> date:
    return datetime.now(timezone.utc).date() - timedelta(days=1)


def main() -> None:
    chat_id = (os.getenv("FEISHU_CHAT_ID") or "").strip()
    if not chat_id:
        logger.error("FEISHU_CHAT_ID not set")
        raise SystemExit(2)

    rid_type = (os.getenv("FEISHU_RECEIVE_ID_TYPE") or "").strip()
    if not rid_type:
        rid_type = "open_id" if chat_id.startswith("ou_") else "chat_id"

    alert = (os.getenv("FEISHU_ALERT") or "").strip()
    if alert:
        send_text_message(chat_id=chat_id, text=alert, receive_id_type=rid_type)
        logger.info("Feishu alert sent to %s", chat_id)
        return

    url = (os.getenv("DASHBOARD_URL") or DEFAULT_DASHBOARD_URL).strip()
    provisional = (os.getenv("REPORT_PROVISIONAL") or "").strip().lower() in {"1", "true", "yes", "on"}
    rd = (os.getenv("REPORT_DATE") or "").strip()
    day = date.fromisoformat(rd) if rd else utc_yesterday()
    as_of = datetime.now().strftime("%m-%d %H:%M")

    # Competitor-focused card + AI analysis (AI self-skips if no SILICONFLOW_API_KEY).
    ai_text = generate_ai_analysis(day)
    card = build_competitor_card(day, url, as_of=as_of, provisional=provisional, ai_text=ai_text)
    resp = send_interactive_card(chat_id=chat_id, card=card, receive_id_type=rid_type)
    msg_id = (((resp.get("data") or {}).get("message_id")) or "").strip()
    logger.info("Feishu competitor card sent for %s (message_id=%s, ai=%s)", day.isoformat(), msg_id, bool(ai_text))


if __name__ == "__main__":
    main()
