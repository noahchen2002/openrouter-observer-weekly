# OpenRouter Monitoring Scripts

本项目当前沉淀了三套独立监控方案：

1. `AI Model Rankings`：每周监控 OpenRouter Top Models 排名和用量。
2. `Model Provider Price&Uptime&Usage`：按模型监控 provider 价格、稳定性和每日承接用量。
3. `Core Model Usage`：汇总 `core_models.json` 中重点关注模型在指定 ISO 周的 Activity 日用量与周占比。
4. `SiliconFlow Top 30 Base Sync`：读取飞书邮箱里的 Top 30 报表附件，去重后同步到多维表格，并维护用户在榜标签。

## SiliconFlow Top 30 Base Sync

```bash
python3 scripts/top30_base_sync.py --dry-run
python3 scripts/top30_base_sync.py
python3 scripts/install_top30_base_sync_launchd.py --load
```

默认计划任务在每周一 09:10、每周四 12:10 运行。详细规则见
[`docs/top30-base-sync.md`](docs/top30-base-sync.md)。

## 配置文件

配置文件位于 `config/` 目录。

### core_models.json

重点关注 **模型**（OpenRouter `model_id`），用于 Usage、Price&Uptime&Usage、Income 等脚本。

```json
[
  "deepseek/deepseek-v4-flash",
  "deepseek/deepseek-v4-pro",
  "moonshotai/kimi-k2.6"
]
```

也支持对象写法（可选 `model_slug`、`model_url`）；多数场景只写 `model_id` 字符串即可。

### core_providers.json

重点关注 **Provider**（承接方），用于按固定 provider 列表监控或过滤（名称需与模型页 **Provider** 列、Excel 中一致）。

每项可为：

- **字符串**：仅写 `provider_slug`（对应 `https://openrouter.ai/provider/{slug}`）
- **对象**：`provider_slug`（必填）+ `provider_name`（展示名，便于匹配）

```json
[
  "deepseek",
  { "provider_slug": "gmicloud", "provider_name": "GMICloud" }
]
```

`provider_slug` 可从模型页 Provider 链接获取，例如 `https://openrouter.ai/provider/deepseek` → `deepseek`。

`model_provider_usage` 会优先抓取白名单内 provider 的用量；若其合计已占该模型当日 Activity 总用量的 **90%**（与 `core_models_usage` 同源），则不再抓取其余 provider，并在 `展示状态` 列标记为 `用量少未查询`。

## 1. AI Model Rankings

### 脚本名称

```bash
python3 -m scripts.ai_model_rankings
```

### 执行方法

默认抓取上一个完整 ISO 周：

```bash
python3 -m scripts.ai_model_rankings
```

指定数据周周一：

```bash
python3 -m scripts.ai_model_rankings --week 2026-05-04
```

`--week` 必须传入目标数据周的周一日期，格式为 `YYYY-MM-DD`。

### 输出内容格式

输出为 Excel 文件，每周一个文件，包含两个 tab：

- `Ranking`
  - `模型名称`
  - `原始用量`
  - `换算后用量（T）`
  - `占比（%）`
- `Metadata`
  - `数据范围`
  - `数据更新时间`（= 本次写入的数据日期，排行榜为数据周周一）
  - `数据来源`
  - `数据周`

### 输出内容位置

```text
data/output/Ranking/AI Model Rankings {YYYY-Www}.xlsx
```

示例：

```text
data/output/Ranking/AI Model Rankings 2026-W19.xlsx
```

## 2. Core Model Usage

