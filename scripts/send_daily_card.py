"""Build a Feishu interactive card from a day's Core Models data and send it.

Reuses pipeline.daily_summary for the underlying numbers, renders an interactive
card (header + per-model top providers with SiliconFlow highlighted + a button
linking to the dashboard), and sends it via lark-cli (bot identity).

Usage:
  .venv/bin/python -m scripts.send_daily_card \
      --week 2026-06-01 --date 2026-06-01 \
      --url "http://192.168.21.223:8765/..." \
      --to ou_xxx --provisional [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.daily_summary import (
    SILICONFLOW_KEYS,
    TOP_N_PROVIDERS,
    STATUS_SHOWN,
    STATUS_SKIPPED,
    STATUS_MISSING,
    collect_daily_models,
    _fmt_share,
    _siliconflow_row,
)
from pipeline.logger import get_logger
from pipeline.utils import normalize_for_match

logger = get_logger()


def _is_sf(provider: str) -> bool:
    return normalize_for_match(provider) in SILICONFLOW_KEYS


def build_card(week_start: date, snapshot_date: date, dashboard_url: str | None, *, provisional: bool, as_of: str) -> dict:
    models = collect_daily_models(week_start, snapshot_date)

    if provisional:
        title = "📊 OpenRouter 核心模型 · 今日实时"
        note = f"⚠️ 截至 {as_of} · 今日数据**未结算**（仍在累计，仅供参考）"
        template = "orange"
    else:
        title = f"📊 OpenRouter 核心模型日报 · {snapshot_date.isoformat()}"
        note = f"数据日期 {snapshot_date.isoformat()} · 已结算"
        template = "blue"

    elements: list[dict] = [{"tag": "markdown", "content": note}, {"tag": "hr"}]

    any_data = False
    for model in models:
        shown = sorted(
            model.shown,
            key=lambda r: (r.uptake_tokens if r.uptake_tokens is not None else -1),
            reverse=True,
        )
        sf = _siliconflow_row(model)
        if not shown and sf is None:
            continue
        any_data = True

        lines = [f"**{model.display_name}**"]
        sf_in_top = False
        for rank, r in enumerate(shown[:TOP_N_PROVIDERS], start=1):
            seg = f"{r.provider} `{r.uptake_text or '—'}` ({_fmt_share(r.share)})"
            if _is_sf(r.provider):
                seg = f"🟢 **{seg}**"
                sf_in_top = True
            lines.append(f"{rank}. {seg}")

        if sf is not None and not sf_in_top:
            if sf.status == STATUS_SHOWN:
                lines.append(f"🟢 **SiliconFlow `{sf.uptake_text or '—'}` ({_fmt_share(sf.share)})**")
            elif sf.status == STATUS_SKIPPED:
                lines.append("🟢 SiliconFlow：用量少未单独抓取（核心已覆盖≥90%）")
            elif sf.status == STATUS_MISSING:
                lines.append("🟢 SiliconFlow：当日未在其页面展示")

        notes = []
        if model.n_missing:
            notes.append(f"{model.n_missing} 未展示")
        if model.n_skipped:
            notes.append(f"{model.n_skipped} 用量少未查询")
        if notes:
            lines.append(f"<font color='grey'>（另有 {'、'.join(notes)}）</font>")

        elements.append({"tag": "markdown", "content": "\n".join(lines)})

    if not any_data:
        elements.append({"tag": "markdown", "content": "⚠️ 未读到当日 provider 承接数据，请检查爬取。"})

    if dashboard_url:
        elements.append({"tag": "hr"})
        elements.append(
            {
                "tag": "action",
                "actions": [
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "🔗 查看完整看板（内网）"},
                        "url": dashboard_url,
                        "type": "primary",
                    }
                ],
            }
        )
    elements.append(
        {
            "tag": "note",
            "elements": [{"tag": "plain_text", "content": "承接量为爬取值，最终以看板为准。"}],
        }
    )

    return {
        "config": {"wide_screen_mode": True},
        "header": {"template": template, "title": {"tag": "plain_text", "content": title}},
        "elements": elements,
    }


def send_card(card: dict, receive_id: str, receive_id_type: str = "open_id") -> dict:
    data = json.dumps(
        {"receive_id": receive_id, "msg_type": "interactive", "content": json.dumps(card, ensure_ascii=False)},
        ensure_ascii=False,
    )
    env = {**os.environ, "LARK_CLI_NO_PROXY": "1"}
    proc = subprocess.run(
        [
            "lark-cli", "api", "POST", "/open-apis/im/v1/messages",
            "--params", json.dumps({"receive_id_type": receive_id_type}),
            "--data", data, "--as", "bot",
        ],
        capture_output=True, text=True, env=env,
    )
    out = proc.stdout.strip()
    try:
        return json.loads(out)
    except Exception:
        return {"_returncode": proc.returncode, "_stdout": out[:1000], "_stderr": proc.stderr[:1000]}


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Send a Core Models day as a Feishu card.")
    p.add_argument("--week", required=True, help="ISO week Monday (YYYY-MM-DD).")
    p.add_argument("--date", required=True, help="Snapshot date (YYYY-MM-DD).")
    p.add_argument("--url", default=None, help="Dashboard URL for the button.")
    p.add_argument("--to", required=True, help="receive_id (open_id or chat_id).")
    p.add_argument("--to-type", default="open_id", choices=["open_id", "chat_id"], help="receive_id type.")
    p.add_argument("--provisional", action="store_true", help="Mark data as not-yet-settled (today).")
    p.add_argument("--as-of", default=None, help="As-of time label; defaults to local HH:MM.")
    p.add_argument("--dry-run", action="store_true", help="Print the card JSON, do not send.")
    return p.parse_args()


def main() -> None:
    args = _parse_args()
    week_start = date.fromisoformat(args.week)
    snapshot = date.fromisoformat(args.date)
    as_of = args.as_of or datetime.now().strftime("%m-%d %H:%M")
    card = build_card(week_start, snapshot, args.url, provisional=bool(args.provisional), as_of=as_of)
    if args.dry_run:
        print(json.dumps(card, ensure_ascii=False, indent=2))
        return
    resp = send_card(card, args.to, args.to_type)
    print(json.dumps(resp, ensure_ascii=False)[:800])


if __name__ == "__main__":
    main()
