"""Publish the latest dashboard to GitHub Pages, password-encrypted (StatiCrypt).

Replaces the Netlify path. The dashboard's data is inlined in the HTML, so we
encrypt the whole file client-side with StatiCrypt: the public *.github.io site
shows nothing without the password, and decrypts in-browser once the viewer
enters it. We then force-push {encrypted index.html + chart.umd.min.js +
.nojekyll} to the gh-pages branch. github.io is the most reliably reachable host
from mainland China without a VPN (Cloudflare Pages is officially unavailable
there; Netlify shared-IP ranges get GFW-blocked), which is why we host here.

Config (env or project .env):
  STATICRYPT_PASSWORD     dashboard password (required; kept in .env, never in source)
  GITHUB_PAGES_TOKEN      PAT with Contents:write on the repo (REQUIRED)
  GITHUB_PAGES_REPO       owner/repo (default: noahchen2002/openrouter-observer-weekly)
  GITHUB_PAGES_BRANCH     branch to publish (default: gh-pages)
  DEPLOY_PROXY            proxy for git push + npx (default: http://127.0.0.1:7897)

Non-fatal: logs and returns False on any failure, so the pipeline still finishes.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.logger import get_logger
from scripts.deploy_dashboard import (
    CHART_JS,
    DASHBOARD_DIR,
    _get,
    _latest_dashboard,
    _load_env_file,
)

logger = get_logger()

DEFAULT_REPO = "noahchen2002/openrouter-observer-weekly"
DEFAULT_BRANCH = "gh-pages"
DEFAULT_PROXY = "http://127.0.0.1:7897"
PUBLIC_URL = "https://noahchen2002.github.io/openrouter-observer-weekly/"


def _encrypt_dashboard(src_html: Path, out_dir: Path, password: str, proxy: str) -> Path | None:
    """StatiCrypt-encrypt src_html into out_dir/index.html. Returns the path or None."""
    out_dir.mkdir(parents=True, exist_ok=True)
    work = out_dir / "index.html"
    shutil.copy2(src_html, work)
    env = {**os.environ}
    # npx may need to fetch staticrypt the first time; git/npx reach the net via proxy.
    if proxy:
        env.setdefault("HTTPS_PROXY", proxy)
        env.setdefault("HTTP_PROXY", proxy)
        env.pop("ALL_PROXY", None)
        env.pop("all_proxy", None)
    cmd = ["npx", "-y", "staticrypt", str(work), "-p", password, "--short", "-d", str(out_dir)]
    proc = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=300)
    if proc.returncode != 0:
        logger.error("StatiCrypt failed (rc=%s): %s", proc.returncode, (proc.stderr or proc.stdout)[-600:])
        return None
    if not work.exists():
        logger.error("StatiCrypt produced no output at %s", work)
        return None
    return work


def _git(args: list[str], cwd: Path, proxy: str) -> subprocess.CompletedProcess:
    base = ["git", "-c", "user.email=noahchen2002@gmail.com", "-c", "user.name=or-observer-bot"]
    if proxy:
        base += ["-c", f"http.proxy={proxy}"]
    return subprocess.run(base + args, cwd=str(cwd), capture_output=True, text=True, timeout=300)


def maybe_deploy_github_pages() -> bool:
    """Encrypt the latest dashboard and force-push to gh-pages. True on success."""
    env_file = _load_env_file(PROJECT_ROOT / ".env")
    token = _get("GITHUB_PAGES_TOKEN", env_file)
    if not token:
        logger.warning("GITHUB_PAGES_TOKEN missing; skipping GitHub Pages deploy")
        return False
    repo = _get("GITHUB_PAGES_REPO", env_file) or DEFAULT_REPO
    branch = _get("GITHUB_PAGES_BRANCH", env_file) or DEFAULT_BRANCH
    password = _get("STATICRYPT_PASSWORD", env_file)
    proxy = _get("DEPLOY_PROXY", env_file) or DEFAULT_PROXY
    if not password:
        logger.warning("STATICRYPT_PASSWORD not set; skipping GitHub Pages deploy")
        return False

    latest = _latest_dashboard()
    if latest is None:
        logger.warning("No dashboard HTML in %s; nothing to deploy", DASHBOARD_DIR)
        return False

    tmp = Path(tempfile.mkdtemp(prefix="ghpages_"))
    try:
        if _encrypt_dashboard(latest, tmp, password, proxy) is None:
            return False
        # Static assets alongside the encrypted page (Chart.js is public; .nojekyll
        # stops GitHub Pages' Jekyll from mangling files).
        chart_src = DASHBOARD_DIR / CHART_JS
        if chart_src.exists():
            shutil.copy2(chart_src, tmp / CHART_JS)
        (tmp / ".nojekyll").write_text("", encoding="utf-8")

        for step in (["init", "-q"], ["checkout", "-q", "-b", branch], ["add", "-A"]):
            r = _git(step, tmp, proxy="")
            if r.returncode != 0:
                logger.error("git %s failed: %s", step[0], r.stderr[-300:])
                return False
        r = _git(["commit", "-qm", f"Deploy encrypted dashboard from {latest.name}"], tmp, proxy="")
        if r.returncode != 0:
            logger.error("git commit failed: %s", r.stderr[-300:])
            return False

        url = f"https://git:{token}@github.com/{repo}.git"
        r = _git(["push", "-f", url, branch], tmp, proxy=proxy)
        if r.returncode != 0:
            redacted = (r.stderr or r.stdout).replace(token, "<TOKEN>")[-500:]
            logger.error("git push to gh-pages failed: %s", redacted)
            return False
        logger.info("GitHub Pages deploy OK -> %s", PUBLIC_URL)
        return True
    except Exception:
        logger.exception("GitHub Pages deploy crashed")
        return False
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> None:
    raise SystemExit(0 if maybe_deploy_github_pages() else 1)


if __name__ == "__main__":
    main()
