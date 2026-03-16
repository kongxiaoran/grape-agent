# 部署与运维（概念 / 原理 / 实现）

## 概念

部署层关注三件事：可启动、可观测、可升级。

## 原理

- 本地开发优先：`uv` 管理依赖与运行
- 服务器部署支持 systemd 常驻
- onefile 打包用于目标机简化部署

## 实现

参考文档：

- `docs/archive/ops/agent-bridge-linux-deploy-cn.md`
- `docs/DEPLOY_ONEFILE_TENGXUN1_RUNBOOK_CN.md`
- `docs/09-deploy-ops/packaging-macos-windows-cn.md`
- `docs/09-deploy-ops/sop-github-build-release-config-cn.md`
- `docs/archive/ops/production-guide-cn.md`

建议运行拓扑：

1. `grape-agent` 主服务
2. `grape-agent-webterm-bridge`（可选）
3. 飞书插件由主进程内启动

## 运行检查清单

1. `gateway.status` 正常
2. 飞书通道 `running=true`
3. bridge `/health` 正常
4. 日志目录可写，滚动策略有效

## 升级建议

- 先灰度新配置（尤其 token、路由、cron）
- 升级后先跑 smoke：CLI、Feishu、Gateway、Bridge 四条链路

## 代码行号引用

- 默认配置搜索顺序（`~/.grape-agent/config/settings.json` 优先）  
  `grape_agent/config.py:704`, `grape_agent/config.py:712`
- 启动入口与主循环  
  `grape_agent/cli.py:1302`, `grape_agent/cli.py:1327`
- Gateway 启停与状态输出  
  `grape_agent/cli.py:994`, `grape_agent/gateway/server.py:27`, `grape_agent/gateway/server.py:41`
- Feishu 通道随主进程生命周期启动/停止  
  `grape_agent/cli.py:956`, `grape_agent/cli.py:1293`, `grape_agent/channels/runtime.py:21`, `grape_agent/channels/runtime.py:38`
- Webterm Bridge 独立服务入口  
  `grape_agent/webterm_bridge/server.py:163`
