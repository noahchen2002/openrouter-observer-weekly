"""Auto-repair data quality anomalies in Core Models pipeline outputs."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from pipeline.core_models_dashboard import generate_core_models_dashboard
from pipeline.core_models_provider import generate_core_models_provider_excel
from pipeline.data_quality import DataQualityIssue, DataQualityReport, check_data_quality
from pipeline.logger import get_logger
from pipeline.model_provider_price_uptime import (
    MonitoredModel,
    generate_price_uptime_workbook_for_model,
    load_monitored_models,
)
from pipeline.model_provider_usage import generate_usage_workbook_for_model

logger = get_logger()

PLAYWRIGHT_ENV = "PLAYWRIGHT_BROWSERS_PATH"


def _ensure_playwright_env() -> None:
    if os.getenv(PLAYWRIGHT_ENV):
        return
    default = Path.home() / "Library" / "Caches" / "ms-playwright"
    if default.is_dir():
        os.environ[PLAYWRIGHT_ENV] = str(default)


@dataclass(frozen=True)
class RepairFailure:
    step: str
    detail: str
    error: str


@dataclass(frozen=True)
class RepairReport:
    week_start: date
    through_date: date
    issues_before: int
    issues_after: int | None
    repaired_steps: int
    failures: tuple[RepairFailure, ...]
    quality_before: DataQualityReport
    quality_after: DataQualityReport | None

    @property
    def ok(self) -> bool:
        if self.quality_after is None:
            return False
        return self.quality_after.ok

    @property
    def issues_fixed(self) -> int:
        if self.issues_after is None:
            return 0
        return max(0, self.issues_before - self.issues_after)

    def format_summary(self) -> str:
        lines = [
            f"Auto-repair: {self.repaired_steps} step(s) run, "
            f"{self.issues_before} issue(s) before"
            + (f", {self.issues_after} after" if self.issues_after is not None else ""),
        ]
        if self.issues_fixed > 0:
            lines.append(f"Fixed {self.issues_fixed} issue(s).")
        if self.failures:
            if self.quality_after and self.quality_after.ok:
                lines.append(
                    f"({len(self.failures)} repair step error(s), but re-check passed)"
                )
            else:
                lines.append(f"{len(self.failures)} repair failure(s):")
                for failure in self.failures:
                    lines.append(f"- [{failure.step}] {failure.detail}: {failure.error}")
        if self.quality_after and not self.quality_after.ok:
            lines.append(self.quality_after.format_summary().strip())
        return "\n".join(lines) + "\n"


def _models_by_slug(models: list[MonitoredModel]) -> dict[str, MonitoredModel]:
    return {model.model_slug: model for model in models}


def _price_uptime_pairs(issues: tuple[DataQualityIssue, ...]) -> list[tuple[MonitoredModel, date]]:
    """Issues fixable by regenerating Price&Uptime daily tabs."""
    categories = {"missing_tab", "header_mismatch"}
    models = _models_by_slug(load_monitored_models())
    seen: set[tuple[str, date]] = set()
    pairs: list[tuple[MonitoredModel, date]] = []
    for issue in issues:
        if issue.category not in categories or not issue.model_slug or not issue.snapshot_date:
            continue
        key = (issue.model_slug, issue.snapshot_date)
        if key in seen:
            continue
        model = models.get(issue.model_slug)
        if model is None:
            continue
        seen.add(key)
        pairs.append((model, issue.snapshot_date))
    return sorted(pairs, key=lambda item: (item[1], item[0].model_slug))


def _usage_pairs(issues: tuple[DataQualityIssue, ...]) -> list[tuple[MonitoredModel, date]]:
    """Issues fixable by re-running Provider Usage (Step 3.2)."""
    categories = {"incomplete_usage", "zero_shown_with_activity"}
    models = _models_by_slug(load_monitored_models())
    seen: set[tuple[str, date]] = set()
    pairs: list[tuple[MonitoredModel, date]] = []
    for issue in issues:
        if issue.category not in categories or not issue.model_slug or not issue.snapshot_date:
            continue
        key = (issue.model_slug, issue.snapshot_date)
        if key in seen:
            continue
        model = models.get(issue.model_slug)
        if model is None:
            continue
        seen.add(key)
        pairs.append((model, issue.snapshot_date))
    return sorted(pairs, key=lambda item: (item[1], item[0].model_slug))


def _group_usage_by_model(pairs: list[tuple[MonitoredModel, date]]) -> dict[MonitoredModel, list[date]]:
    grouped: dict[MonitoredModel, list[date]] = {}
    for model, snap_date in pairs:
        grouped.setdefault(model, []).append(snap_date)
    return grouped


def repair_data_quality(
    week_start: date,
    *,
    through_date: date,
    quality: DataQualityReport | None = None,
) -> RepairReport:
    """Attempt to repair detected data-quality anomalies."""
    _ensure_playwright_env()
    quality_before = quality or check_data_quality(week_start, through_date=through_date)
    if quality_before.ok:
        return RepairReport(
            week_start=week_start,
            through_date=through_date,
            issues_before=0,
            issues_after=0,
            repaired_steps=0,
            failures=(),
            quality_before=quality_before,
            quality_after=quality_before,
        )

    failures: list[RepairFailure] = []
    repaired_steps = 0

    price_pairs = _price_uptime_pairs(quality_before.issues)
    if price_pairs:
        logger.info("Repair step 1: regenerating %d Price&Uptime tab(s)", len(price_pairs))
        for model, snap_date in price_pairs:
            detail = f"{model.model_slug} @ {snap_date.isoformat()}"
            try:
                path = generate_price_uptime_workbook_for_model(model, week_start, snap_date)
                logger.info("Repaired Price&Uptime tab: %s", path)
            except Exception as exc:
                logger.exception("Price&Uptime repair failed for %s", detail)
                failures.append(RepairFailure(step="price_uptime", detail=detail, error=str(exc)))
        repaired_steps += 1

    usage_pairs = _usage_pairs(quality_before.issues)
    if usage_pairs:
        logger.info("Repair step 2: refreshing Usage for %d model/date pair(s)", len(usage_pairs))
        for model, dates in _group_usage_by_model(usage_pairs).items():
            detail = f"{model.model_slug} @ {', '.join(d.isoformat() for d in dates)}"
            try:
                path = generate_usage_workbook_for_model(model, week_start, dates)
                logger.info("Repaired Usage columns: %s", path)
            except Exception as exc:
                logger.exception("Usage repair failed for %s", detail)
                failures.append(RepairFailure(step="usage", detail=detail, error=str(exc)))
        repaired_steps += 1

    if price_pairs or usage_pairs:
        logger.info("Repair step 3: rebuilding Provider aggregate for week %s", week_start.isoformat())
        try:
            provider_path = generate_core_models_provider_excel(week_start)
            logger.info("Rebuilt Provider workbook: %s", provider_path)
            repaired_steps += 1
        except Exception as exc:
            logger.exception("Provider aggregate rebuild failed")
            failures.append(RepairFailure(step="provider_aggregate", detail=week_start.isoformat(), error=str(exc)))

        logger.info("Repair step 4: rebuilding Dashboard for week %s", week_start.isoformat())
        try:
            dashboard_path = generate_core_models_dashboard(week_start)
            logger.info("Rebuilt Dashboard: %s", dashboard_path)
            repaired_steps += 1
        except Exception as exc:
            logger.exception("Dashboard rebuild failed")
            failures.append(RepairFailure(step="dashboard", detail=week_start.isoformat(), error=str(exc)))

    quality_after = check_data_quality(week_start, through_date=through_date)
    return RepairReport(
        week_start=week_start,
        through_date=through_date,
        issues_before=len(quality_before.issues),
        issues_after=len(quality_after.issues),
        repaired_steps=repaired_steps,
        failures=tuple(failures),
        quality_before=quality_before,
        quality_after=quality_after,
    )
