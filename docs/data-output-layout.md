# data/output 目录说明

运行产物目录，默认不纳入 git（见 `.gitignore`）。

## 当前有效结构

```text
data/output/
├── Ranking/
│   └── AI Model Rankings {YYYY-Www}.xlsx          # scripts.ai_model_rankings
├── Price&Uptime&Usage/
│   └── {model_slug}/
│       └── {model_slug} {YYYY-Www}.xlsx           # price_uptime + usage 回填
└── Core_Models/
    ├── Core Model Usage {YYYY-Www}.xlsx           # scripts.core_models_usage
    ├── Core Model Provider {YYYY-Www}.xlsx        # scripts.core_models_provider
    ├── Core Model Income {YYYY-Www}.xlsx          # scripts.core_models_income
    ├── Core Models Dashboard {YYYY-Www}.html      # scripts.build_core_models_dashboard
    └── chart.umd.min.js                           # 看板依赖（与 Dashboard 同目录）
```

## Metadata（所有 Excel）

上述 **5 类 `.xlsx`** 均含 `Metadata` sheet（字段 / 内容两列）。

- **数据更新时间**：本次写入的数据日期（snapshot date）。单日脚本为 `--date` 对应日；Price&Uptime 增量补数为工作簿内最大日 tab。**Core Model Usage / Income** 为 `week_start + 7`（该周结束后次日，保证周日数据完整）。
- **Price&Uptime&Usage** 另含 **已写入日期**：工作簿内已有 `YYYY-MM-DD` 日 tab 列表。
