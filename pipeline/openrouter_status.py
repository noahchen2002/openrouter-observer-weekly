"""Fetch per-model daily 429 counts from SiliconFlow's OpenRouter provider dashboard.

The 429 (rate-limit) counts live ONLY in the provider dashboard's internal API,
which is Cookie-authenticated (Clerk session, 60s tokens, httpOnly client cookies
on the FAPI domain) — no public API, no bearer, and login is automation-hostile.

So we keep a long-lived REAL Chrome (not Playwright's Chromium) running with a
remote-debugging port and a dedicated profile, logged in ONCE by the operator.
The always-on Mac keeps it open so Clerk keeps the session warm. The daily job
attaches over CDP and runs fetch() inside that logged-in page (same origin → the
live session cookie is sent), so no re-login and no cookie wrangling.

Chrome is launched (see scripts/install_or_cdp_browser) as:
  Google Chrome --remote-debugging-port=9222 \
      --user-data-dir=~/.openrouter-observer/chrome-cdp \
      --proxy-server=http://127.0.0.1:7897 \
      https://openrouter.ai/provider/SiliconFlow/dashboard

Endpoints (both GET, Cookie auth):
  /api/provider-dashboard/providers/SiliconFlow/list-endpoints
      -> { data: [ { id, model_permaslug, ... } ] }  (~48)
  /api/provider-dashboard/<UUID>/get-status-raw-graph?window=7d
      -> { data: [ { x: "YYYY-MM-DD 00:00:00", y: { "error-429": N, ... } } ] }
A core model maps to every endpoint whose model_permaslug == model_id or starts
with "<model_id>-" (dated suffix); the "-" guard separates glm-5 from glm-5.1.
We SUM 429 across a model's endpoints for its daily total.
"""

from __future__ import annotations

import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from pipeline.logger import get_logger

logger = get_logger()

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BASE = "https://openrouter.ai"
# Chrome's remote-debugging endpoint rejects a 127.0.0.1 Host header (anti DNS
# rebinding) and Playwright's HTTP probe trips a 400 on Chrome 149, so we resolve
# the raw webSocketDebuggerUrl from /json/version and connect over ws:// directly.
CDP_HTTP = "http://localhost:9222"
LIST_PATH = "/api/provider-dashboard/providers/SiliconFlow/list-endpoints"
SNAPSHOT_PATH = PROJECT_ROOT / "data" / "output" / "Core_Models" / "status_errors.json"
# Error status codes we surface per model in the daily card (rate-limit + gateway).
MONITORED_STATUS = ("429", "502", "504")


class AuthExpired(RuntimeError):
    """Raised when the dashboard session is gone (401/403) — operator must re-login
    in the persistent debug Chrome."""


class BrowserUnavailable(RuntimeError):
    """Raised when the CDP debug Chrome isn't reachable on CDP_URL."""


def _core_model_ids() -> list[str]:
    raw = json.loads((PROJECT_ROOT / "config" / "core_models.json").read_text(encoding="utf-8"))
    out: list[str] = []
    for item in raw:
        if isinstance(item, str):
            out.append(item.strip())
        elif isinstance(item, dict) and item.get("model_id"):
            out.append(str(item["model_id"]).strip())
    return [m for m in out if m]


def _matches(permaslug: str, model_id: str) -> bool:
    return permaslug == model_id or permaslug.startswith(model_id + "-")


def _ws_url() -> str:
    import urllib.request
    try:
        ver = json.loads(urllib.request.urlopen(f"{CDP_HTTP}/json/version", timeout=5).read())
    except Exception as exc:
        raise BrowserUnavailable(f"debug Chrome not reachable at {CDP_HTTP}: {exc}") from exc
    ws = ver.get("webSocketDebuggerUrl")
    if not ws:
        raise BrowserUnavailable("no webSocketDebuggerUrl from debug Chrome")
    return ws


def _page_fetch_json(page, path: str):
    return page.evaluate(
        """async (p) => {
            try {
                const r = await fetch(p, { credentials: 'include', headers: { 'accept': 'application/json' } });
                if (!r.ok) return { __status: r.status };
                return await r.json();
            } catch (e) { return { __error: String(e) }; }
        }""",
        path,
    )


