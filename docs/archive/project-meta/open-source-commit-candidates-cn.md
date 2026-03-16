# 开源提交候选清单（当前工作区）

> 目标：把当前大量改动整理成可公开发布的 commit 方案。  
> 说明：当前工作区存在跨特性共改文件（如 `grape_agent/cli.py`、`grape_agent/config.py`），若追求高质量历史，建议使用 `git add -p` 分块提交。

## 1. 建议先决条件

1. 先确认私有内容已隔离：

```bash
git status --short --ignored | rg DEPLOY_ONEFILE
```

应看到 `docs/DEPLOY_ONEFILE_TENGXUN1_RUNBOOK_CN.md` 为 ignored（`!!`）。

2. 再跑一次去敏扫描：

```bash
rg -n "(api_key:|app_secret:|token:|PRIVATE KEY|118\.89\.73\.230|10\.200\.10\.24)" grape_agent browser_plugin docs README.md README_CN.md -S
```

## 2. 提交策略

## 2.1 策略 A（推荐给当前状态）：单次 Squash 提交

适用场景：改动跨度大、文件交叉多、你更看重“先发布开源版本”。

```bash
git add .
git commit -m "feat: open-source baseline with multi-agent runtime, channels, gateway, webterm bridge and docs"
```

优点：

- 操作最简单
- 风险最低（不容易漏文件）

缺点：

- commit 历史可读性一般

## 2.2 策略 B（推荐给想要清晰历史）：分批提交

下面给出可执行的候选批次。

---

## 3. 分批提交候选（B1 ~ B7）

## B1. Open Source Hygiene（去敏与仓库治理）

建议包含：

- `.gitignore`
- `README.md`
- `README_CN.md`
- `browser_plugin/chrome-webterm-agent/service_worker.js`
- `browser_plugin/chrome-webterm-agent/README.md`
- `grape_agent/config/config.yaml`
- `grape_agent/config/webterm_profiles.yaml`
- `docs/OPEN_SOURCE_PREP_CN.md`
- `docs/WEBTERM_BRIDGE_PLUGIN_QUICKSTART_CN.md`
- `tests/test_webterm_bridge_profiles.py`

建议命令：

```bash
git add .gitignore README.md README_CN.md
git add browser_plugin/chrome-webterm-agent/service_worker.js browser_plugin/chrome-webterm-agent/README.md
git add grape_agent/config/config.yaml grape_agent/config/webterm_profiles.yaml
git add docs/OPEN_SOURCE_PREP_CN.md docs/WEBTERM_BRIDGE_PLUGIN_QUICKSTART_CN.md
git add tests/test_webterm_bridge_profiles.py
git commit -m "chore: sanitize configs and prepare repository for open source"
```

---

## B2. Multi-Agent / Routing / Session 基础能力

建议包含：

- `grape_agent/agents/`
- `grape_agent/routing/`
- `grape_agent/session_store.py`
- `grape_agent/tools/sessions_spawn_tool.py`
- `grape_agent/tools/sessions_send_tool.py`
- `grape_agent/tools/sessions_list_tool.py`
- `grape_agent/tools/sessions_history_tool.py`
- `grape_agent/tools/tool_policy.py`
- `tests/test_agent_registry.py`
- `tests/test_routing_resolver.py`
- `tests/test_session_store.py`
- `tests/test_sessions_tools.py`
- `tests/test_subagent_orchestrator.py`

注意：`grape_agent/cli.py`、`grape_agent/runtime_factory.py` 涉及多特性，建议本批使用 `git add -p` 仅添加会话/编排相关片段。

提交信息建议：

```text
feat: add multi-agent profiles, routing and subagent orchestration
```

---

## B3. Channel Runtime + Feishu 插件化

建议包含：

- `grape_agent/channels/`
- `grape_agent/feishu/bridge.py`
- `grape_agent/feishu/client.py`
- `grape_agent/feishu/embedded_runner.py`
- `grape_agent/feishu/server_ws.py`
- `grape_agent/feishu/rendering.py`
- `tests/test_channels_runtime.py`
- `tests/test_feishu_bridge_routing.py`
- `tests/test_feishu_bridge_streaming.py`
- `tests/test_feishu_channel_plugin.py`
- `tests/test_config_feishu.py`

