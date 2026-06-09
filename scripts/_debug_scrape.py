"""TEMP debug harness: scrape one provider page and print tooltip results.

Used to establish a baseline for accuracy hardening. Not part of the pipeline.
Usage: .venv/bin/python -m scripts._debug_scrape siliconflow deepseek
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from playwright.sync_api import sync_playwright

from pipeline import config
from pipeline.utils import navigate_with_retry, scrape_provider_chart_usage


def main() -> None:
    slugs = sys.argv[1:] or ["siliconflow"]
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=config.HEADLESS)
        page = browser.new_page(viewport={"width": 1600, "height": 1000})
        try:
            for slug in slugs:
                url = f"https://openrouter.ai/provider/{slug}"
                print(f"\n{'='*70}\nPROVIDER {slug}  {url}")
                ok = navigate_with_retry(page, url)
                print("navigate ok:", ok)
                if not ok:
                    continue
                results = scrape_provider_chart_usage(page, slug)
                print(f"-> {len(results)} date(s) scraped")
                for r in results:
                    n_models = len(r.get("models") or [])
                    print(
                        f"  {r.get('chart_date')}  total={r.get('total_tokens_text')}  "
                        f"models={n_models}  dailyPace={r.get('daily_pace_text')}"
                    )
                    for m in (r.get("models") or [])[:6]:
                        print(f"       - {m['model_name']}: {m['tokens_text']}")
        finally:
            browser.close()


if __name__ == "__main__":
    main()
