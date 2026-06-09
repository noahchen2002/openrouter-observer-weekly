"""Shared utilities for the OpenRouter observer pipeline."""

from __future__ import annotations

import re
from typing import Any

from playwright.sync_api import Locator, Page

from pipeline.logger import get_logger

logger = get_logger()

MAX_NAV_RETRIES = 3


def navigate_with_retry(page: Page, url: str, max_retries: int = MAX_NAV_RETRIES) -> bool:
    for attempt in range(1, max_retries + 1):
        try:
            # Use domcontentloaded, NOT networkidle: OpenRouter keeps background
            # requests open so networkidle waited 20-60s per page (the main reason a
            # full scrape took 30-50+ min). Then wait explicitly for a recharts chart
            # to render — that's the real readiness signal for every chart page
            # (provider usage AND the Top Models ranking chart).
            page.goto(url, wait_until="domcontentloaded", timeout=45_000)
            try:
                # Wait for actual plotted bars, not just the chart container — the
                # data loads async after the wrapper appears. This is the real
                # "data ready" signal for provider usage AND the Top Models chart.
                page.wait_for_selector(".recharts-bar-rectangles .recharts-rectangle", timeout=30_000)
            except Exception:
                # Fall back to any chart container so pages with genuinely no bars
                # still proceed instead of erroring here.
                try:
                    page.wait_for_selector(".recharts-wrapper, .recharts-surface", timeout=5_000)
                except Exception:
                    pass
            page.wait_for_timeout(1_200)
            return True
        except Exception as e:
            logger.warning("Navigation attempt %d/%d failed for %s: %s", attempt, max_retries, url, e)
            if attempt < max_retries:
                page.wait_for_timeout(2_000 * attempt)
    return False


