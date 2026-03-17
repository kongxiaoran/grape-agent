# 部署与运维（概念 / 原理 / 实现）

## 1) 目标与边界

部署运维关注三件事：

1. 服务可启动（启动链完整）
2. 状态可观测（健康、会话、通道、任务）
3. 版本可升级（配置外置、灰度、回滚）

本项目是“主进程 + 可选桥接进程”架构，不是分布式多服务平台。

## 2) 运行入口（以当前仓库为准）

`pyproject.toml` 中脚本入口：

- `grape-agent = grape_agent.cli:main`（`pyproject.toml:39`）
- `grape = grape_agent.cli:main`（`:40`）
- `grape-agent-feishu = grape_agent.feishu.server_ws:main`（`:42`）
- `grape-agent-webterm-bridge = grape_agent.webterm_bridge.server:main`（`:43`）

## 3) 配置发现与优先级

配置查找逻辑：

- `grape_agent/config.py:731`（`find_config_file`）
- `grape_agent/config.py:763`（`get_default_config_path`）

优先级（简化）：

1. `~/.grape-agent/config/settings.json`（推荐）
2. 开发目录 `./grape_agent/config/settings.json`
3. 安装包内默认配置

## 4) 运行拓扑建议

### 4.1 最小拓扑（本地开发）

1. `grape-agent`（CLI 主进程）

### 4.2 协作拓扑（常用）

1. `grape-agent`（主进程，内含 Gateway + Channel Runtime + Cron 可选）
2. `grape-agent-webterm-bridge`（独立 HTTP 进程，可选）

### 4.3 飞书接入方式

主进程通道插件模式（推荐）：随主进程生命周期管理。  
独立 `grape-agent-feishu` 入口通常用于单独运行/调试。

## 5) 启动链路（主进程）

在 `run_agent` 中按配置启用组件：

1. 初始化 channel runtime（`cli.py:1067`）
2. 可选启动 cron scheduler（`cli.py:1076`-`:1091`）
3. 启动 gateway server（`cli.py:1105`-`:1106`）
4. 创建 terminal 主会话（`cli.py:1108`）

退出时统一 stop：

- `cli.py:1447`-`:1455`

## 6) 关键配置项（运维最常改）

1. Gateway
   - `grape_agent/config.py:193`（`GatewayConfig`）
2. Cron
   - `grape_agent/config.py:202`（`CronConfig`）
3. Webterm Bridge
   - `grape_agent/config.py:212`（`WebtermBridgeConfig`）
4. Feishu Channel
   - `grape_agent/config.py:168`（`FeishuConfig`）

## 7) 运维可观测面

### 7.1 Gateway 状态总览

`status` 方法返回：

1. 服务 uptime
2. model/provider
3. sessions 总数
4. channels snapshot
5. gateway/subagent/cron 状态

实现：

- `grape_agent/gateway/handlers/status.py:8`

### 7.2 通道状态

- `channels.status` -> `ChannelRuntime.snapshot()`
- `grape_agent/gateway/handlers/channels.py:6`

### 7.3 Cron 状态

- `cron.status` -> scheduler snapshot
- `grape_agent/gateway/handlers/cron.py:8`

## 8) 标准检查清单（上线后必做）

1. `health` 与 `status` 可调用，返回 `ok=true`
2. `channels.status` 中启用通道 `running=true`
3. 若开启 cron，`cron.status.scheduler.running=true`
4. 主路径 smoke：CLI 对话、工具调用、退出清理
5. 若启 bridge：`GET /health` 返回 `{"status":"ok"}`

## 9) 升级与回滚建议

### 9.1 升级前

1. 备份 `settings.json` 与 cron store
2. 记录当前版本 commit/tag
3. 准备 smoke 用例（CLI / Gateway / Channel / Bridge）

### 9.2 升级后

1. 先跑 `status` 检查核心组件
2. 再跑 smoke 任务
3. 最后观察一段时间运行日志

### 9.3 回滚触发条件（建议）

1. Gateway 无法稳定响应
2. 通道入站明显丢失
3. Cron 大面积超时或失败

## 10) 打包与发布文档入口

当前仓库已提供：

1. 跨平台打包指南  
   `docs/09-deploy-ops/packaging-macos-windows-cn.md`
2. GitHub 发布 SOP  
   `docs/09-deploy-ops/sop-github-build-release-config-cn.md`
3. Linux onefile 实录（历史文档，含 `mini-agent` 命名）  
   `docs/DEPLOY_ONEFILE_TENGXUN1_RUNBOOK_CN.md`

说明：第 3 篇偏历史迁移记录，执行前请把命令中的 `mini-agent` 替换为当前 `grape-agent` 入口。

## 11) 常见故障与排查路径

1. 启动失败：先查配置路径是否命中，再查 API key/provider/model
2. Gateway 鉴权失败：核对 `gateway.auth.token` 与调用方 token
3. Bridge 502：通常是 bridge 连不上 gateway 或 method 调用报错
4. Feishu 无消息：查插件启动状态、账号配置、订阅权限与去重策略
5. Cron 不触发：查 `enabled/next_run_at/schedule` 与系统时间

## 12) 最小改造练习

1. 在 `status` 返回中新增版本号字段（从 `pyproject` 或环境变量读取）
2. 给 `CronDelivery` 增加按 job_id 的投递失败重试策略
3. 增加一个 `ops.smoke` Gateway 方法，一次性返回关键健康检查结果
