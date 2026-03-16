# 文档实现一致性强化审计（含代码行号）

审计范围：`docs/README.md` 与 `docs/00-intro`、`docs/01-09` 主学习文档。  
审计目标：每篇文档关键结论均可追溯到当前代码实现，不记录未落地能力。

## 逐文档追溯表

| 文档 | 关键结论（节选） | 代码证据（文件:行） | 结论 |
| --- | --- | --- | --- |
| `docs/README.md` | 学习路径覆盖 runtime / tools / channels / gateway / bridge | `grape_agent/agent.py:322`, `grape_agent/runtime_factory.py:244`, `grape_agent/channels/runtime.py:12`, `grape_agent/gateway/server.py:18`, `grape_agent/webterm_bridge/server.py:24` | 已对齐 |
| `docs/00-intro/learning-path-cn.md` | CLI 可跑通、飞书入站可在 claude 样式下回显、gateway 可调 status | `grape_agent/cli.py:756`, `grape_agent/cli.py:833`, `grape_agent/gateway/handlers/status.py:8` | 已对齐 |
| `docs/00-intro/repo-structure-policy.md` | 配置/入口目录治理建议基于当前工程入口 | `grape_agent/cli.py:1302`, `grape_agent/config.py:666`, `grape_agent/config.py:704` | 已对齐 |
| `docs/00-intro/doc-migration-map.md` | 文档迁移关系（非运行时代码行为） | 文档治理说明，不声明运行时实现 | 已对齐 |
| `docs/01-runtime-loop/runtime-loop-cn.md` | `max_steps` 控制循环、超阈值才摘要、支持取消清理 | `grape_agent/agent.py:343`, `grape_agent/agent.py:202`, `grape_agent/agent.py:345`, `grape_agent/agent.py:417` | 已对齐 |
| `docs/02-llm-and-prompt/llm-and-prompt-cn.md` | 统一 `LLMResponse`、注入身份护栏、usage/provider_events 标准化 | `grape_agent/schema/schema.py:59`, `grape_agent/runtime_factory.py:70`, `grape_agent/llm/anthropic_client.py:294`, `grape_agent/llm/openai_client.py:289` | 已对齐 |
| `docs/03-tools-and-mcp/tools-and-mcp-cn.md` | 文件/Bash/MCP/Skill 工具体系与真实工具名 | `grape_agent/tools/file_tools.py:63`, `grape_agent/tools/bash_tool.py:217`, `grape_agent/tools/mcp_loader.py:183`, `grape_agent/tools/skill_tool.py:13` | 已对齐 |
| `docs/04-session-routing-subagent/session-routing-subagent-cn.md` | session key 规范、路由规则、subagent 深度限制与叶子工具策略 | `grape_agent/routing/session_key.py:6`, `grape_agent/routing/resolver.py:38`, `grape_agent/agents/orchestrator.py:69`, `grape_agent/agents/policy.py:16` | 已对齐 |
| `docs/05-channels-feishu/channels-feishu-cn.md` | ChannelPlugin 生命周期、飞书桥接、分片发送、claude 样式入站回显 | `grape_agent/channels/types.py:28`, `grape_agent/channels/runtime.py:21`, `grape_agent/feishu/bridge.py:282`, `grape_agent/cli.py:833` | 已对齐 |
| `docs/06-gateway-webterm/gateway-webterm-cn.md` | Gateway TCP 单行 JSON（RPC-like）、channels/sessions/cron 方法、Bridge HTTP 转发 | `grape_agent/gateway/server.py:54`, `grape_agent/gateway/handlers/channels.py:16`, `grape_agent/gateway/handlers/sessions.py:6`, `grape_agent/gateway/handlers/cron.py:8`, `grape_agent/webterm_bridge/server.py:97` | 已对齐 |
| `docs/07-cron-isolation/cron-isolation-cn.md` | cron 轮询调度、并发限制、`sticky/isolated` 会话策略、结果回投递 | `grape_agent/cron/scheduler.py:71`, `grape_agent/cron/scheduler.py:31`, `grape_agent/cron/executor.py:77`, `grape_agent/cron/delivery.py:32` | 已对齐 |
| `docs/08-cli-ui/cli-ui-cn.md` | claude 风格 UI、thinking 动态行（1s 刷新）、工具紧凑展示、Ctrl+C 清理退出 | `grape_agent/ui/renderer.py:111`, `grape_agent/ui/renderer.py:137`, `grape_agent/ui/renderer.py:211`, `grape_agent/cli.py:1278`, `grape_agent/cli.py:1287` | 已对齐 |
| `docs/09-deploy-ops/deploy-ops-cn.md` | 配置搜索优先级、主服务/通道/gateway/bridge 启停关系 | `grape_agent/config.py:704`, `grape_agent/cli.py:994`, `grape_agent/cli.py:956`, `grape_agent/cli.py:1293`, `grape_agent/webterm_bridge/server.py:163` | 已对齐 |

## 本轮修订摘要

- 已为学习索引与模块文档补充“代码行号引用”章节。
- 已修正文档中与实现不一致的描述（如 cron 会话策略、飞书终端回显前提、Gateway 协议措辞、工具名精度）。
- 当前审计未发现“文档声称已实现但代码不存在”的剩余条目（在本轮范围内）。
