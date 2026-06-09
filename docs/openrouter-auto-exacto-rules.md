# OpenRouter Auto Exacto 路由规则

> 来源: https://openrouter.ai/docs/guides/routing/auto-exacto
> 抓取时间: 2026-05-13

## 概述

Auto Exacto 是一个自动路由优化步骤，专门针对包含 tools 的请求自动优化 Provider 排序。它**默认对所有 tool-calling 请求生效**，无需配置。

## 工作原理

当请求包含 tools 时，Auto Exacto 使用以下**真实性能信号**重新排序可用 Provider：

1. **吞吐量** — 实时每秒 token 数指标（可在模型页面的 Performance 标签页查看）
2. **Tool-calling 成功率** — 每个 Provider 完成 tool call 的可靠性（也可在 Performance 标签页查看）
3. **基准测试数据** — OpenRouter 内部评估结果，尚未公开

表现差的 Provider 被降优先级，表现强的 Provider 被提到前面。

## 实测效果

OpenRouter 观察到启用 Auto Exacto 后，tau-bench 分数和 tool-calling 成功率均有显著提升。

## 退出 Auto Exacto

**不使用 Auto Exacto 时**，OpenRouter 的默认路由是**价格加权**的 — 请求在 Provider 之间负载均衡，强烈偏向低成本。

退出方法（任选其一即可回到价格加权排序）：
1. **`provider.sort` 参数** — 在请求体的 `provider` 对象中设置 `sort: "price"`
2. **`:floor` 虚拟变体** — 在模型 slug 后附加 `:floor`（如 `openai/gpt-4o:floor`）
3. **账户默认排序设置** — 在账户设置中将默认 Provider 排序设为 price

---

## 对本项目分析的意义

1. **两种路由模式**：
   - 普通请求 → 价格逆平方加权（低价 Provider 占优）
   - Tool-calling 请求 → 吞吐量 + 成功率排序（高性能 Provider 占优）

2. **市占率归因的新维度**：如果一个 Provider 在某模型上同时获得普通流量和 tool-calling 流量，且它在该模型上有高吞吐量和高 tool-calling 成功率，那么它的市占率领先可能不仅仅是价格驱动的

3. **数据收集影响**：OpenRouter 的 Provider 页面图表显示的是合并流量（不区分路由模式），所以我们看到的市场份额是两种路由模式流量的混合结果

4. **分析建议**：
   - 如果某 Provider 价格不低但市占率领先，可能是 tool-calling 场景下的性能优势所致
   - 可以检查该 Provider 在 Performance 标签页上的吞吐量和 tool-calling 成功率来验证
   - 这也解释了为什么某些"贵但快"的 Provider 仍然有可观的市场份额