汇总 `[config/core_models.json](config/core_models.json)` 中配置的重点模型，在指定 ISO 周内按天拉取 [Activity 页](https://openrouter.ai/z-ai/glm-5.1/activity) 对应的每日 token（与 `model_provider_usage` 使用同一 Activity API），并输出独立 Excel。

### 脚本名称

```bash
python3 -m scripts.core_models_usage
```

### 执行方法

```bash
python3 -m scripts.core_models_usage --week 2026-05-18
```

参数说明：

- `--week`：必填，目标周周一（`YYYY-MM-DD`）。
- `--config`：可选，覆盖默认的 `config/core_models.json`。

不依赖 Price&Uptime 工作簿，可单独运行。脚本会自动拉取该周 Top Models 图的 Total 作为占比分母（与 `AI Model Rankings` 相同数据源）。

### 输出内容格式

每周一个 Excel，包含 `Usage`、`Metadata`：

- `Usage`
  - `模型ID`、`模型名称`
  - 该周周一～周日 7 列（`YYYY-MM-DD`，当日 compact 用量，如 `66.4B`）
  - `周合计`、`换算后用量（T）`、`占比（%）`（占比 = 模型周合计 / 该周排行榜 Total）
- `Metadata`
  - `数据范围`、`数据更新时间`（= 该周结束后次日，即 `week_start + 7`，保证周日数据完整）、`数据来源`、`数据周`、`排行榜 Total` 等

### 输出内容位置

```text
data/output/Core_Models/Core Model Usage {YYYY-Www}.xlsx
```

示例：

```text
data/output/Core_Models/Core Model Usage 2026-W20.xlsx
```





## 3. Model Provider Price&Uptime&Usage

这套监控按模型生成文件。模型清单见上文 **配置文件 → core_models.json**；可选 provider 白名单见 **core_providers.json**。

### 3.1 生成 Price&Uptime

#### 脚本名称

```bash
python3 -m scripts.model_provider_price_uptime
```

#### 执行方法

指定目标周和监控日期：

```bash
python3 -m scripts.model_provider_price_uptime --week 2026-05-18 --date 2026-05-18
```

参数说明：

- `--week`：必填，目标周周一，决定输出到哪个周文件。
- `--date`：可选，写入 Excel 的 tab 名；不传则默认当天。

#### 输出内容格式

输出为 Excel 文件。每个模型每周一个文件，每天一个 tab。

Price&Uptime 基础列：

- `Provider`
- `Provider URL`
- `Region`
- `Quantization`
- `Latency`
- `Throughput`
- `Uptime`
- `Total Context`
- `Max Output`
- `Input Price`
- `Output Price`
- `Cache Read`

其中：

- 价格统一为 `$ /M tokens` 口径。
- `Latency`、`Throughput` 来自模型页面 provider 卡片。
- `Uptime` 使用 OpenRouter API 的 1d uptime。

### 3.2 回填 Provider Usage

#### 脚本名称

```bash
python3 -m scripts.model_provider_usage
```

#### 执行方法

生成/更新单日 Usage 数据：

```bash
python3 -m scripts.model_provider_usage --week 2026-05-18 --date 2026-05-18
```

一次生成/更新整周 7 天：

```bash
python3 -m scripts.model_provider_usage --week 2026-05-18 --all-week
```

参数说明：

- `--week`：必填，目标周周一。
- `--date`：可选，单日模式下写入的日期 tab；不传则默认当天。
- `--all-week`：可选，生成该周周一到周日 7 个 tab。

Usage 脚本依赖同一天的 Price&Uptime tab。请先运行 `model_provider_price_uptime`，再运行 `model_provider_usage`。

#### 输出内容格式

Usage 脚本不会生成独立 Excel，而是回填到同一个 Price&Uptime&Usage Excel 的对应日期 tab。

每个 Price&Uptime&Usage 工作簿还含 `Metadata` sheet（`数据范围`、`数据更新时间`、`数据来源`、`数据周`、`已写入日期`）。`数据更新时间` 为工作簿内最新日 tab 日期；每次 price_uptime 或 usage 写入后刷新。

Usage 回填列位于 `Cache Read` 后：

- `展示状态`
- `Provider 承接用量`
- `Provider当日总量`
- `承接占比`

其中：

- `Provider 承接用量`：provider 页面 tooltip 中目标模型当天用量，例如 `66.4B`。
- `Provider当日总量`：provider 页面 tooltip 的 `Total`。
- `承接占比`：`Provider 承接用量 / 模型 Activity 页每日总用量`。
- 如果 provider tooltip 没展示该模型，则 `展示状态` 写 `未展示`。
- 若 `config/core_providers.json` 中的 provider 已覆盖该模型当日总用量的 90%，其余 provider 不再抓取，`展示状态` 写 `用量少未查询`。

### 输出内容位置

```text
data/output/Price&Uptime&Usage/{model_slug}/{model_slug} {YYYY-Www}.xlsx
```

示例：

```text
data/output/Price&Uptime&Usage/deepseek-v4-flash/deepseek-v4-flash 2026-W21.xlsx
```

### 2.3 每日自动补昨天数据

**环境（定时任务依赖 `.venv`）**

```bash
bash scripts/setup_venv.sh
```

会用系统 `/usr/bin/python3` 重建 `.venv`、安装 `requirements.txt`，并下载 Playwright Chromium 到 `~/Library/Caches/ms-playwright`。日常手动跑也请优先：

```bash
.venv/bin/python -m scripts.model_provider_daily
```

每天自动补数使用本机 `launchd`。任务目标时间是 **UTC 00:00**；当前本机时区为 Asia/Shanghai，所以实际触发时间配置为每天 **08:00**。

定时任务执行 [`scripts/model_provider_daily`](scripts/model_provider_daily.py)，按 UTC **昨天** 日期写入对应 ISO 周，顺序与上文章节一致：

1. **§2** Core Model Usage（当周整周 Activity）
2. **§3.1** Price&Uptime（昨日 tab）
3. **§3.2** Provider Usage（昨日 tab，含 Playwright，耗时常，整段可能 30–60+ 分钟）
4. **Provider 汇总** → `Core Model Provider {周}.xlsx`（§3 完成后汇总，看板 §5 依赖）
5. **§4** Core Model Income：仅当 `data/input/model_income_W*.xlsx` 存在时重生成；**未更新输入文件时跳过**，看板沿用已有 `Core Model Income {周}.xlsx`
6. **§5** Core Models Dashboard HTML

机器需保持唤醒且勿在任务运行中睡眠。周一 UTC 00:00 运行时补 UTC 周日数据，写入上一周工作簿。

手动跑一次完整每日流水线：

```bash
.venv/bin/python -m scripts.model_provider_daily
```

手动指定补某一天：

```bash
.venv/bin/python -m scripts.model_provider_daily --date 2026-05-19
```

安装 LaunchAgent 配置（**必须先有可用 `.venv`**，plist 使用 `.venv/bin/python` 与 `PLAYWRIGHT_BROWSERS_PATH`）：

```bash
python3 -m scripts.install_model_provider_daily_launchd
```

安装并立即加载定时任务：

```bash
python3 -m scripts.install_model_provider_daily_launchd --load
```

#### 飞书通知（可选）

项目支持在 **检查任务**（`com.openrouter-observer.model-provider-daily-check`）结束时发送飞书群消息：

- **成功**：发送成功摘要，并把新生成的 `Core Models Dashboard {YYYY-Www}.html` 作为文件发到群里
- **失败**：发送失败摘要（包含日志 tail）

配置方式（推荐把凭证放在独立的 `.env` 文件里，避免写入 LaunchAgent plist；launchd 不继承交互式环境）：

```bash
# 1) 指定要通知的群（chat_id）
export FEISHU_CHAT_ID="oc_xxxxxxxxxxxxxxxxxxxx  # 你的群 chat_id"

# 2) 准备飞书机器人凭证文件（示例：~/.hermes/.env）
#   FEISHU_APP_ID=...
#   FEISHU_APP_SECRET=...
#   （或 FEISHU_TENANT_ACCESS_TOKEN=...）

# 3) 重新写 plist 并加载（plist 里只存 chat_id 与 env 文件路径，不存密钥明文）
python3 -m scripts.install_model_provider_daily_launchd --load \
  --feishu-notify \
  --feishu-chat-id "$FEISHU_CHAT_ID" \
  --feishu-env-file "$HOME/.hermes/.env"
```

手动测试（不等到定时点）：

```bash
# 触发一次检查任务（会读取 launchd 里的 env 并尝试发送飞书消息）
launchctl start com.openrouter-observer.model-provider-daily-check
```

手动触发一次已加载的任务：

```bash
launchctl start com.openrouter-observer.model-provider-daily
```

查看日志：

```bash
tail -f data/debug/launchd/model_provider_daily.out.log
tail -f data/debug/launchd/model_provider_daily.err.log
```

停止并卸载任务：

```bash
python3 -m scripts.install_model_provider_daily_launchd --unload
```

若仓库在 **`~/Desktop`**，macOS 可能阻止 launchd 读取项目路径（日志里 `Operation not permitted`）。请将项目移到如 `~/Projects/`，或为 `.venv/bin/python` 开启「完全磁盘访问权限」后重装 `--load`。



### 4. Core Model Income（模型周收入）

从 `data/input/model_income_{YYYY-Www}.xlsx` 或 `model_income_Www.xlsx`（sheet `查询结果`）提取 core 模型每日 `paid_usd`，生成独立 Excel（与 Usage 同目录，不修改 Usage 工作簿）。

```bash
python3 -m scripts.core_models_income --week 2026-05-11
```

参数：`--week`（必填周一）、`--income`（默认 `data/input/model_income_{周}.xlsx`）、`--output`、`--config`。

输出：`data/output/Core_Models/Core Model Income {YYYY-Www}.xlsx`（示例：`Core Model Income 2026-W20.xlsx`）。

工作簿含 `Income`、`Metadata` 两个 tab。`Income` 列：`模型ID`、`模型名称`、该周 7 个日期列（USD）、`周合计`、`占比（%）`。占比分母 = 收入文件中该周**全部模型** `paid_usd` 合计（非仅 core 模型）。`Metadata` 中 `数据更新时间` = `week_start + 7`（该周结束后次日，保证周日数据完整）。

### 5. Core Models HTML 看板

将 Usage、Provider、Income 三份周度 Excel 汇总为单页 HTML（Tailwind CSS CDN + 本地 Chart.js）：顶部含时间范围、数据来源与核心结论，6 个 KPI 卡片，每图配有标题/说明/业务洞察，周合计占比环形图在图例与扇区（≥5%）显示百分比，表格支持表头样式、行 hover 与异常值高亮，布局响应式。Provider 区块每个模型折叠块内含 Top3 承接文字总结（与图表同源，仅统计「已展示」行）。

```bash
python3 -m scripts.build_core_models_dashboard --week 2026-05-18
```

输出：`data/output/Core_Models/Core Models Dashboard {YYYY-Www}.html` 及同目录 `chart.umd.min.js`（Chart.js 本地加载；样式依赖 Tailwind CDN，需联网打开）。用浏览器直接打开 HTML 即可。

输出目录结构说明见 [docs/data-output-layout.md](docs/data-output-layout.md)。
