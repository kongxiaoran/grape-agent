# 通道插件与飞书（概念 / 原理 / 实现）

## 概念

通道层把外部输入（如飞书）转换为 Agent 会话输入，并把结果回投递到原通道。

## 原理

- 通过 `ChannelPlugin` 抽象统一通道生命周期
- Feishu 使用长连接 WS 收消息，bridge 做去重、会话映射、回复分片
- 在 `ui.style=claude` 时，终端可同步显示飞书入站消息，便于观察远程控制流

## 实现

核心文件：

- `mini_agent/channels/runtime.py`
- `mini_agent/channels/types.py`
- `mini_agent/channels/plugins/feishu/plugin.py`
- `mini_agent/feishu/server_ws.py`
- `mini_agent/feishu/bridge.py`
- `mini_agent/feishu/embedded_runner.py`

关键能力：

- 多账号配置与默认账号
- 群聊 @ 门控
- 回复线程策略（thread/topic）
- 长文本分片发送
- 入站事件日志标准化

## 验证

1. 开启 `channels.feishu.enabled=true`
2. 飞书发送消息；若 `ui.style=claude`，观察终端出现黑底白字入站回显
3. 观察飞书收到分片/线程回复

## 常见问题

- 收不到消息：检查飞书应用订阅权限和长连接状态
- 终端无回显：确认 CLI 的 `ChannelContext.on_inbound_message` 已生效

## 代码行号引用

- 通道插件接口与上下文：`ChannelPlugin` / `ChannelContext`  
  `mini_agent/channels/types.py:17`, `mini_agent/channels/types.py:28`
- 通道运行时生命周期（start/stop/send/snapshot）  
  `mini_agent/channels/runtime.py:12`, `mini_agent/channels/runtime.py:21`, `mini_agent/channels/runtime.py:52`
- Feishu 插件多账号启动与发送类型  
  `mini_agent/channels/plugins/feishu/plugin.py:21`, `mini_agent/channels/plugins/feishu/plugin.py:33`, `mini_agent/channels/plugins/feishu/plugin.py:64`
- Feishu bridge 去重、路由、分片、处理中 ACK  
  `mini_agent/feishu/bridge.py:113`, `mini_agent/feishu/bridge.py:157`, `mini_agent/feishu/bridge.py:279`, `mini_agent/feishu/bridge.py:282`
- 终端入站回显挂钩（`ui.style=claude` 分支）  
  `mini_agent/cli.py:827`, `mini_agent/cli.py:833`
