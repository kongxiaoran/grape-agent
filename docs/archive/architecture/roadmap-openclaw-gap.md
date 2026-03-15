# Grape-Agent 路线图：对齐 OpenClaw 核心能力（第一阶段）

## 1. 目标

在保持 `Grape-Agent` 代码简洁度的前提下，分阶段补齐以下能力：

1. 网关控制面（Gateway Control Plane）
2. 通道插件接口（Channel Plugin Interface）
3. 多代理路由（Multi-Agent Routing）
4. Subagent 编排（Subagent Orchestration）
5. 定时任务与隔离执行（Cron + Isolated Execution）
6. 通道能力增强（先 Feishu）

本路线图参考 `openclaw` 的架构思想（网关化、插件化、会话与代理解耦），但不照搬其全部复杂度。优先做“可落地、可测试、可维护”的 Python 版本。

---

## 2. 设计原则

1. 复刻能力，不复刻复杂度：先实现核心机制，再逐步扩展。
2. 单一事实来源：`runtime_factory`、`session_store`、`gateway state` 各司其职。
3. 协议先行：先定义 Gateway 与插件接口，再落实现。
4. 默认安全：鉴权、白名单、权限边界默认开启。
5. 可观测性优先：入站、路由、工具调用、出站统一日志。

---

## 3. 里程碑总览

| 里程碑 | 主题 | 目标结果 |
| --- | --- | --- |
| M1 | 网关控制面 | 统一入口（CLI/Feishu/未来通道）通过 Gateway 协议驱动 |
| M2 | 通道插件接口 | Feishu 从“内建模块”升级为“插件实现”，可扩展 Telegram/Slack |
| M3 | 多代理路由 | 支持 route rule：channel/account/chat -> agent_id/workspace |
| M4 | Subagent 编排 | 支持 `sessions_spawn/list/history/send` 与深度限制 |
| M5 | 定时任务与隔离执行 | 支持 cron job，按 agent/session 隔离运行与回投递 |
| M6 | Feishu 增强 | 多账号、线程/话题、流式回复、消息卡片与更细策略 |

## 3.1 当前实现状态（2026-03-09）

- [x] M1 网关控制面
- [x] M2 通道插件接口（Feishu 插件化 + `channels.send`）
- [x] M3 多代理路由（profile/rules/session_key）
- [x] M4 Subagent 编排（`sessions_spawn/list/history/send` + 深度策略）
- [x] M5 定时任务与隔离执行（cron store/scheduler/executor + `cron.*` gateway）
- [x] M6 Feishu 能力增强（多账号、策略化会话作用域、长文本渐进分片、text/post/card）

---

## M1：网关控制面

### M1-1 建立 Gateway Server 骨架
- 改动文件
  - `mini_agent/gateway/server.py`（新建）
  - `mini_agent/gateway/protocol.py`（新建）
  - `mini_agent/gateway/handlers/__init__.py`（新建）
  - `mini_agent/cli.py`（接入 Gateway 启动）
- 接口草案
```python
class GatewayServer:
    async def start(self) -> None: ...
    async def stop(self) -> None: ...

class GatewayRequest(TypedDict):
    id: str
    method: str
    params: dict

class GatewayResponse(TypedDict):
    id: str
    ok: bool
    result: dict | None
    error: dict | None
```
- 验收标准
  1. 启动 `grape-agent` 时可同时拉起 Gateway。
  2. 支持最小方法：`health`、`status`、`sessions.list`。
  3. 异常请求返回统一错误结构（含 code/message）。

### M1-2 Gateway 方法注册与处理器分层
- 改动文件
  - `mini_agent/gateway/router.py`（新建）
  - `mini_agent/gateway/handlers/health.py`（新建）
  - `mini_agent/gateway/handlers/sessions.py`（新建）
- 接口草案
```python
Handler = Callable[[dict, GatewayContext], Awaitable[dict]]

class GatewayRouter:
    def register(self, method: str, handler: Handler) -> None: ...
    async def dispatch(self, req: GatewayRequest) -> GatewayResponse: ...
```
- 验收标准
  1. 方法注册与执行解耦，新增方法无需修改 server 主循环。
  2. 未注册方法返回 `METHOD_NOT_FOUND`。
  3. 单元测试覆盖 method dispatch 与异常路径。

### M1-3 鉴权与连接级上下文
- 改动文件
  - `mini_agent/gateway/auth.py`（新建）
  - `mini_agent/config.py`（新增 gateway.auth 配置）
  - `mini_agent/config/config-example.yaml`（新增示例）
- 接口草案
```python
class GatewayAuthConfig(BaseModel):
    enabled: bool = True
    token: str = ""

class ConnectionContext(TypedDict):
    client_id: str
    role: Literal["operator", "channel", "node"]
```
- 验收标准
  1. 未携带 token 的请求被拒绝（可配置关闭）。
  2. 日志能区分 client_id/role。
  3. Feishu 通道接入走 channel role。

---

## M2：通道插件接口

