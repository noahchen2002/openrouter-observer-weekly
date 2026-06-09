"""Install a launchd job for the daily Core Models pipeline (README sections 2-5)."""

from __future__ import annotations

import argparse
import os
import plistlib
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LABEL = "com.openrouter-observer.model-provider-daily"
PLIST_PATH = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"
CHECK_LABEL = "com.openrouter-observer.model-provider-daily-check"
CHECK_PLIST_PATH = Path.home() / "Library" / "LaunchAgents" / f"{CHECK_LABEL}.plist"


def resolve_venv_python() -> Path | None:
    venv_python = PROJECT_ROOT / ".venv" / "bin" / "python"
    if not venv_python.is_file():
        return None
    try:
        resolved = venv_python.resolve(strict=True)
    except OSError:
        return None
    if not os.access(resolved, os.X_OK):
        return None
    return venv_python


def python_executable() -> str:
    venv_python = resolve_venv_python()
    if venv_python is not None:
        return str(venv_python)
    raise SystemExit(
        "Missing or broken .venv. Run: bash scripts/setup_venv.sh\n"
        "Then reinstall launchd: python3 -m scripts.install_model_provider_daily_launchd --load",
    )


def playwright_browsers_path() -> str:
    return str(Path.home() / "Library" / "Caches" / "ms-playwright")


def _parse_dotenv(path: Path) -> dict[str, str]:
    """Parse a simple .env file (KEY=VALUE, # comments)."""
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        # Strip optional quotes.
        if len(value) >= 2 and ((value[0] == value[-1] == '"') or (value[0] == value[-1] == "'")):
            value = value[1:-1]
        values[key] = value
    return values


def _copy_env(keys: tuple[str, ...]) -> dict[str, str]:
    """Copy selected env vars into the launchd plist.

    launchd jobs do not inherit your interactive shell environment, so any
    tokens/ids needed by the job should be embedded into the plist (stored under
    ~/Library/LaunchAgents).
    """

    env: dict[str, str] = {}
    for key in keys:
        value = os.getenv(key)
        if value is not None and str(value).strip() != "":
            env[key] = str(value)
    return env


def launchd_payload() -> dict:
    log_dir = PROJECT_ROOT / "data" / "debug" / "launchd"
    return {
        "Label": LABEL,
        "ProgramArguments": [
            python_executable(),
            str(PROJECT_ROOT / "scripts" / "model_provider_daily.py"),
        ],
        "WorkingDirectory": str(PROJECT_ROOT),
        "EnvironmentVariables": {
            "PLAYWRIGHT_BROWSERS_PATH": playwright_browsers_path(),
        },
        "StartCalendarInterval": {
            "Hour": 8,
            "Minute": 0,
        },
        "StandardOutPath": str(log_dir / "model_provider_daily.out.log"),
        "StandardErrorPath": str(log_dir / "model_provider_daily.err.log"),
        "RunAtLoad": False,
    }


def check_launchd_payload(
    *,
    hour: int = 9,
    minute: int = 0,
    feishu_chat_id: str | None = None,
    feishu_notify: bool = False,
    feishu_env_file: str | None = None,
) -> dict:
    """Install a follow-up check job to ensure the daily pipeline completed."""
    log_dir = PROJECT_ROOT / "data" / "debug" / "launchd"
    env = {
        "PLAYWRIGHT_BROWSERS_PATH": playwright_browsers_path(),
        "AUTO_REPAIR": "1",
    }
    if feishu_notify:
        env["FEISHU_NOTIFY"] = "1"
    if feishu_chat_id:
        env["FEISHU_CHAT_ID"] = feishu_chat_id
    if feishu_env_file:
        env["FEISHU_ENV_FILE"] = feishu_env_file
    return {
        "Label": CHECK_LABEL,
        "ProgramArguments": [
            python_executable(),
            str(PROJECT_ROOT / "scripts" / "model_provider_daily_check.py"),
        ],
        "WorkingDirectory": str(PROJECT_ROOT),
        "EnvironmentVariables": env,
        "StartCalendarInterval": {
            "Hour": int(hour),
            "Minute": int(minute),
        },
        "StandardOutPath": str(log_dir / "model_provider_daily_check.out.log"),
        "StandardErrorPath": str(log_dir / "model_provider_daily_check.err.log"),
        "RunAtLoad": False,
    }