def normalize_for_match(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def parse_compact_number(value: str | None) -> float | None:
    if not value:
        return None
    match = re.search(r"([+-]?[\d,.]+)\s*([KMBT]?)\b", value, flags=re.IGNORECASE)
    if not match:
        return None
    try:
        number = float(match.group(1).replace(",", ""))
    except ValueError:
        return None
    multiplier = {
        "": 1,
        "K": 1_000,
        "M": 1_000_000,
        "B": 1_000_000_000,
        "T": 1_000_000_000_000,
    }.get(match.group(2).upper(), 1)
    return number * multiplier


def extract_chart_tooltip_structured(page: Page) -> dict[str, Any] | None:
    data = page.evaluate(
        """
        () => {
            const wrapper = document.querySelector(".recharts-tooltip-wrapper");
            if (!wrapper) return null;
            const dateEl = wrapper.querySelector("time");
            const dateStr = dateEl?.getAttribute("datetime") || dateEl?.innerText || "";
            const rows = wrapper.querySelectorAll(".flex.w-full.items-start.justify-between");
            const models = [];
            let totalText = null;
            let dailyPaceText = null;
            for (const row of rows) {
                const spans = row.querySelectorAll("span");
                if (spans.length < 2) continue;
                const name = (spans[0].innerText || "").trim();
                const value = (spans[spans.length - 1].innerText || "").trim();
                if (name.toLowerCase() === "total") {
                    totalText = value;
                } else if (name.toLowerCase() === "daily pace") {
                    dailyPaceText = value;
                } else {
                    models.push({ name, value });
                }
            }
            return { date: dateStr, models, total: totalText, dailyPace: dailyPaceText };
        }
        """
    )
    if not data or not data.get("models"):
        return None

    model_rows = []
    for m in data["models"]:
        tokens_text = m["value"]
        tokens = parse_compact_number(tokens_text)
        model_rows.append(
            {
                "model_name": m["name"],
                "tokens_text": tokens_text,
                "tokens": tokens,
            }
        )

    total_text = data.get("total")
    daily_pace_text = data.get("dailyPace")
    date_str = data.get("date", "")
    chart_date = date_str[:10] if date_str else None

    if not chart_date:
        return None

    return {
        "chart_date": chart_date,
        "total_tokens_text": total_text,
        "total_tokens": parse_compact_number(total_text),
        "daily_pace_text": daily_pace_text,
        "daily_pace": parse_compact_number(daily_pace_text),
        "models": model_rows,
    }


def locate_usage_section(page: Page) -> Locator | None:
    """定位 provider 页面的 Usage 图表区域，支持重试等待动态渲染."""
    # 先尝试等待 recharts SVG 出现（图表已渲染的信号）
    try:
        page.wait_for_selector(".recharts-wrapper, .recharts-bar-rectangles", timeout=15_000)
    except Exception:
        pass

    # 多种策略定位包含 "Tokens processed on OpenRouter" 的容器
    candidates = [
        page.locator("section").filter(
            has_text=re.compile(r"Tokens processed on OpenRouter", re.IGNORECASE)
        ),
        page.locator("article").filter(
            has_text=re.compile(r"Tokens processed on OpenRouter", re.IGNORECASE)
        ),
        page.locator("div").filter(
            has_text=re.compile(r"Tokens processed on OpenRouter", re.IGNORECASE)
        ),
    ]
    for locator in candidates:
        try:
            count = locator.count()
            if count > 0:
                return locator.first
        except Exception:
            continue

    # 兜底：直接按 recharts 图表区域找
    chart_wrappers = page.locator(".recharts-wrapper")
    try:
        if chart_wrappers.count() > 0:
            return chart_wrappers.first
    except Exception:
        pass

    return None


def scrape_provider_chart_usage(
    page: Page,
    provider_name: str = "provider",
    *,
    latest_n: int | None = None,
) -> list[dict[str, Any]]:
    """Scrape the provider usage chart.

    latest_n: if set, only hover the rightmost N bars (most recent dates). The
    intraday refresh only needs "today" (the last bar), so this avoids hovering
    all ~90 historical bars and cuts a per-provider scrape from ~40s to a few
    seconds. Default None preserves the full-history behaviour the weekly/daily
    pipeline relies on.
    """
    section = locate_usage_section(page)
    if section is None:
        logger.warning("Usage section not found on %s provider page", provider_name)
        return []

    try:
        section.scroll_into_view_if_needed(timeout=5_000)
    except Exception:
        pass

    page.wait_for_timeout(1_000)

    bar_selector = ".recharts-bar-rectangles .recharts-rectangle"
    bars = section.locator(bar_selector)

    # Get every bar's center-x in ONE round trip instead of one bounding_box() call
    # per bar (there are ~900 stacked rects; per-bar calls cost ~8s/provider).
    try:
        x_positions = bars.evaluate_all(
            """
            (els) => {
              const seen = new Set();
              const out = [];
              for (const el of els) {
                const b = el.getBoundingClientRect();
                if (!b.width && !b.height) continue;
                const cx = Math.round(b.x + b.width / 2);
                if (!seen.has(cx)) { seen.add(cx); out.push(cx); }
              }
              return out.sort((a, b) => a - b);
            }
            """
        )
    except Exception as exc:
        logger.warning("[%s] bar enumeration failed: %s", provider_name, exc)
        x_positions = []

    if not x_positions:
        logger.warning("[%s] No bars found in chart", provider_name)
        return []

    if latest_n is not None and latest_n > 0:
        x_positions = x_positions[-latest_n:]
    logger.info("[%s] Found %d unique x positions (dates)", provider_name, len(x_positions))

    svg = section.locator("svg").first
    try:
        svg_box = svg.bounding_box(timeout=2_000)
    except Exception:
        svg_box = None

    if not svg_box:
        logger.warning("[%s] Cannot get SVG bounding box", provider_name)
        return []

    center_y = svg_box["y"] + svg_box["height"] / 2

    results: list[dict[str, Any]] = []
    seen_dates: set[str] = set()
    misses = 0
    # A point just above the plot area; moving here clears any lingering tooltip so
    # the next hover forces recharts to render fresh data, preventing a stale value
    # from a previous bar being attributed to the wrong date.
    neutral_y = max(svg_box["y"] - 20, 0)

    for x in x_positions:
        payload = None
        for attempt in range(3):
            page.mouse.move(x, neutral_y)
            page.wait_for_timeout(60)
            page.mouse.move(x, center_y)
            page.wait_for_timeout(180 + attempt * 120)
            candidate = extract_chart_tooltip_structured(page)
            if candidate and candidate.get("chart_date"):
                payload = candidate
                break
        if not payload:
            misses += 1
            continue

        date_key = payload["chart_date"]
        if date_key in seen_dates:
            continue
        seen_dates.add(date_key)
        results.append(payload)

    if misses:
        logger.warning(
            "[%s] %d/%d bar position(s) yielded no tooltip", provider_name, misses, len(x_positions)
        )
    logger.info("[%s] Collected usage data for %d dates from chart", provider_name, len(results))
    return results


def clean_text(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", value).strip()


def clean_lines(value: str | None) -> list[str]:
    if not value:
        return []
    return [clean_text(line) for line in value.splitlines() if clean_text(line)]


def safe_parse_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = value.strip().replace("$", "").replace(",", "")
        if cleaned == "":
            return None
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None
