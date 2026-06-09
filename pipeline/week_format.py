"""ISO week and Chinese date formatting helpers."""

from __future__ import annotations

from datetime import date, timedelta


def iso_week_label(week_start: date) -> str:
    iso = week_start.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def format_cn_date(value: date) -> str:
    return f"{value.year}/{value.month}/{value.day}"


def format_data_range(week_start: date) -> str:
    week_end = week_start + timedelta(days=6)
    return f"{format_cn_date(week_start)} ～ {format_cn_date(week_end)}"