def write_plist() -> Path:
    log_dir = PROJECT_ROOT / "data" / "debug" / "launchd"
    log_dir.mkdir(parents=True, exist_ok=True)
    PLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    with PLIST_PATH.open("wb") as handle:
        plistlib.dump(launchd_payload(), handle, sort_keys=False)
    return PLIST_PATH


def write_check_plist(
    *,
    hour: int = 9,
    minute: int = 0,
    feishu_chat_id: str | None = None,
    feishu_notify: bool = False,
    feishu_env_file: str | None = None,
) -> Path:
    log_dir = PROJECT_ROOT / "data" / "debug" / "launchd"
    log_dir.mkdir(parents=True, exist_ok=True)
    CHECK_PLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    with CHECK_PLIST_PATH.open("wb") as handle:
        plistlib.dump(
            check_launchd_payload(
                hour=hour,
                minute=minute,
                feishu_chat_id=feishu_chat_id,
                feishu_notify=feishu_notify,
                feishu_env_file=feishu_env_file,
            ),
            handle,
            sort_keys=False,
        )
    return CHECK_PLIST_PATH


def _launchctl(*args: str) -> None:
    subprocess.run(["launchctl", *args], check=True)


def load_job() -> None:
    uid = os.getuid()
    unload_job()
    _launchctl("bootstrap", f"gui/{uid}", str(PLIST_PATH))
    _launchctl("enable", f"gui/{uid}/{LABEL}")
    _launchctl("bootstrap", f"gui/{uid}", str(CHECK_PLIST_PATH))
    _launchctl("enable", f"gui/{uid}/{CHECK_LABEL}")


def unload_job() -> None:
    uid = os.getuid()
    subprocess.run(
        ["launchctl", "bootout", f"gui/{uid}", str(PLIST_PATH)],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    subprocess.run(
        ["launchctl", "bootout", f"gui/{uid}", str(CHECK_PLIST_PATH)],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Install the daily Core Models launchd job (sections 2-5)",
    )
    parser.add_argument("--load", action="store_true", help="Load the job after writing the plist.")
    parser.add_argument("--unload", action="store_true", help="Unload the existing job and exit.")
    parser.add_argument("--check-hour", type=int, default=9, help="Check job hour (local time). Default: 9.")
    parser.add_argument("--check-minute", type=int, default=0, help="Check job minute (local time). Default: 0.")
    parser.add_argument(
        "--feishu-chat-id",
        default=None,
        help="Feishu group chat_id for notifications (stored in check job env FEISHU_CHAT_ID).",
    )
    parser.add_argument(
        "--feishu-notify",
        action="store_true",
        help="Enable Feishu notification from the check job (sets FEISHU_NOTIFY=1).",
    )
    parser.add_argument(
        "--feishu-env-file",
        default=str(Path.home() / ".hermes" / ".env"),
        help="Optional .env file to read Feishu credentials from (default: ~/.hermes/.env).",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    if args.unload:
        unload_job()
        print(f"Unloaded launchd job: {LABEL}")
        print(f"Unloaded launchd job: {CHECK_LABEL}")
        return

    path = write_plist()
    check_path = write_check_plist(
        hour=args.check_hour,
        minute=args.check_minute,
        feishu_chat_id=args.feishu_chat_id,
        feishu_notify=bool(args.feishu_notify),
        feishu_env_file=args.feishu_env_file,
    )
    print(f"Wrote launchd plist: {path}")
    print(f"Wrote launchd plist: {check_path}")
    print(f"Python: {python_executable()}")
    print(f"PLAYWRIGHT_BROWSERS_PATH: {playwright_browsers_path()}")
    print("Scheduled local time: 08:00 (Asia/Shanghai), equivalent to UTC 00:00.")
    print(f"Scheduled check local time: {args.check_hour:02d}:{args.check_minute:02d}.")
    if args.feishu_notify:
        print(f"Feishu notify: enabled (chat_id={args.feishu_chat_id or 'MISSING'})")
        print(f"Feishu env file: {args.feishu_env_file}")
    print(
        "Note: if the repo lives under ~/Desktop, grant Full Disk Access to .venv/bin/python "
        "or move the project out of Desktop (macOS blocks launchd otherwise).",
    )
    if args.load:
        load_job()
        print(f"Loaded launchd job: {LABEL}")
        print(f"Loaded launchd job: {CHECK_LABEL}")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as exc:
        print(f"launchctl failed: {exc}", file=sys.stderr)
        raise SystemExit(exc.returncode) from exc