### M2-1 抽象 ChannelPlugin 协议
- 改动文件
  - `mini_agent/channels/types.py`（新建）
  - `mini_agent/channels/registry.py`（新建）
  - `mini_agent/channels/runtime.py`（新建）
- 接口草案
```python
class ChannelPlugin(Protocol):
    id: str
    async def start(self, ctx: "ChannelContext") -> None: ...
    async def stop(self) -> None: ...
    async def send(self, target: str, content: str, **kwargs) -> dict: ...
```
- 验收标准
  1. 插件通过 registry 注册/加载。
  2. 通道生命周期（start/stop）由统一 runtime 管理。
  3. 新增插件不改 core router。

### M2-2 Feishu 改造为插件实现
- 改动文件
  - `mini_agent/channels/plugins/feishu/plugin.py`（新建）
  - `mini_agent/channels/plugins/feishu/adapter.py`（新建）
  - `mini_agent/feishu/*`（迁移/收敛）
- 接口草案
```python
class FeishuPlugin(ChannelPlugin):
    id = "feishu"
    async def start(self, ctx: ChannelContext) -> None: ...
    async def send(self, target: str, content: str, **kwargs) -> dict: ...
```
- 验收标准
  1. Feishu 功能与当前版本等效（收发、去重、mention gating）。
  2. Gateway 中可通过 `channels.status` 查询 feishu 状态。
  3. 终端日志包含标准化通道事件格式。

### M2-3 插件配置标准化
- 改动文件
  - `mini_agent/config.py`
  - `mini_agent/config/config-example.yaml`
  - `mini_agent/channels/config_loader.py`（新建）
- 接口草案
```yaml
channels:
  feishu:
    enabled: true
    app_id: "..."
    app_secret: "..."
    group_require_mention: true
```
- 验收标准
  1. 旧 `feishu.*` 配置向新结构兼容迁移。
  2. 配置校验失败给出明确 path + reason。
  3. 文档覆盖配置字段含义与默认值。

---

## M3：多代理路由

### M3-1 AgentProfile 与 AgentRegistry
- 改动文件
  - `mini_agent/agents/profile.py`（新建）
  - `mini_agent/agents/registry.py`（新建）
  - `mini_agent/runtime_factory.py`（支持按 agent_id 构建）
- 接口草案
```python
class AgentProfile(BaseModel):
    id: str
    workspace: str
    model: str | None = None
    system_prompt_path: str | None = None

class AgentRegistry:
    def get(self, agent_id: str) -> AgentProfile: ...
```
- 验收标准
  1. 支持 `main` + 多个自定义 agent profile。
  2. 不同 agent 可有独立 workspace 与模型覆盖。
  3. `sessions.list` 能显示 session -> agent 映射。

### M3-2 RoutingRule 与路由解析器
- 改动文件
  - `mini_agent/routing/rules.py`（新建）
  - `mini_agent/routing/resolver.py`（新建）
  - `mini_agent/channels/runtime.py`（接入 resolver）
- 接口草案
```python
class RoutingInput(TypedDict):
    channel: str
    account_id: str | None
    chat_id: str
    chat_type: Literal["direct", "group"]

class RoutingResult(TypedDict):
    agent_id: str
    session_key: str
    matched_by: str
```
- 验收标准
  1. 支持 channel/account/chat_type/chat_id 维度匹配。
  2. 无匹配时稳定回落到默认 agent。
  3. 路由决策日志可追踪（含 matched_by）。

### M3-3 会话键规范
- 改动文件
  - `mini_agent/session_store.py`
  - `mini_agent/routing/session_key.py`（新建）
- 接口草案
```python
def build_session_key(agent_id: str, channel: str, chat_id: str) -> str:
    return f"agent:{agent_id}:{channel}:{chat_id}"
```
- 验收标准
  1. 会话键全局唯一且可解析。
  2. 终端/飞书/未来通道使用同一编码规范。
  3. 回归测试覆盖兼容旧 key。

---

## M4：Subagent 编排

### M4-1 引入 `sessions_spawn` 工具
- 改动文件
  - `mini_agent/tools/sessions_spawn_tool.py`（新建）
  - `mini_agent/agents/spawn.py`（新建）
  - `mini_agent/runtime_factory.py`（工具注入）
- 接口草案
```python
async def sessions_spawn(task: str, agent_id: str | None = None, mode: str = "run") -> dict:
    # return {status, child_session_key, run_id}
```
- 验收标准
  1. 主 agent 可启动子会话执行任务。
  2. 返回 child_session_key 与 run_id。
  3. 失败路径可恢复且不污染父会话。

### M4-2 `sessions_list/history/send` 工具集
- 改动文件
  - `mini_agent/tools/sessions_list_tool.py`（新建）
  - `mini_agent/tools/sessions_history_tool.py`（新建）
  - `mini_agent/tools/sessions_send_tool.py`（新建）
