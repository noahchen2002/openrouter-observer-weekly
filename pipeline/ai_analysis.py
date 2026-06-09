"""AI competitor analysis via SiliconFlow (international site, DeepSeek V4 Pro).

Feeds the already-computed competitor data (exact numbers come from code, not the
model) to an LLM and asks for a short competitive read: where SiliconFlow is
losing, on price vs volume vs uptime, and what to watch. The model only
interprets/words it — numbers are authoritative from the workbook.

Self-skips (returns None) when SILICONFLOW_API_KEY is absent, so the pipeline
still runs without AI configured.
"""

from __future__ import annotations

import json
import os
import urllib.request
from datetime import date
from pathlib import Path

from pipeline.competitor_summary import ModelCompetition, collect_competition, iso_week_start
from pipeline.logger import get_logger

logger = get_logger()

DEFAULT_BASE = "https://api.siliconflow.com/v1"
DEFAULT_MODEL = "deepseek-ai/DeepSeek-V4-Pro"


def _load_env_file(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
            v = v[1:-1]
        if k:
            out[k] = v
    return out


def _cfg(name: str, default: str = "") -> str:
    direct = os.getenv(name)
    if direct and direct.strip():
        return direct.strip()
    env = _load_env_file(Path(__file__).resolve().parents[1] / ".env")
    return (env.get(name) or default).strip()


def _facts_for_prompt(models: list[ModelCompetition]) -> str:
    lines = []
    for m in models:
        sf = m.sf_row
        if sf is None:
            lines.append(f"{m.display_name}: 硅基当日未展示")
            continue
        above = m.competitors_above
        lines.append(
            f"\n模型 {m.display_name}: 硅基第{m.sf_rank}/{m.shown_count}名, "
            f"调用量{sf.uptake_text}, In${sf.input_price} Out${sf.output_price} "
            f"Cache${sf.cache_price} uptime{sf.uptime}%"
        )
        if not above:
            lines.append("  领先(无人超过硅基)")
        for r in above:
            lines.append(
                f"  竞品 {r.provider}: 调用量{r.uptake_text}, In${r.input_price} "
                f"Out${r.output_price} Cache${r.cache_price} uptime{r.uptime}%"
            )
    return "\n".join(lines)


def generate_ai_analysis(day: date, *, timeout: float = 90.0) -> str | None:
    key = _cfg("SILICONFLOW_API_KEY")
    if not key:
        logger.info("SILICONFLOW_API_KEY not set; skipping AI analysis")
        return None
    base = _cfg("SILICONFLOW_BASE_URL", DEFAULT_BASE).rstrip("/")
    model = _cfg("SILICONFLOW_MODEL", DEFAULT_MODEL)

    try:
        models = collect_competition(iso_week_start(day), day)
    except Exception:
        logger.exception("AI analysis: could not load competition data")
        return None
    if not models:
        return None

    facts = _facts_for_prompt(models)
    system = (
        "你是 SiliconFlow（硅基流动）的竞品分析助手。下面是某日 OpenRouter 上各核心模型的"
        "承接数据，硅基与领先它的竞品对比（调用量、In/Out/Cache 价格 $/M、uptime）。"
        "请用中文输出 3-5 条**简短**竞品洞察，聚焦：①哪些模型硅基明显落后、差距主因是价格还是"
        "稳定性还是单纯量小；②价格上我们 vs 竞品是贵还是便宜；③uptime 是否拖后腿；④可行动建议。"
        "每条一句话，直接给结论，不要复述全部数字，不要客套。"
    )
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": f"数据日期 {day.isoformat()}：\n{facts}"},
        ],
        # V4-Pro is a reasoning model: it spends most tokens on a chain-of-thought
        # (reasoning_content) before the final answer (content). Give generous room
        # so the visible answer isn't starved to empty.
        "max_tokens": 12500,
        "temperature": 0.3,
        "stream": False,
    }
    req = urllib.request.Request(
        f"{base}/chat/completions",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        text = (data["choices"][0]["message"]["content"] or "").strip()
        if not text:
            logger.warning("AI analysis returned empty content")
            return None
        logger.info("AI analysis generated (%d chars)", len(text))
        return text
    except Exception:
        logger.exception("AI analysis request failed")
        return None
