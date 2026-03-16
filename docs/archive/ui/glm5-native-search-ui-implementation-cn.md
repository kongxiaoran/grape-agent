# GLM-5 原生搜索与终端交互重构方案（P0/P1 实现记录）

## 1. 目标
本次改造有两条主线：
1. **GLM-5 原生联网搜索**：优先走模型内建搜索能力，而不是 MCP/bash。
2. **CLI 交互重构**：输出风格贴近 Claude Code，减少噪音并增强“工具可见性”。

## 2. 关键问题与根因

### 2.1 原生搜索 422 报错
在 `anthropic` 协议入口下，若注入 OpenAI 风格：
```json
{"type":"web_search","web_search":{"enable":"True"}}
```
会报 `tools[].name missing`（422）。

根因：Anthropic 入口按 **server tool schema** 校验，要求 `name` 等字段。

### 2.2 交互不可见
历史输出以 step 框为主（`💭 Step x/y`），对“模型原生工具调用”没有可视事件，导致看不到是否真的触发了 web search。

## 3. 分期方案（与落地状态）

| Phase | 目标 | 状态 |
|---|---|---|
| P0 | 去掉 step 框与默认耗时、支持 provider 原生工具事件展示、工具调用紧凑化 | ✅ 已实现 |
| P1 | 抽离统一渲染器（legacy/compact/claude）、增加 UI 配置与 `--ui-style` | ✅ 已实现 |

---

## 4. P0 详细实现

### 4.1 去掉默认 step 框与 step 耗时
- 默认样式改为 `claude`，并默认：
  - `show_steps=false`
  - `show_timing=false`
- 结果：默认不再打印 `💭 Step x/y` 和 `⏱️ Step ...`

### 4.2 Provider 原生工具事件结构
在 schema 增加 `ProviderEvent`，并在 `LLMResponse` 增加：
- `provider_events: list[ProviderEvent] | None`

### 4.3 Anthropic 解析 server_tool_use/tool_result
在 `AnthropicClient._parse_response()` 里解析：
- `server_tool_use` -> 记录工具名称与 input
- `tool_result` -> 记录 tool_use_id 与返回摘要

### 4.4 Tool Call 输出紧凑化
`Agent.run()` 改为一行展示工具调用，例如：
```text
⏺ bash(command=echo hello)
✓ bash: hello
```
不再默认打印大块 JSON 参数（可通过配置开启）。

---

## 5. P1 详细实现

### 5.1 抽离统一渲染器
新增：
- `grape_agent/ui/renderer.py`
- `grape_agent/ui/__init__.py`

核心能力：
- 支持 `legacy / compact / claude`
- 控制 `show_thinking/show_tool_args/show_timing/show_steps`
- 控制 `render_markdown`（终端基础 Markdown 渲染）
- 统一渲染：thinking、provider events、tool call/result、assistant 正文
- `claude` 样式下收敛输出噪音，默认突出“事件流 + 结果正文”

### 5.2 配置扩展
在配置中新增：
```yaml
ui:
  style: "claude"
  show_thinking: true
  show_tool_args: false
  show_timing: false
  show_steps: false
  render_markdown: true
```

### 5.3 CLI 覆盖参数
新增参数：
```bash
grape-agent --ui-style claude
grape-agent --ui-style compact
grape-agent --ui-style legacy
```

### 5.4 Agent 接入 renderer
`Agent` 构造支持传入 `ui_renderer`，`run()` 全部改为 renderer 驱动输出。

---

## 6. GLM-5 原生搜索接入（与 UI 改造并行）

### 6.1 配置入口
新增（已接入）：
```yaml
native_web_search:
  enabled: true
  model_patterns: ["glm-5"]
  tool_type: "web_search"
  web_search:
    enable: "True"
```

### 6.2 Provider 适配策略
- OpenAI 协议：注入 `type=web_search`。
- Anthropic 协议：自动映射为 `type=web_search_20250305` + `name=web_search`。
- 若新增原生工具后请求失败：自动回退重试（去掉原生工具）。

---

## 7. 本次改动文件清单

### 7.1 核心代码
- `grape_agent/schema/schema.py`
- `grape_agent/schema/__init__.py`
- `grape_agent/llm/anthropic_client.py`
- `grape_agent/llm/openai_client.py`
- `grape_agent/agent.py`
- `grape_agent/logger.py`
- `grape_agent/ui/renderer.py`
- `grape_agent/ui/__init__.py`
- `grape_agent/config.py`
- `grape_agent/cli.py`
- `grape_agent/config/config-example.yaml`
- `grape_agent/config/config.yaml`

### 7.2 测试
- `tests/test_config_native_web_search.py`
- `tests/test_llm_native_web_search.py`
- `tests/test_config_ui.py`
- `tests/test_ui_renderer.py`
- `tests/test_llm_provider_events.py`

---

## 8. 验收结果对照

### 验收项 1
**默认交互不再出现 `💭 Step x/y`**
- 结果：✅ 通过（默认 `ui.style=claude`, `show_steps=false`）

### 验收项 2
**原生 web_search 触发时，终端能看到 `Web Search(...)`**
- 结果：✅ 通过
- 示例：
  - `⏺ Web Search("OpenClaw latest version")`
  - `✓ Provider tool completed`

### 验收项 3
**bash/MCP/原生工具三类统一展示**
- 结果：✅ 通过（统一走 renderer 事件输出）

### 验收项 4
**长参数不刷屏，最终答案区域清晰**
- 结果：✅ 通过（默认参数摘要化；详情可通过 `show_tool_args=true` 打开）

### 验收项 5
**Markdown 输出在终端具备基础可读渲染（如粗体、表格）**
- 结果：✅ 通过（`render_markdown=true` 时生效）

---

## 9. 使用说明

### 9.1 推荐默认配置
```yaml
ui:
  style: "claude"
  show_thinking: true
  show_tool_args: false
  show_timing: false
  show_steps: false
  render_markdown: true
```

### 9.2 临时切换样式
```bash
uv run grape-agent --ui-style compact
uv run grape-agent --ui-style legacy
```

### 9.3 若要回到旧风格（接近原输出）
```yaml
ui:
  style: "legacy"
  show_timing: true
  show_steps: true
  show_tool_args: true
```