def fetch_core_model_status(target_day: date) -> dict[str, dict[str, int]]:
    """Return {model_id: {"429": n, "502": n, "504": n}} (summed across the model's
    SiliconFlow endpoints) for target_day. Attaches to the persistent debug Chrome
    over CDP. Raises BrowserUnavailable / AuthExpired so the caller can alert."""
    from playwright.sync_api import sync_playwright

    core = _core_model_ids()
    target = target_day.isoformat()
    codes = list(MONITORED_STATUS)
    ws = _ws_url()
    with sync_playwright() as p:
        try:
            browser = p.chromium.connect_over_cdp(ws)
        except Exception as exc:
            raise BrowserUnavailable(f"cannot attach over CDP: {exc}") from exc
        page = None
        try:
            ctx = browser.contexts[0] if browser.contexts else browser.new_context()
            # Fresh page on the origin (session cookies live in the context). Avoids
            # reusing a stale sign-in tab; if logged out, goto redirects and fetch 401s.
            page = ctx.new_page()
            page.goto(BASE, wait_until="domcontentloaded", timeout=40000)

            listing = _page_fetch_json(page, LIST_PATH)
            if not isinstance(listing, dict) or not isinstance(listing.get("data"), list):
                st = listing.get("__status") if isinstance(listing, dict) else None
                if st in (401, 403):
                    raise AuthExpired(f"list-endpoints -> {st}")
                logger.error("status fetch: list-endpoints unavailable: %s", str(listing)[:200])
                return {}

            wanted: dict[str, list[str]] = {m: [] for m in core}
            for ep in listing["data"]:
                slug = str(ep.get("model_permaslug") or "").strip()
                uuid = str(ep.get("id") or "").strip()
                if not slug or not uuid:
                    continue
                for m in core:
                    if _matches(slug, m):
                        wanted[m].append(uuid)
                        break
            uuids = sorted({u for lst in wanted.values() for u in lst})
            per_uuid = page.evaluate(
                """async ({uuids, target, codes}) => {
                    const out = {};
                    for (const id of uuids) {
                        try {
                            const r = await fetch(`/api/provider-dashboard/${id}/get-status-raw-graph?window=7d`, { credentials: 'include' });
                            if (!r.ok) { out[id] = null; continue; }
                            const j = await r.json();
                            let y = null;
                            for (const b of (j.data || [])) {
                                if (String(b.x || '').slice(0, 10) === target) { y = b.y || {}; break; }
                            }
                            if (y === null) { out[id] = null; continue; }
                            const c = {};
                            for (const code of codes) c[code] = y['error-' + code] || 0;
                            out[id] = c;
                        } catch (e) { out[id] = null; }
                    }
                    return out;
                }""",
                {"uuids": uuids, "target": target, "codes": codes},
            )
            result: dict[str, dict[str, int]] = {}
            for m, ids in wanted.items():
                per = [per_uuid.get(u) for u in ids if isinstance(per_uuid.get(u), dict)]
                if ids and per:
                    result[m] = {code: int(sum(int(d.get(code) or 0) for d in per)) for code in codes}
            logger.info("status fetch for %s: %s", target, result)
            return result
        finally:
            if page is not None:
                try:
                    page.close()
                except Exception:
                    pass
            # Disconnect CDP only; the real Chrome keeps running.
            try:
                browser.close()
            except Exception:
                pass


def _alert_target() -> str:
    """Operator receive_id for maintenance alerts, from env OR_ALERT_OPEN_ID or .env
    (kept out of source so the public repo carries no personal id)."""
    import os
    direct = (os.getenv("OR_ALERT_OPEN_ID") or "").strip()
    if direct:
        return direct
    envf = PROJECT_ROOT / ".env"
    if envf.exists():
        for line in envf.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if line.startswith("OR_ALERT_OPEN_ID=") and not line.startswith("#"):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def send_maintenance_alert(text: str) -> bool:
    """DM a maintenance alert to the operator (OR_ALERT_OPEN_ID) via lark-cli, so a
    dead 429 session/browser is never silent. Returns True on lark-cli code 0."""
    import os
    import subprocess

    to = _alert_target()
    if not to:
        logger.warning("OR_ALERT_OPEN_ID not set; cannot send 429 maintenance alert")
        return False
    rid = "open_id" if to.startswith("ou_") else "chat_id"
    data = json.dumps(
        {"receive_id": to, "msg_type": "text", "content": json.dumps({"text": text}, ensure_ascii=False)},
        ensure_ascii=False,
    )
    env = {**os.environ, "LARK_CLI_NO_PROXY": "1"}
    try:
        proc = subprocess.run(
            ["lark-cli", "api", "POST", "/open-apis/im/v1/messages",
             "--params", json.dumps({"receive_id_type": rid}), "--data", data, "--as", "bot"],
            capture_output=True, text=True, env=env, timeout=30,
        )
        ok = '"code": 0' in proc.stdout or '"code":0' in proc.stdout
        logger.info("429 maintenance alert sent (ok=%s)", ok)
        return ok
    except Exception:
        logger.exception("429 maintenance alert failed to send")
        return False


def save_status_snapshot(target_day: date) -> dict[str, dict[str, int]]:
    """Fetch + merge {model_id: {code: n}} into status_errors.json keyed by date.
    Re-raises Auth/Browser errors so the caller can alert."""
    counts = fetch_core_model_status(target_day)
    if not counts:
        return {}
    SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    store: dict[str, dict[str, dict[str, int]]] = {}
    if SNAPSHOT_PATH.exists():
        try:
            store = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
        except Exception:
            store = {}
    store[target_day.isoformat()] = counts
    SNAPSHOT_PATH.write_text(json.dumps(store, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("Saved status snapshot: %s", SNAPSHOT_PATH)
    return counts


def load_status_for_day(target_day: date) -> dict[str, dict[str, int]]:
    """Read {model_id: {code: n}} for target_day from the snapshot JSON. {} if absent."""
    if not SNAPSHOT_PATH.exists():
        return {}
    try:
        store = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
        out: dict[str, dict[str, int]] = {}
        for mid, codes in (store.get(target_day.isoformat()) or {}).items():
            if isinstance(codes, dict):
                out[str(mid)] = {str(c): int(v) for c, v in codes.items()}
        return out
    except Exception:
        return {}


def _main() -> int:
    args = sys.argv[1:]
    if args and args[0] == "fetch":
        day = datetime.now(timezone.utc).date() - timedelta(days=1)
        if len(args) >= 2:
            day = date.fromisoformat(args[1])
        try:
            print(json.dumps(fetch_core_model_status(day), ensure_ascii=False, indent=2))
        except (AuthExpired, BrowserUnavailable) as e:
            print(f"{type(e).__name__}: {e}", file=sys.stderr)
            return 3
        return 0
    print("usage: python -m pipeline.openrouter_status fetch [YYYY-MM-DD]")
    return 2


if __name__ == "__main__":
    raise SystemExit(_main())
