# Playwright 动态页面采集指南

> 记录使用 Playwright 采集 OpenRouter 动态 React 页面（排行榜 Top Models 图、Provider 用量图）的方法论与踩坑。实现代码见 `pipeline/utils.py`、`pipeline/model_ranking_weekly.py`、`pipeline/model_provider_usage.py`。

> **说明：** 旧版周度 CSV/JSON 流水线（`main.py`、`run.py`、step1–5、市占归因、`aggregate_iso_week_usage`）已下线。当前脚本见 [README.md](../README.md)：`ai_model_rankings`、`model_provider_price_uptime`、`model_provider_usage`、`core_models_usage`、`core_models_provider`、`core_models_income`。

---

## 一、适用场景

- 目标页面是 React/Vue 等 SPA，数据由前端渲染
- 需要 hover、滚动等交互才能看到 Recharts tooltip
- 无稳定公开 API 或需与页面展示一致时，用 Playwright DOM/图表交互

---

## 二、工作流

```
探索 → 诊断 → 实现 → 测试 → 修复迭代
```

---

## 三、采集路径与代码位置

| 优先级 | 路径 | 本项目中的实现 |
|--------|------|----------------|
| 1 | Recharts tooltip（按 x 坐标 hover） | `extract_chart_tooltip_structured`、`scrape_provider_chart_usage`（`pipeline/utils.py`） |
| 2 | Top Models 周堆叠图 | `_scrape_top_models_chart_payloads`（`pipeline/model_ranking_weekly.py`） |
| 3 | Activity 日用量 | `fetch_model_activity_totals`（`pipeline/model_activity.py`，HTTP API，非 Playwright） |

**原则：** 优先 `page.evaluate()` 结构化提取；Provider/排行榜图表用「唯一 x 坐标 + hover」而非逐 bar。

### 3.1 导航重试

`navigate_with_retry`（`pipeline/utils.py`）：失败时降级为 `domcontentloaded`，指数退避。

### 3.2 紧凑数字与模型名匹配

- `parse_compact_number`：`1.5T`、`66.4B` 等
- `normalize_for_match`：跨数据源模糊匹配模型名

### 3.3 跨源「周」对齐

- Rankings / Core Usage 占比：按 **ISO 周一～周日** 对齐（`--week` 传入周一）
- Provider 图表按 **日** 写入 tab，不要对 chart 数据用 `daily[-7:]` 滑动窗口去冒充 ISO 周

---

## 四、诊断技巧

- `page.screenshot` + `page.inner_text("body")` 保存快照
- `page.evaluate` 检查 tooltip wrapper、`getBoundingClientRect`
- 监听 `/api/frontend/` 响应对比 DOM 与 API

---

## 五、常见踩坑（精简）

| 问题 | 教训 |
|------|------|
| `net::ERR_CONNECTION_CLOSED` | CDN 限流 → 导航重试 + 退避 |
| URL 选择器失效（`/models/` 改版） | 用 `data-testid` 或 JS evaluate，勿依赖路径 |
| 卡片内 `.first` 链到作者页 | 一次 evaluate 遍历所有 `a[href]` |
| Tooltip `width/height=0` | 用 `.recharts-tooltip-wrapper` 直接取 DOM，不做可见性过滤 |
| innerText 把 `5B` 拆成两行 | 按 tooltip 内 `<span>` 结构化提取 |
| 901 根 bar 逐条 hover 太慢 | 按 x 中心坐标去重后 hover |
| 涨跌幅 `motion.div[title]` 与箭头颜色矛盾 | 以 SVG `text-red` / `text-green` class 为准 |
| 两源「周」定义不同 | 对比前确认日期范围一致（ISO 周 vs 滑动 7 天） |

---

## 六、扩展新采集点

1. 在对应 `pipeline/*.py` 模块实现抓取逻辑，入口脚本放 `scripts/`。
2. 复用 `pipeline/utils.py` 的 `navigate_with_retry`、`extract_chart_tooltip_structured`、`scrape_provider_chart_usage`、`normalize_for_match`。
3. 新 Provider：在 `config/core_models.json` 增加模型后跑 `model_provider_price_uptime` → `model_provider_usage`。
4. 新图表类型：仍可按 x 坐标 hover；line/area 选择器替换为 `.recharts-line` / `.recharts-area`。
