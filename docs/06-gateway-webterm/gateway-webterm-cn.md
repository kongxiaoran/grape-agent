# Gateway 与 Webterm Bridge（概念 / 原理 / 实现）

## 概念

Gateway 是控制面，Webterm Bridge 是浏览器插件的本地桥接层。

## 原理

- Gateway 提供统一 TCP 单行 JSON 请求/响应（RPC-like）方法（health/status/sessions/channels/cron）
- Webterm Bridge 暴露本地 HTTP，向 Gateway 转发请求
- 浏览器插件只对接 Bridge，不直接接入 Agent 内部

## 实现

核心文件：

- `grape_agent/gateway/server.py`
- `grape_agent/gateway/router.py`
- `grape_agent/gateway/handlers/*.py`
- `grape_agent/webterm_bridge/server.py`
- `grape_agent/webterm_bridge/gateway_client.py`
- `browser_plugin/chrome-webterm-agent/*`

关键方法：

- `channels.status`
- `channels.send`
- `sessions.list`
- `cron.*`

## 验证

1. 启用 gateway 并设置 token
2. 使用 TCP 发送一行 JSON 调 `status`
3. 启动 bridge 与插件，验证会话创建与建议命令请求

## 代码行号引用

- Gateway 请求/响应协议模型  
  `grape_agent/gateway/protocol.py:36`, `grape_agent/gateway/protocol.py:52`
- Gateway TCP 服务（按行 JSON 收发）  
  `grape_agent/gateway/server.py:18`, `grape_agent/gateway/server.py:54`, `grape_agent/gateway/server.py:75`
- Gateway 内建方法注册  
  `grape_agent/gateway/handlers/__init__.py:28`
- `channels.send` / `channels.status` 实现  
  `grape_agent/gateway/handlers/channels.py:6`, `grape_agent/gateway/handlers/channels.py:16`
- Webterm Bridge HTTP API 与 Gateway 转发  
  `grape_agent/webterm_bridge/server.py:24`, `grape_agent/webterm_bridge/server.py:71`, `grape_agent/webterm_bridge/server.py:97`
- Bridge 会话管理与建议命令生成  
  `grape_agent/webterm_bridge/session_manager.py:36`, `grape_agent/webterm_bridge/session_manager.py:47`, `grape_agent/webterm_bridge/session_manager.py:109`
