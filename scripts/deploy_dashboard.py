"""Publish the latest dashboard to the public Netlify site.

Assembles web/public (latest dashboard HTML as index.html + chart.js — never the
.xlsx workbooks) and runs `netlify deploy --prod`. Designed to be called as the
final step of the daily / intraday pipelines so the public URL always reflects
the freshest data. Non-fatal: if the Netlify token is absent or deploy fails, it
logs and returns False rather than breaking the pipeline.

Reads NETLIFY_AUTH_TOKEN and NETLIFY_SITE_ID from the environment or the project
.env file.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from pipeline import config
from pipeline.core_models_dashboard import dashboard_output_path  # noqa: F401  (kept for parity)
from pipeline.logger import get_logger

logger = get_logger()

WEB_DIR = PROJECT_ROOT / "web"
PUBLIC_DIR = WEB_DIR / "public"
DASHBOARD_DIR = config.OUTPUT_DIR / "Core_Models"
CHART_JS = "chart.umd.min.js"


def _load_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        key, val = key.strip(), val.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
            val = val[1:-1]
        if key:
            values[key] = val
    return values


def _get(name: str, env_file: dict[str, str]) -> str:
    direct = os.getenv(name)
    if direct and direct.strip():
        return direct.strip()
    return (env_file.get(name) or "").strip()


def _latest_dashboard() -> Path | None:
    candidates = sorted(
        DASHBOARD_DIR.glob("Core Models Dashboard *.html"),
        key=lambda p: p.name,
    )
    return candidates[-1] if candidates else None


def assemble_public() -> Path | None:
    """Copy the latest dashboard to web/public/index.html (+ chart.js). Returns the source."""
    latest = _latest_dashboard()
    if latest is None:
        logger.warning("No dashboard HTML found in %s; nothing to deploy", DASHBOARD_DIR)
        return None
    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(latest, PUBLIC_DIR / "index.html")
    chart_src = DASHBOARD_DIR / CHART_JS
    if chart_src.exists():
        shutil.copy2(chart_src, PUBLIC_DIR / CHART_JS)
    logger.info("Assembled public dir from %s", latest.name)
    return latest


def maybe_deploy_dashboard() -> bool:
    """Assemble + deploy to Netlify. Returns True on success, False if skipped/failed."""
    env_file = _load_env_file(PROJECT_ROOT / ".env")
    token = _get("NETLIFY_AUTH_TOKEN", env_file)
    site = _get("NETLIFY_SITE_ID", env_file)
    if not token or not site:
        logger.warning("Netlify token/site missing; skipping public deploy")
        return False

    if assemble_public() is None:
        return False

    cmd = [
        "npx", "-y", "netlify-cli", "deploy",
        "--prod", "--dir", "public", "--site", site,
        "--message", "auto-deploy from pipeline",
    ]
    env = {**os.environ, "NETLIFY_AUTH_TOKEN": token}
    try:
        proc = subprocess.run(cmd, cwd=str(WEB_DIR), env=env, capture_output=True, text=True, timeout=600)
    except Exception:
        logger.exception("Netlify deploy crashed")
        return False
    if proc.returncode != 0:
        logger.error("Netlify deploy failed (rc=%s): %s", proc.returncode, (proc.stderr or proc.stdout)[-800:])
        return False
    logger.info("Netlify deploy OK -> public site updated")
    return True


def main() -> None:
    ok = maybe_deploy_dashboard()
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