注意：`grape_agent/config.py`、`grape_agent/config/config-example.yaml` 也有 Feishu 配置变更，建议 `git add -p` 拆到该批。

提交信息建议：

```text
feat: pluginize channels and integrate embedded feishu runtime
```

---

## B4. Gateway 控制面 + Cron 调度

建议包含：

- `grape_agent/gateway/`
- `grape_agent/cron/`
- `tests/test_gateway_router.py`
- `tests/test_gateway_cron.py`
- `tests/test_config_gateway.py`
- `tests/test_config_cron.py`

注意：`grape_agent/cli.py`、`grape_agent/config.py`、`grape_agent/config/config-example.yaml` 相关片段建议用 `git add -p`。

提交信息建议：

```text
feat: add gateway control plane and cron scheduler execution pipeline
```

---

## B5. Webterm Bridge（HTTP -> Gateway）

建议包含：

- `grape_agent/webterm_bridge/`
- `tests/test_webterm_bridge_session_manager.py`
- `tests/test_webterm_bridge_utils.py`
- `tests/test_config_webterm_bridge.py`

可选包含（若你希望 bridge 相关配置同批）：

- `grape_agent/config/webterm_profiles.yaml`
- `grape_agent/config/config-example.yaml` 中 webterm 段

提交信息建议：

```text
feat: add webterm bridge service and gateway tcp client integration
```

---

## B6. Browser Plugin（Chrome Webterm Agent）

建议包含：

- `browser_plugin/chrome-webterm-agent/manifest.json`
- `browser_plugin/chrome-webterm-agent/content_script.js`
- `browser_plugin/chrome-webterm-agent/service_worker.js`
- `browser_plugin/chrome-webterm-agent/sidepanel.html`
- `browser_plugin/chrome-webterm-agent/sidepanel.js`
- `browser_plugin/chrome-webterm-agent/styles.css`
- `browser_plugin/chrome-webterm-agent/README.md`

提交信息建议：

```text
feat: add chrome webterm plugin for bridge-based agent interaction
```

---

## B7. 文档与依赖收尾

建议包含：

- `docs/AGENT_DESIGN_IMPLEMENTATION_GUIDE_CN.md`
- `docs/AGENT_BRIDGE_LINUX_DEPLOY_CN.md`
- `docs/BROWSER_BASTION_AGENT_ADAPTER_PLAN_CN.md`
- `docs/IM_PLUGIN_INTEGRATION_CN.md`
- `docs/ROADMAP_OPENCLAW_GAP.md`
- `docs/WEBTERM_BRIDGE_PLUGIN_QUICKSTART_CN.md`（若前面未提交）
- `docs/OPEN_SOURCE_PREP_CN.md`（若前面未提交）
- `pyproject.toml`
- `uv.lock`
- `tests/test_mcp.py`

提交信息建议：

```text
docs: add architecture guides, deployment notes and open source prep checklist
```

---

## 4. 暂不建议开源提交的内容

- `docs/DEPLOY_ONEFILE_TENGXUN1_RUNBOOK_CN.md`（已由 `.gitignore` 隔离）
- 任意本地私有配置文件：
  - `grape_agent/config/config.local.yaml`
  - `grape_agent/config/mcp.local.json`
  - `grape_agent/config/webterm_profiles.local.yaml`
- 办公/演示产物：`*.pptx`、本地总结文档

## 5. 最终发布前建议命令

```bash
# 1) 只看将被提交内容
git status --short

# 2) 跑关键测试（可按你实际时间裁剪）
pytest -q tests/test_gateway_router.py tests/test_feishu_channel_plugin.py tests/test_webterm_bridge_session_manager.py

# 3) 二次去敏扫描
rg -n "(api_key:|app_secret:|token:|PRIVATE KEY|118\.89\.73\.230|10\.200\.10\.24)" grape_agent browser_plugin docs README.md README_CN.md -S
```