- 接口草案
```python
async def sessions_list(limit: int = 20) -> list[dict]: ...
async def sessions_history(session_key: str, limit: int = 50) -> list[dict]: ...
async def sessions_send(session_key: str, message: str, wait: bool = False) -> dict: ...
```
- 验收标准
  1. 父会话可以列出/查看/消息子会话。
  2. history 默认脱敏（截断超长、隐藏敏感字段）。
  3. 支持 wait 与 fire-and-forget 两种发送模式。

### M4-3 深度与权限策略
- 改动文件
  - `mini_agent/agents/policy.py`（新建）
  - `mini_agent/tools/tool_policy.py`（新建）
- 接口草案
```python
class SubagentPolicy(BaseModel):
    max_depth: int = 2
    deny_tools_leaf: list[str] = ["sessions_spawn", "sessions_list", "sessions_history"]
```
- 验收标准
  1. 达到深度上限后禁止继续 spawn。
  2. leaf subagent 自动收敛工具集。
  3. 策略命中有可审计日志。

---

## M5：定时任务与隔离执行

### M5-1 Cron 数据模型与持久化
- 改动文件
  - `mini_agent/cron/models.py`（新建）
  - `mini_agent/cron/store.py`（新建）
  - `mini_agent/config.py`（cron 配置）
- 接口草案
```python
class CronJob(BaseModel):
    id: str
    schedule: str
    agent_id: str = "main"
    task: str
    session_target: Literal["isolated", "sticky"] = "isolated"
```
- 验收标准
  1. 支持增删查改 cron job。
  2. 重启后任务可恢复。
  3. 非法 schedule 会被配置校验拦截。

### M5-2 调度器与执行器
- 改动文件
  - `mini_agent/cron/scheduler.py`（新建）
  - `mini_agent/cron/executor.py`（新建）
  - `mini_agent/cli.py`（生命周期接入）
- 接口草案
```python
class CronScheduler:
    async def start(self) -> None: ...
    async def stop(self) -> None: ...
```
- 验收标准
  1. 任务到点触发，支持并发上限。
  2. 超时任务被中断并记录状态。
  3. isolated 模式下每次运行用新 session key。

### M5-3 回投递与可观测
- 改动文件
  - `mini_agent/cron/delivery.py`（新建）
  - `mini_agent/gateway/handlers/cron.py`（新建）
- 接口草案
```python
async def deliver_cron_result(job_id: str, result: str, channel_target: dict | None) -> None: ...
```
- 验收标准
  1. 可回投递到指定通道（先支持 Feishu）。
  2. `cron.runs` 可查询历史运行状态。
  3. 失败告警消息格式统一。

---

## M6：通道能力增强（Feishu 优先）

### M6-1 多账号与账号路由
- 改动文件
  - `mini_agent/channels/plugins/feishu/accounts.py`（新建）
  - `mini_agent/channels/plugins/feishu/plugin.py`
  - `mini_agent/config.py`
- 接口草案
```yaml
channels:
  feishu:
    default_account: "main"
    accounts:
      main: { app_id: "...", app_secret: "..." }
      ops:  { app_id: "...", app_secret: "..." }
```
- 验收标准
  1. 支持多账号同时在线。
  2. 可按 routing rule 选择账号发消息。
  3. 每个账号状态独立可观测。

### M6-2 线程/话题回复与策略细化
- 改动文件
  - `mini_agent/channels/plugins/feishu/threading.py`（新建）
  - `mini_agent/channels/plugins/feishu/policy.py`（新建）
- 接口草案
```python
class FeishuPolicy(BaseModel):
    require_mention: bool = True
    reply_in_thread: bool = True
    group_session_scope: Literal["group", "group_sender", "topic"] = "group"
```
- 验收标准
  1. 群聊/话题上下文隔离可配置。
  2. thread reply 行为符合配置。
  3. policy 命中日志可追踪。

### M6-3 流式输出与卡片能力
- 改动文件
  - `mini_agent/channels/plugins/feishu/streaming.py`（新建）
  - `mini_agent/channels/plugins/feishu/cards.py`（新建）
- 接口草案
```python
class StreamingEmitter(Protocol):
    async def start(self, target: str) -> str: ...
    async def update(self, stream_id: str, delta: str) -> None: ...
    async def finish(self, stream_id: str, final_text: str) -> None: ...
```
- 验收标准
  1. 长回复可流式更新（非一次性大文本）。
  2. 超长消息自动切片并保持序号。
  3. 卡片渲染失败自动降级到纯文本。

---

## 4. 交付顺序建议

1. M1 -> M2（先把入口和插件抽象立起来）
2. M3（再做代理和路由）
3. M4（在多代理基础上做 subagent）
4. M5（加入自动化）
5. M6（最后打磨 Feishu）

---

## 5. 阶段验收门槛（Definition of Done）

每个里程碑必须满足：

1. 功能验收：核心流程可在本地复现（含异常路径）。
2. 测试验收：新增单测 + 集成测试，关键路径覆盖率不低于既有基线。
3. 文档验收：配置、启动、排障命令更新到 `docs/`。
4. 回滚验收：提供开关或兼容路径，不阻断现有 `mini_agent.cli` 使用。
