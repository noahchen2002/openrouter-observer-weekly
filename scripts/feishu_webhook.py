"""Post a Core Models card to a Feishu group via a custom-bot webhook.

Used by GitHub Actions (and anywhere without the bot App Secret): a Feishu group
"custom bot" gives a webhook URL that accepts interactive cards with no app
credential. Supports the optional signature-verification secret.

Env:
  FEISHU_WEBHOOK         required — the custom bot webhook URL
  FEISHU_WEBHOOK_SECRET  optional — signing secret if "签名校验" is enabled
  DASHBOARD_URL          optional — button link (default: public Netlify site)
  REPORT_DATE            optional — YYYY-MM-DD; default = UTC yesterday
  REPORT_PROVISIONAL     optional — "1" to mark data not-yet-settled
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import sys
import time
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.logger import get_logger
from pipeline.sf_summary import build_sf_card

logger = get_logger()

DEFAULT_DASHBOARD_URL = "https://or-core-monitor-noah.netlify.app"


def _gen_sign(secret: str, timestamp: int) -> str:
    string_to_sign = f"{timestamp}\n{secret}"
    digest = hmac.new(string_to_sign.encode("utf-8"), b"", hashlib.sha256).digest()
    return base64.b64encode(digest).decode("utf-8")


def post_card(webhook: str, card: dict, *, secret: str | None = None, timeout: float = 20.0) -> dict:
    payload: dict = {"msg_type": "interactive", "card": card}
    if secret:
        ts = int(time.time())
        payload["timestamp"] = str(ts)
        payload["sign"] = _gen_sign(secret, ts)
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(webhook, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8")
    try:
        return json.loads(body)
    except Exception:
        return {"_raw": body}


def utc_yesterday() -> date:
    return datetime.now(timezone.utc).date() - timedelta(days=1)


def post_text(webhook: str, text: str, *, secret: str | None = None, timeout: float = 20.0) -> dict:
    payload: dict = {"msg_type": "text", "content": {"text": text}}
    if secret:
        ts = int(time.time())
        payload["timestamp"] = str(ts)
        payload["sign"] = _gen_sign(secret, ts)
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(webhook, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8")
    try:
        return json.loads(body)
    except Exception:
        return {"_raw": body}


def main() -> None:
    webhook = (os.getenv("FEISHU_WEBHOOK") or "").strip()
    if not webhook:
        logger.error("FEISHU_WEBHOOK not set; cannot push to group")
        raise SystemExit(2)
    secret = (os.getenv("FEISHU_WEBHOOK_SECRET") or "").strip() or None

    # Alert mode: send a plain-text failure notice instead of the data card.
    alert = (os.getenv("FEISHU_ALERT") or "").strip()
    if alert:
        resp = post_text(webhook, alert, secret=secret)
        logger.info("Feishu alert sent")
        print(json.dumps(resp, ensure_ascii=False)[:300])
        return
    url = (os.getenv("DASHBOARD_URL") or DEFAULT_DASHBOARD_URL).strip()
    provisional = (os.getenv("REPORT_PROVISIONAL") or "").strip().lower() in {"1", "true", "yes", "on"}
    rd = (os.getenv("REPORT_DATE") or "").strip()
    day = date.fromisoformat(rd) if rd else utc_yesterday()
    as_of = datetime.now().strftime("%m-%d %H:%M")

    card = build_sf_card(day, url, as_of=as_of, provisional=provisional)
    resp = post_card(webhook, card, secret=secret)
    code = resp.get("code", resp.get("StatusCode"))
    if code not in (0, None):
        logger.error("Feishu webhook returned non-zero: %s", json.dumps(resp, ensure_ascii=False)[:500])
        raise SystemExit(1)
    logger.info("Feishu group card sent for %s", day.isoformat())
    print(json.dumps(resp, ensure_ascii=False)[:300])


if __name__ == "__main__":
    main()
