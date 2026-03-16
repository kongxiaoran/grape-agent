# Grape-Agent 开源整理与发布清单

本文档用于指导本仓库从“内部迭代状态”整理到“可公开开源状态”。

## 1. 当前目标

- 保留可复现、可学习、可扩展的核心能力
- 移除或隔离环境绑定内容（密钥、固定公网地址、私有部署记录）
- 给新贡献者提供稳定入口（文档、配置、目录职责）

## 2. 已落地的整理项

1. **插件默认配置去敏**
- 已将浏览器插件默认桥接地址/Token恢复为通用开发值：
  - `http://127.0.0.1:8766`
  - `change-me-webterm-bridge-token`
- 文件：`browser_plugin/chrome-webterm-agent/service_worker.js`

2. **运行时可覆盖恢复**
- `set_bridge_config` 重新支持动态覆盖，不再锁死到某个公网环境。
- 文件：`browser_plugin/chrome-webterm-agent/service_worker.js`

3. **本地配置去敏**
- `grape_agent/config/config.yaml` 已回退为 `config-example.yaml` 的安全示例内容（无真实 API Key / App Secret）。

4. **日志画像示例去私有化**
- `webterm_profiles.yaml` 中内网主机、账号、路径已替换为公开示例。
- 文件：`grape_agent/config/webterm_profiles.yaml`

5. **文档入口补齐**
- 新增架构入门文档并在 README 中建立入口：
  - `docs/AGENT_DESIGN_IMPLEMENTATION_GUIDE_CN.md`
  - `docs/OPEN_SOURCE_PREP_CN.md`

6. **`.gitignore` 增强**
- 增加本地私有配置、环境实录、办公产物的忽略规则。

## 3. 推荐目录职责（开源视角）

- `grape_agent/`：核心运行时代码（可开源）
- `browser_plugin/`：客户端插件（可开源）
- `docs/`：公开文档（可开源）
- `grape_agent/config/config-example.yaml`：唯一公开模板（可开源）
- `grape_agent/config/config.yaml`：建议仅用于本地（可保留为安全示例）
- `docs/private/`：私有部署文档（不建议开源）

## 4. 发布前必检清单（每次发版都要做）

1. **敏感信息扫描**

```bash
rg -n "(api_key:|app_secret:|token:|PRIVATE KEY|BEGIN RSA|AKIA|sk-[A-Za-z0-9]|cli_[A-Za-z0-9]{10,})" grape_agent browser_plugin docs README.md README_CN.md
```

2. **公网环境痕迹扫描**

```bash
rg -n "(118\.|10\.|172\.(1[6-9]|2[0-9]|3[0-1])\.|192\.168\.|tengxun|tianyi|bastion)" docs browser_plugin grape_agent -S
```

3. **确认 ignore 策略生效**

```bash
git status --short
```

确保私有 runbook、本地配置文件不会进入待提交列表。

4. **最小可运行验证**

```bash
uv sync
cp grape_agent/config/config-example.yaml grape_agent/config/config.yaml
# 填入自己的测试 key 后执行
uv run grape-agent --version
```

## 5. 本地私有文件命名建议

为减少误提交，建议将本地文件命名为：

- `grape_agent/config/config.local.yaml`
- `grape_agent/config/mcp.local.json`
- `grape_agent/config/webterm_profiles.local.yaml`
- `docs/private/*.md`

并保持这些路径在 `.gitignore` 内。

## 6. 开源协作约定（建议）

1. 所有示例配置必须使用占位符，不得写真实密钥。
2. 所有部署文档不得出现真实公网 IP、真实主机别名、真实账号。
3. 插件默认值必须指向本地开发地址，不得绑定真实生产环境。
4. 新增功能必须附带最小文档入口（至少在 README 的相关文档区可发现）。

