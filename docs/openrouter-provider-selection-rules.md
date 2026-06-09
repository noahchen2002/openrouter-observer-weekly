# OpenRouter Provider Selection 路由规则

> 来源: https://openrouter.ai/docs/guides/routing/provider-selection
> 抓取时间: 2026-05-13

## 概述

OpenRouter 将请求路由到模型的最佳可用 Provider。默认行为是基于**价格**在顶级 Provider 之间做负载均衡以最大化可用性。

## Provider 对象字段

请求体中的 `provider` 对象可包含以下字段：

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `order` | string[] | - | 按顺序尝试的 Provider slug 列表（如 `["anthropic", "openai"]`） |
| `allow_fallbacks` | boolean | `true` | 主 Provider 不可用时是否允许备用 Provider |
| `require_parameters` | boolean | `false` | 仅使用支持请求中所有参数的 Provider |
| `data_collection` | "allow" \| "deny" | "allow" | 控制是否使用可能存储数据的 Provider |
| `zdr` | boolean | - | 限制路由仅到零数据保留(ZDR)端点 |
| `enforce_distillable_text` | boolean | - | 限制路由仅到允许文本蒸馏的模型 |
| `only` | string[] | - | 允许的 Provider slug 列表 |
| `ignore` | string[] | - | 跳过的 Provider slug 列表 |
| `quantizations` | string[] | - | 按量化级别过滤（如 `["int4", "int8"]`） |
| `sort` | string | - | 按价格或吞吐量排序（`"price"` / `"throughput"` / `"latency"`） |
| `max_price` | object | - | 本次请求愿意支付的最高价格 |

## 基于价格的负载均衡（默认策略）

**这是理解市占率的关键！**

对每个模型，OpenRouter 的默认行为是在 Provider 之间负载均衡，**优先考虑价格**。

默认负载均衡策略：
1. **优先**选择过去 30 秒内没有重大故障的 Provider
2. 在稳定的 Provider 中，选择最低成本的候选项，**按价格的逆平方加权**选择
3. 将剩余 Provider 作为后备

### 负载均衡示例

如果 Provider A 每百万 token 花费 $1，Provider B 花费 $2，Provider C 花费 $3，且 Provider B 最近有几次故障：

- 请求被路由到 Provider A。Provider A 被选中的概率是 Provider C 的 **9 倍**，因为 `(1/1²) / (1/3²) = 9`
- 如果 Provider A 失败，接下来尝试 Provider C
- 如果 Provider C 也失败，最后尝试 Provider B

> **关键洞察**：默认路由使价格低的 Provider 获得指数级更多的流量。价格 3 倍便宜的 Provider 获得 9 倍的路由概率。这直接解释了为什么低价 Provider 倾向于占据高市占率。

> 注意：如果设置了 `sort` 或 `order`，负载均衡将被禁用。

## Provider 排序

三种排序选项：
- `"price"`: 优先最低价格
- `"throughput"`: 优先最高吞吐量
- `"latency"`: 优先最低延迟

## 快捷方式

- **`:nitro` 后缀**：附加到模型 slug 即按吞吐量排序（等同于 `provider.sort = "throughput"`）
- **`:floor` 后缀**：附加到模型 slug 即按价格排序（等同于 `provider.sort = "price"`）

## 指定特定 Provider

使用 `order` 字段指定 Provider 优先顺序。路由器会按此列表顺序尝试，如果一个都没运行，则回退到其他 Provider。

设置 `allow_fallbacks: false` 可禁止回退。

## 目标特定 Provider 端点

每个 Provider 可能托管同一模型的多个端点（如默认端点和 "turbo" 端点）。可用模型详情页的 Provider slug 副本按钮获取精确 slug。

例如 DeepInfra 提供 DeepSeek R1 的两个端点：
- 默认端点 slug: `deepinfra`
- Turbo 端点 slug: `deepinfra/turbo`

## 要求 Provider 支持所有参数

`require_parameters: true` — 只有支持请求中所有参数的 Provider 才会收到请求。

## 数据策略合规

`data_collection: "deny"` — 仅使用不收集用户数据的 Provider。

## EU 数据驻留（企业版）

企业客户可启用 EU 区域内路由，提示和补全完全在 EU 内处理。

---

## 对本项目分析的意义

1. **默认路由是价格逆平方加权** — 这意味着价格是市占率的首要驱动因素，低价 Provider 天然获得更多流量
2. **用户可自定义路由** — 通过 `sort`/`order`/`only` 等字段，部分用户可能绕过默认价格路由，但这些是显式选择
3. **Auto Exacto** — 对 tool-calling 请求会覆盖默认路由，改用吞吐量+成功率排序（见 auto-exacto.md）
4. **:nitro / :floor 快捷方式** — 模型 slug 的后缀变体代表不同的路由偏好，可能影响各 Provider 的实际流量分布
5. **故障回避** — 30 秒窗口内的故障会显著降低路由概率，所以 uptime 高的 Provider 有额外优势
