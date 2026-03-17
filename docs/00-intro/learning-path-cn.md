# 学习路线（中文）

## 你会学到什么

目标是让你在 30-90 分钟内完成三件事：

1. 能把项目跑起来并完成一次真实对话
2. 能解释一次请求从输入到输出的调用链
3. 能定位关键代码并做一个小改动

## 先建立最小概念模型（建议 15-20 分钟）

先看两篇概念文档，再进入模块实现：

1. [Agent 核心概念（中文）](./agent-core-concepts-cn.md)
2. [一次请求的端到端调用链（中文）](./e2e-call-chain-cn.md)

如果你是第一次接触 Agent 工程，这一步不要跳过。后面的模块文档默认你已经理解 `Agent loop / tool call / session / routing / subagent`。

## 路线 A：新手优先（建议顺序）

1. [README](../../README.md)：项目全景与启动方式
2. [运行时主循环](../01-runtime-loop/runtime-loop-cn.md)：核心执行闭环
3. [工具系统与 MCP](../03-tools-and-mcp/tools-and-mcp-cn.md)：工具如何被模型调用
4. [CLI 与终端 UI](../08-cli-ui/cli-ui-cn.md)：交互体验与输入输出流
5. [通道插件与飞书](../05-channels-feishu/channels-feishu-cn.md)：多入口消息如何接入

完成这条路线后，你应当能回答：

1. `agent.run()` 每一步在做什么
2. 模型产生 `tool_calls` 后，工具结果如何回填到消息历史
3. CLI 输入如何变成 `terminal/main` 会话

## 路线 B：工程实现深水区

1. [会话、路由与 Subagent](../04-session-routing-subagent/session-routing-subagent-cn.md)
2. [Gateway 与 Webterm Bridge](../06-gateway-webterm/gateway-webterm-cn.md)
3. [Cron 与隔离执行](../07-cron-isolation/cron-isolation-cn.md)
4. [部署与运维](../09-deploy-ops/deploy-ops-cn.md)

这条路线重点是“系统性能力”：多代理路由、控制面、定时编排和可运维性。

## 30 分钟最小实操

1. 启动 CLI：`uv run grape`
2. 提问一个需要读文件的问题，观察输出中是否出现 `tool call -> tool result -> final answer`
3. 再提一个长任务，观察是否触发多步循环和 token 摘要逻辑
4. 用 Gateway 发送一次 `status`，确认服务状态可见

## 代码走读锚点（按调用顺序）

1. CLI 入口：`grape_agent/cli.py:1462`（`main`）
2. 启动与装配：`grape_agent/cli.py:847`（`run_agent`）
3. 会话创建：`grape_agent/cli.py:987`（`create_managed_session`）
4. 运行时组装：`grape_agent/runtime_factory.py:324`（`build_runtime_bundle`）
5. Agent 主循环：`grape_agent/agent.py:420`（`run`）
6. 摘要触发：`grape_agent/agent.py:279`（`_summarize_messages`）
7. Gateway 状态接口：`grape_agent/gateway/handlers/status.py:8`（`handle_status`）

## 常见误区

1. 只看“实现”不看“概念”：会导致看见函数却不知道为什么存在
2. 只看 README 不看代码：无法建立真实调用链
3. 只跑 happy path：遇到取消、中断、重试时会完全失去定位能力
