"""Install the local "always-on server" launchd jobs for the daily report.

Two jobs, both in local (Asia/Shanghai) time:

  1. com.openrouter-observer.daily-scrape  @ 08:05
     Runs scripts.model_provider_daily — scrape + dashboard for UTC yesterday.

  2. com.openrouter-observer.daily-push    @ 09:00
     Runs scripts.local_daily_push — waits for (1) to finish, verifies, runs AI
     analysis, and sends the competitor card to the Feishu group via lark-cli.

Feishu auth is handled by lark-cli (app secret in the macOS keychain), so no
secret is written into the plists. Only the target chat_id and a few knobs are
embedded, because launchd jobs do NOT inherit your interactive shell env.

Usage:
  python3 -m scripts.install_daily_server --load          # write + load both
  python3 -m scripts.install_daily_server --unload         # remove both
  python3 -m scripts.install_daily_server --load \
      --chat-id oc_xxx --scrape-time 08:05 --push-time 09:00
"""

from __future__ import annotations

import argparse
import os
import plistlib
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LAUNCHD_DIR = PROJECT_ROOT / "data" / "debug" / "launchd"
LA_DIR = Path.home() / "Library" / "LaunchAgents"

SCRAPE_LABEL = "com.openrouter-observer.daily-scrape"
PUSH_LABEL = "com.openrouter-observer.daily-push"

# Target Feishu group chat_id. Public repo → no real id hardcoded: pass --chat-id
# or set env FEISHU_CHAT_ID at install time (the value is baked into the local
# plist under ~/Library/LaunchAgents, never committed).
DEFAULT_CHAT_ID = (os.getenv("FEISHU_CHAT_ID") or "oc_REPLACE_WITH_YOUR_GROUP_CHAT_ID").strip()
DEFAULT_DASHBOARD_URL = "https://noahchen2002.github.io/openrouter-observer-weekly/"
# launchd jobs get a bare env; add Homebrew so lark-cli / node resolve by name.
LAUNCHD_PATH = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"


def venv_python() -> str:
    candidate = PROJECT_ROOT / ".venv" / "bin" / "python"
    if not candidate.is_file() or not os.access(candidate.resolve(), os.X_OK):
        raise SystemExit(
            "Missing or broken .venv. Run: bash scripts/setup_venv.sh\n"
            "Then reinstall: python3 -m scripts.install_daily_server --load",
        )
    return str(candidate)


def playwright_browsers_path() -> str:
    return str(Path.home() / "Library" / "Caches" / "ms-playwright")


def _parse_hhmm(value: str) -> tuple[int, int]:
    hh, mm = value.split(":", 1)
    return int(hh), int(mm)


def scrape_payload(*, hour: int, minute: int, deploy_netlify: bool) -> dict:
    return {
        "Label": SCRAPE_LABEL,
        "ProgramArguments": [
            venv_python(),
            str(PROJECT_ROOT / "scripts" / "model_provider_daily.py"),
        ],
        "WorkingDirectory": str(PROJECT_ROOT),
        "EnvironmentVariables": {
            "PATH": LAUNCHD_PATH,
            "PLAYWRIGHT_BROWSERS_PATH": playwright_browsers_path(),
            "HEADLESS": "true",
            "DAILY_LATEST_N": "8",
            "DEPLOY_NETLIFY": "1" if deploy_netlify else "0",
        },
        "StartCalendarInterval": {"Hour": hour, "Minute": minute},
        "StandardOutPath": str(LAUNCHD_DIR / "daily_scrape.out.log"),
        "StandardErrorPath": str(LAUNCHD_DIR / "daily_scrape.err.log"),
        "RunAtLoad": False,
    }


def push_payload(*, hour: int, minute: int, chat_id: str, dashboard_url: str, wait_minutes: int) -> dict:
    return {
        "Label": PUSH_LABEL,
        "ProgramArguments": [
            venv_python(),
            str(PROJECT_ROOT / "scripts" / "local_daily_push.py"),
        ],
        "WorkingDirectory": str(PROJECT_ROOT),
        "EnvironmentVariables": {
            "PATH": LAUNCHD_PATH,
            "PLAYWRIGHT_BROWSERS_PATH": playwright_browsers_path(),
            "FEISHU_CHAT_ID": chat_id,
            "FEISHU_RECEIVE_ID_TYPE": "open_id" if chat_id.startswith("ou_") else "chat_id",
            "DASHBOARD_URL": dashboard_url,
            "CHECK_WAIT_MINUTES": str(wait_minutes),
            "AUTO_REPAIR": "1",
        },
        "StartCalendarInterval": {"Hour": hour, "Minute": minute},
        "StandardOutPath": str(LAUNCHD_DIR / "daily_push.out.log"),
        "StandardErrorPath": str(LAUNCHD_DIR / "daily_push.err.log"),
        "RunAtLoad": False,
    }


