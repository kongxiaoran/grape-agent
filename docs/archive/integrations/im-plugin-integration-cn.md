# Grape-Agent IM 插件集成指南（开发者 + AI）

## 1. 文档目标

本指南用于指导你把一个 IM 平台（Feishu/Lark、Telegram、Discord 等）以插件形式集成到 `grape-agent`。  
读者包括：

- 开发者：希望手工实现新通道
- AI 编程助手：希望按固定约束自动改代码

当前基线（M2-M6）已完成：

- 通道插件运行时：`grape_agent/channels/*`
- Feishu 插件化（多账号）：`grape_agent/channels/plugins/feishu/plugin.py`
- 启停接入：`grape_agent/cli.py`
- 通道状态查询：Gateway `channels.status`
- 主动发送入口：Gateway `channels.send`（透传 `ChannelRuntime.send`）
- 通道标准日志：`[ChannelEvent] channel=... event=...`
- Subagent 工具链：`sessions_spawn/list/history/send`
- Cron 调度与回投递：Gateway `cron.*`

---

## 2. 架构总览

### 2.1 运行链路

1. `grape-agent` 启动
2. `ChannelRuntime.start()` 启动所有启用的通道插件
3. IM 插件建立连接（WS/Webhook/Polling）
4. 插件收到 IM 消息后，进入该通道自己的 bridge/handler
5. bridge 调用 Agent 会话并回发消息
6. `grape-agent` 退出时，`ChannelRuntime.stop()` 统一关闭插件

### 2.2 关键代码入口

- 插件协议：`grape_agent/channels/types.py`
- 插件注册表：`grape_agent/channels/registry.py`
- 插件运行时：`grape_agent/channels/runtime.py`
- 默认注册：`build_default_registry()` in `grape_agent/channels/runtime.py`
- CLI 生命周期接入：`grape_agent/cli.py`
- Gateway 状态：
  - `grape_agent/gateway/handlers/channels.py`
  - `grape_agent/gateway/handlers/status.py`

---

## 3. 插件接口规范（必须实现）

`ChannelPlugin` 协议定义在 `grape_agent/channels/types.py`：

```python
class ChannelPlugin(Protocol):
    id: str

    async def start(self, ctx: ChannelContext) -> None: ...
    async def stop(self) -> None: ...
    async def send(self, target: str, content: str, **kwargs: Any) -> dict[str, Any]: ...
    def snapshot(self) -> dict[str, Any]: ...
```

设计要求：

- `start()`：非阻塞地完成启动；可内部起线程/协程
- `stop()`：幂等，重复调用不报错
- `send()`：统一主动消息发送入口；返回结构化结果
- `snapshot()`：返回稳定字段，至少包含 `enabled`、`running`

---

## 4. 配置规范

统一使用 `channels` 结构，不再支持顶层 `feishu`：

```yaml
channels:
  feishu:
    enabled: true
    default_account: "main"
    accounts:
      main:
        app_id: "cli_xxx"
        app_secret: "xxx"
        domain: "feishu"
      ops:
        app_id: "cli_ops_xxx"
        app_secret: "xxx"
        domain: "lark"
    policy:
      require_mention: true
      reply_in_thread: true
      group_session_scope: "group"  # group|group_sender|topic
    streaming:
      enabled: false
      chunk_size: 600
      interval_ms: 120
      reply_all_chunks: false
      progress_ping_sec: 15
```

对应配置模型在 `grape_agent/config.py`：

- `FeishuConfig`
- `ChannelsConfig`
- `Config.channels`

注意：

- 顶层 `feishu:` 会被判定为非法配置并报错
- 新 IM 插件需要增加自己的配置 model，并挂到 `ChannelsConfig`

---

## 5. 新增一个 IM 插件的最小步骤

以新增 `telegram` 为例：

1. 新建插件目录  
`grape_agent/channels/plugins/telegram/`

2. 实现插件类（参考 Feishu 插件）

```python
from __future__ import annotations
from typing import Any
from grape_agent.channels.types import ChannelContext

class TelegramChannelPlugin:
    id = "telegram"

    def __init__(self):
        self._enabled = False
        self._runner = None

    async def start(self, ctx: ChannelContext) -> None:
        self._enabled = bool(ctx.config.channels.telegram.enabled)
        # 初始化客户端/启动后台循环

    async def stop(self) -> None:
        # 关闭连接与后台任务
        pass

    async def send(self, target: str, content: str, **kwargs: Any) -> dict[str, Any]:
        # 实际发送逻辑
        return {"ok": True}

    def snapshot(self) -> dict[str, Any]:
        return {"enabled": self._enabled, "running": True, "plugin": self.id}
```

3. 注册插件  
编辑 `build_default_registry()`：

```python
registry.register("telegram", TelegramChannelPlugin)
```

