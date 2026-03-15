# 学习路线（中文）

## 目标

让学习者在 30-90 分钟内完成：

1. 能跑起来 `grape-agent`
2. 能解释一次 Agent 调用链路
3. 能定位到核心模块代码并做小改动

## 路线 A：新手（建议）

1. 先看 [README](../../README.md)
2. 再看 [运行时主循环](../01-runtime-loop/runtime-loop-cn.md)
3. 再看 [工具系统与 MCP](../03-tools-and-mcp/tools-and-mcp-cn.md)
4. 再看 [CLI 与终端 UI](../08-cli-ui/cli-ui-cn.md)
5. 最后看 [通道插件与飞书](../05-channels-feishu/channels-feishu-cn.md)

## 路线 B：工程实现

1. [会话、路由与 Subagent](../04-session-routing-subagent/session-routing-subagent-cn.md)
2. [Gateway 与 Webterm Bridge](../06-gateway-webterm/gateway-webterm-cn.md)
3. [Cron 与隔离执行](../07-cron-isolation/cron-isolation-cn.md)
4. [部署与运维](../09-deploy-ops/deploy-ops-cn.md)

## 最小实践任务

1. 在终端问一个问题，观察 `thinking -> tool -> final` 输出
2. 开启 Feishu 通道，发消息并确认终端能同步打印入站消息（`ui.style=claude` 时有黑底白字回显）
3. 通过 Gateway 发送一次 `status` 请求，验证控制面状态

## 代码行号引用

- CLI 启动与交互主循环：`mini_agent/cli.py:756`, `mini_agent/cli.py:1108`
- 飞书入站终端回显挂钩：`mini_agent/cli.py:827`, `mini_agent/cli.py:833`
- Gateway `status` 处理：`mini_agent/gateway/handlers/status.py:8`
