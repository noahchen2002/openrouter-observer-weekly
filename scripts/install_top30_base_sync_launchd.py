"""Install a launchd job for the SiliconFlow Top 30 Base sync."""

from __future__ import annotations

import argparse
import os
import plistlib
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LABEL = "com.openrouter-observer.top30-base-sync"
PLIST_PATH = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"


def python_executable() -> str:
    venv_python = PROJECT_ROOT / ".venv" / "bin" / "python"
    if venv_python.is_file() and os.access(venv_python, os.X_OK):
        return str(venv_python)
    return sys.executable


def lark_cli_binary() -> str:
    return shutil.which("lark-cli") or "lark-cli"


def launchd_payload(*, minute_delay: int, max_messages: int) -> dict:
    log_dir = PROJECT_ROOT / "data" / "debug" / "launchd"
    return {
        "Label": LABEL,
        "ProgramArguments": [
            python_executable(),
            str(PROJECT_ROOT / "scripts" / "top30_base_sync.py"),
            "--max-messages",
            str(max_messages),
        ],
        "WorkingDirectory": str(PROJECT_ROOT),
        "EnvironmentVariables": {
            "LARK_CLI_BIN": lark_cli_binary(),
            "PATH": os.environ.get("PATH", "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"),
        },
        "StartCalendarInterval": [
            {"Weekday": 1, "Hour": 9, "Minute": minute_delay},
            {"Weekday": 4, "Hour": 12, "Minute": minute_delay},
        ],
        "StandardOutPath": str(log_dir / "top30_base_sync.out.log"),
        "StandardErrorPath": str(log_dir / "top30_base_sync.err.log"),
        "RunAtLoad": False,
    }


def write_plist(*, minute_delay: int, max_messages: int) -> Path:
    (PROJECT_ROOT / "data" / "debug" / "launchd").mkdir(parents=True, exist_ok=True)
    PLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    with PLIST_PATH.open("wb") as handle:
        plistlib.dump(launchd_payload(minute_delay=minute_delay, max_messages=max_messages), handle, sort_keys=False)
    return PLIST_PATH


def unload_job() -> None:
    uid = os.getuid()
    subprocess.run(
        ["launchctl", "bootout", f"gui/{uid}", str(PLIST_PATH)],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def load_job() -> None:
    uid = os.getuid()
    unload_job()
    subprocess.run(["launchctl", "bootstrap", f"gui/{uid}", str(PLIST_PATH)], check=True)
    subprocess.run(["launchctl", "enable", f"gui/{uid}/{LABEL}"], check=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Install the Top 30 Base sync launchd job.")
    parser.add_argument("--load", action="store_true", help="Load the job after writing the plist.")
    parser.add_argument("--unload", action="store_true", help="Unload the existing job and exit.")
    parser.add_argument(
        "--minute-delay",
        type=int,
        default=10,
        help="Run at N minutes after 09:00 Monday and 12:00 Thursday. Default: 10.",
    )
    parser.add_argument("--max-messages", type=int, default=50)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.unload:
        unload_job()
        print(f"Unloaded {LABEL}")
        return 0
    path = write_plist(minute_delay=args.minute_delay, max_messages=args.max_messages)
    print(f"Wrote {path}")
    if args.load:
        load_job()
        print(f"Loaded {LABEL}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