def _write_plist(label: str, payload: dict) -> Path:
    LAUNCHD_DIR.mkdir(parents=True, exist_ok=True)
    LA_DIR.mkdir(parents=True, exist_ok=True)
    path = LA_DIR / f"{label}.plist"
    with path.open("wb") as handle:
        plistlib.dump(payload, handle, sort_keys=False)
    return path


def _bootout(label: str) -> None:
    uid = os.getuid()
    subprocess.run(
        ["launchctl", "bootout", f"gui/{uid}", str(LA_DIR / f"{label}.plist")],
        check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def _bootstrap(label: str) -> None:
    uid = os.getuid()
    subprocess.run(["launchctl", "bootstrap", f"gui/{uid}", str(LA_DIR / f"{label}.plist")], check=True)
    subprocess.run(["launchctl", "enable", f"gui/{uid}/{label}"], check=True)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Install the local daily-report launchd server (scrape + push).")
    p.add_argument("--load", action="store_true", help="Write plists and load both jobs.")
    p.add_argument("--unload", action="store_true", help="Unload + remove both jobs and exit.")
    p.add_argument("--chat-id", default=DEFAULT_CHAT_ID, help="Feishu group chat_id (oc_...) or open_id (ou_...).")
    p.add_argument("--dashboard-url", default=DEFAULT_DASHBOARD_URL, help="Card button link.")
    p.add_argument("--scrape-time", default="08:05", help="Scrape job HH:MM local time. Default 08:05.")
    p.add_argument("--push-time", default="09:00", help="Push job HH:MM local time. Default 09:00.")
    p.add_argument("--wait-minutes", type=int, default=45, help="Max minutes the push waits for the scrape. Default 45.")
    p.add_argument("--deploy-netlify", action="store_true", help="Also deploy to Netlify from the local scrape (default off; cloud already does it).")
    return p.parse_args()


def main() -> None:
    args = _parse_args()

    if args.load and args.chat_id.startswith("oc_REPLACE"):
        raise SystemExit(
            "Refusing to load: no real chat_id. Pass --chat-id oc_xxx or set FEISHU_CHAT_ID.",
        )

    if args.unload:
        _bootout(SCRAPE_LABEL)
        _bootout(PUSH_LABEL)
        for label in (SCRAPE_LABEL, PUSH_LABEL):
            path = LA_DIR / f"{label}.plist"
            if path.exists():
                path.unlink()
        print(f"Unloaded + removed: {SCRAPE_LABEL}, {PUSH_LABEL}")
        return

    sh, sm = _parse_hhmm(args.scrape_time)
    ph, pm = _parse_hhmm(args.push_time)

    scrape_path = _write_plist(SCRAPE_LABEL, scrape_payload(hour=sh, minute=sm, deploy_netlify=args.deploy_netlify))
    push_path = _write_plist(
        PUSH_LABEL,
        push_payload(hour=ph, minute=pm, chat_id=args.chat_id, dashboard_url=args.dashboard_url, wait_minutes=args.wait_minutes),
    )

    print(f"Wrote: {scrape_path}")
    print(f"Wrote: {push_path}")
    print(f"Python: {venv_python()}")
    print(f"Scrape time: {sh:02d}:{sm:02d} | Push time: {ph:02d}:{pm:02d} (Asia/Shanghai)")
    print(f"Feishu chat_id: {args.chat_id}")
    print(f"Dashboard URL: {args.dashboard_url}")
    print(f"Push waits up to {args.wait_minutes} min for the scrape to finish.")

    if args.load:
        _bootout(SCRAPE_LABEL)
        _bootout(PUSH_LABEL)
        _bootstrap(SCRAPE_LABEL)
        _bootstrap(PUSH_LABEL)
        print(f"Loaded: {SCRAPE_LABEL}, {PUSH_LABEL}")
    else:
        print("Not loaded. Re-run with --load to bootstrap both jobs.")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as exc:
        print(f"launchctl failed: {exc}", file=sys.stderr)
        raise SystemExit(exc.returncode) from exc
