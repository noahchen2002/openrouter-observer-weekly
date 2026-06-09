"""OpenRouter model Activity API helpers (daily token totals)."""

from __future__ import annotations

import time
from typing import Any
from urllib.parse import quote

import httpx

from pipeline import config
from pipeline.logger import get_logger

logger = get_logger()

MAX_REQUEST_RETRIES = 3
REQUEST_TIMEOUT_SECONDS = 30.0
RETRYABLE_STATUS_CODES = {429, 502, 503, 504}
JSON_HEADERS = {
    "Accept": "application/json",
    "User-Agent": "openrouter-observer-weekly/usage",
}
FRONTEND_ORIGIN = config.API_BASE_URL.replace("/api/v1", "")
# 2026-06: OpenRouter moved the frontend stats API under /api/frontend/v1/*.
# (old /api/frontend/models and /api/frontend/stats/model-activity now 404.)
MODELS_URL = f"{FRONTEND_ORIGIN}/api/frontend/v1/catalog/models"


def _should_retry(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in RETRYABLE_STATUS_CODES
    if isinstance(exc, httpx.TimeoutException):
        return True
    if isinstance(exc, httpx.TransportError):
        return True
    if isinstance(exc, OSError) and "EOF" in str(exc):
        return True
    return False


def _get_json_with_retry(url: str, *, context: str, max_retries: int = MAX_REQUEST_RETRIES) -> Any:
    last_exc: BaseException | None = None
    for attempt in range(1, max_retries + 1):
        try:
            response = httpx.get(url, headers=JSON_HEADERS, timeout=REQUEST_TIMEOUT_SECONDS)
            response.raise_for_status()
            return response.json()
        except Exception as exc:
            last_exc = exc
            if not _should_retry(exc) or attempt >= max_retries:
                raise
            delay_seconds = 2 * attempt
            logger.warning(
                "%s request attempt %d/%d failed for %s: %s; retrying in %ss",
                context,
                attempt,
                max_retries,
                url,
                exc,
                delay_seconds,
            )
            time.sleep(delay_seconds)
    if last_exc is not None:
        raise last_exc
    raise RuntimeError(f"{context} request failed without exception")


def fetch_model_permaslug(model_id: str) -> str:
    payload = _get_json_with_retry(MODELS_URL, context="Models list")
    items = payload.get("data", payload) if isinstance(payload, dict) else payload
    if not isinstance(items, list):
        raise RuntimeError("OpenRouter frontend models API did not return a model list")

    fallback: str | None = None
    for item in items:
        if not isinstance(item, dict) or item.get("slug") != model_id:
            continue
        permaslug = item.get("permaslug")
        if not permaslug:
            continue
        fallback = str(permaslug)
        name = str(item.get("name") or item.get("short_name") or "").lower()
        if "(free)" not in name:
            return str(permaslug)
    if fallback:
        return fallback
    raise RuntimeError(f"Could not resolve permaslug for model_id={model_id}")


def fetch_model_activity_totals(model_id: str) -> dict[str, int]:
    permaslug = fetch_model_permaslug(model_id)
    encoded = quote(permaslug, safe="")
    url = (
        f"{FRONTEND_ORIGIN}/api/frontend/v1/stats/model-activity"
        f"?permaslug={encoded}&variant=standard"
    )
    payload = _get_json_with_retry(url, context=f"Model activity ({model_id})")
    analytics = ((payload.get("data") or {}).get("analytics") if isinstance(payload, dict) else None) or []

    totals: dict[str, int] = {}
    for item in analytics:
        if not isinstance(item, dict):
            continue
        day = str(item.get("date") or "")[:10]
        if not day:
            continue
        prompt = int(item.get("total_prompt_tokens") or 0)
        completion = int(item.get("total_completion_tokens") or 0)
        reasoning = int(item.get("total_native_tokens_reasoning") or 0)
        totals[day] = prompt + completion + reasoning
    return totals


def model_display_name_from_endpoints(endpoints: list[dict[str, Any]], fallback_slug: str) -> str:
    for endpoint in endpoints:
        if not isinstance(endpoint, dict):
            continue
        name = str(endpoint.get("model_name") or "").strip()
        if name:
            return name
    return fallback_slug.replace("-", " ").title()


def model_activity_url(model_id: str) -> str:
    clean = model_id.strip().strip("/")
    return f"https://openrouter.ai/{clean}/activity"