4. 接入运行时可见性  
编辑 `ChannelRuntime`：

- `_configured_channel_ids()` 增加 `"telegram"`
- `_is_channel_enabled()` 增加 `channels.telegram.enabled` 判断

5. 增加配置模型与示例  
编辑：

- `grape_agent/config.py`
- `grape_agent/config/config-example.yaml`

6. 增加测试  
建议至少补：

- 配置解析测试（默认值 + 自定义值 + 错误配置）
- 运行时测试（enabled 启动、disabled 跳过、stop 幂等）

---

## 6. Feishu 插件实现说明（当前参考）

当前 Feishu 插件是一个包装层，复用既有 Feishu 逻辑：

- 插件类：`grape_agent/channels/plugins/feishu/plugin.py`
- 内部 runner：`grape_agent/feishu/embedded_runner.py`
- runner 内部仍调用 `FeishuWebSocketServer` + bridge

这是一种迁移友好的改造方式：

- 先把“生命周期管理”统一到插件框架
- 再逐步把通道内部逻辑继续解耦（适合后续 M2/M6）

---

## 7. Gateway 观测与联调

### 7.1 查询通道状态

方法：`channels.status`  
示例请求（TCP 一行 JSON）：

```json
{"id":"1","method":"channels.status","params":{},"auth":{"token":"YOUR_TOKEN","client_id":"dev","role":"operator"}}
```

典型响应：

```json
{
  "id": "1",
  "ok": true,
  "result": {
    "started": true,
    "running_count": 1,
    "channels": {
      "feishu": {
        "enabled": true,
        "running": true,
        "plugin": "feishu"
      }
    }
  },
  "error": null
}
```

### 7.2 运行期排查建议

- 插件未启动：检查 `channels.<id>.enabled`
- 已启用但未运行：检查注册表是否注册该插件
- 连接失败：查看插件内部/SDK 日志
- Gateway 里看不到通道：检查 `ChannelRuntime.snapshot()` 字段

### 7.3 主动发送（Proactive Push）

方法：`channels.send`  
参数：

- `channel`: 通道 ID（如 `feishu`）
- `target`: 目标 ID（`mode=send` 时是 `chat_id`；`mode=reply` 时可作为 `message_id` 兜底）
- `content`: 发送文本
- `options`: 通道特定可选参数（Feishu 支持以下字段）
  - `message_type`: `text`/`post`/`card`（显式指定时优先，`card` 会映射为 Feishu `interactive`）
- `mode`: `send`（默认）或 `reply`
- `receive_id_type`: `send` 模式下默认 `chat_id`
- `message_id`: `reply` 模式时优先使用
- `reply_in_thread`: `reply` 模式是否线程内回复
- `account_id`: 指定发送账号（不传则走 `default_account`）

示例请求：

```json
{"id":"2","method":"channels.send","params":{"channel":"feishu","target":"oc_xxx","content":"hello","options":{"receive_id_type":"chat_id"}},"auth":{"token":"YOUR_TOKEN","client_id":"dev","role":"operator"}}
```

注意：

- `channels.send` 的 `GatewayResponse.ok` 表示网关方法执行是否成功
- 实际通道投递结果看 `result.ok` 和 `result.error`
- `mode=reply` 时若未传 `message_id`，插件会回退使用 `target` 作为 `message_id`
- 若未显式传 `message_type`，会按 `channels.feishu.render_mode` 决策：
  - `raw`：使用 `post`
  - `card`：使用 `interactive`
  - `auto`：检测到代码块/表格时用 `interactive`，否则用 `post`
- `channels.feishu.streaming` 是“渐进分片流式”，用于长文本分片按间隔推送（不是模型 token 级流式）
- `progress_ping_sec` 用于长任务期间周期性发送“还在处理中”提示（`0` 表示关闭）

---

## 8. 对 AI 的执行约束（建议直接复制到任务提示）

1. 只修改与当前插件相关的最小文件集合。
2. 优先复用 `channels` 框架，不新增第二套生命周期系统。
3. `start/stop` 必须幂等，异常需可恢复。
4. `snapshot` 返回稳定字段：`enabled`、`running`、`plugin`。
5. 同步补齐测试：配置解析 + 运行时 + Gateway 状态。
6. 不要引入旧配置兼容层（本项目当前策略为新结构优先且唯一）。
7. 记录通道关键事件时，优先使用标准日志函数输出 `[ChannelEvent]`。

---

## 9. 验收清单

- [ ] `grape-agent` 启动后，目标 IM 插件自动启动
- [ ] `grape-agent` 退出后，目标 IM 插件自动停止
- [ ] `channels.status` 可看到该插件状态
- [ ] 配置错误时给出明确报错路径
- [ ] 核心测试通过（至少配置 + 运行时 + 网关）
- [ ] 不影响已有 Feishu 通信链路
