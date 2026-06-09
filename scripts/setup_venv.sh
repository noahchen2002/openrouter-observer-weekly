#!/usr/bin/env bash
# Recreate project venv and install runtime + Playwright Chromium (for daily launchd).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PYTHON="${PYTHON:-/usr/bin/python3}"
if ! command -v "$PYTHON" >/dev/null 2>&1; then
  echo "Python not found: $PYTHON" >&2
  exit 1
fi

echo "Using Python: $("$PYTHON" --version) ($("$PYTHON" -c 'import sys; print(sys.executable)'))"
rm -rf .venv
"$PYTHON" -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
.venv/bin/playwright install chromium
.venv/bin/python -c "
from playwright.sync_api import sync_playwright
p = sync_playwright().start()
b = p.chromium.launch(headless=True)
b.close()
p.stop()
print('Playwright Chromium OK')
"
echo "venv ready: $ROOT/.venv/bin/python"
