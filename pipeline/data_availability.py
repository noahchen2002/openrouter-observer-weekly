"""Helpers for marking historical data that can no longer be fetched."""

from __future__ import annotations

from datetime import date

EXPIRED_UNAVAILABLE_TEXT = "过期无法获取该数据"


def is_past_day(day: date, *, today: date | None = None) -> bool:
    reference = today or date.today()
    return day < reference


def activity_daily_display(day: date, tokens: int, *, api_failed: bool = False) -> str:
    if tokens > 0:
        return tokens
    if api_failed or is_past_day(day):
        return EXPIRED_UNAVAILABLE_TEXT
    return ""


def activity_daily_numeric(tokens: int, *, expired: bool) -> int:
    return 0 if expired else tokens
