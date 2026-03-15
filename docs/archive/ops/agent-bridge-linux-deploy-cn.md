# Grape-Agent + Webterm Bridge 打包与 Linux 部署指南

本文档覆盖两件事：
1. 本地环境如何启动 `grape-agent` 与 `grape-agent-webterm-bridge`
2. 如何在 Linux 服务器部署（含打包成 Linux 可执行）

## 1. 组件关系

- `grape-agent`：主进程，负责模型对话、工具调用、Gateway 控制面。
- `grape-agent-webterm-bridge`：本地 HTTP 桥接服务，供浏览器插件调用，再通过 Gateway 转发到 Agent。
- `Feishu` 插件：由 `grape-agent` 进程内自动拉起（当 `channels.feishu.enabled=true`），不需要单独起第三个进程。

## 2. 配置文件位置规则

程序会按以下优先级查找 `config.yaml`：

1. `./mini_agent/config/config.yaml`（开发目录）
2. `~/.grape-agent/config/config.yaml`（当前运行用户）
3. 包安装目录内 `mini_agent/config/config.yaml`

生产环境建议使用第 2 种（用户级配置目录）。

## 3. 本地环境启动（开发/联调）

## 3.1 准备

```bash
git clone <your-repo-url> Grape-Agent
cd Grape-Agent

# 安装依赖
uv sync

# 初始化配置
cp mini_agent/config/config-example.yaml mini_agent/config/config.yaml
```

编辑 `mini_agent/config/config.yaml`，至少确认这些字段：

```yaml
api_key: "<YOUR_LLM_API_KEY>"
api_base: "<YOUR_API_BASE>"
model: "<YOUR_MODEL>"
provider: "anthropic"

gateway:
  enabled: true
  host: "127.0.0.1"
  port: 8765
  auth:
    enabled: true
    token: "<STRONG_GATEWAY_TOKEN>"

webterm_bridge:
  enabled: true
  host: "127.0.0.1"
  port: 8766
  token: "<STRONG_BRIDGE_TOKEN>"
  # 不填时默认复用 gateway.host/port/token

channels:
  feishu:
    enabled: true
    default_account: "main"
    accounts:
      main:
        app_id: "<FEISHU_APP_ID>"
        app_secret: "<FEISHU_APP_SECRET>"
        domain: "feishu"
```

## 3.2 启动

终端 1：

```bash
uv run grape-agent
```

终端 2：

```bash
uv run grape-agent-webterm-bridge
```

## 3.3 验证

1. 验证 Bridge：

```bash
curl -s http://127.0.0.1:8766/health
```

预期返回：`{"status":"ok","service":"webterm-bridge"}`。

2. 验证 Gateway TCP（JSON 行协议）：

```bash
printf '%s\n' '{"id":"health-1","method":"health","params":{},"auth":{"token":"<STRONG_GATEWAY_TOKEN>","client_id":"manual-test","role":"operator"}}' \
  | nc 127.0.0.1 8765
```

预期返回包含：`"ok": true`。

## 4. Linux 服务器部署（推荐：源码 + systemd）

这种方式最稳妥，升级和排障成本最低。

## 4.1 服务器准备

```bash
# 以 root 执行
useradd -m -s /bin/bash miniagent
mkdir -p /opt/grape-agent
chown -R miniagent:miniagent /opt/grape-agent
```

切换到 `miniagent` 用户：

```bash
sudo -iu miniagent
cd /opt/grape-agent

git clone <your-repo-url> .
uv sync

mkdir -p ~/.grape-agent/config
cp mini_agent/config/config-example.yaml ~/.grape-agent/config/config.yaml
```

编辑 `~/.grape-agent/config/config.yaml`（同本地章节）。

## 4.2 systemd 服务文件

创建 `/etc/systemd/system/grape-agent.service`：

```ini
[Unit]
Description=Grape-Agent Service
After=network.target

[Service]
Type=simple
User=miniagent
Group=miniagent
WorkingDirectory=/opt/grape-agent
ExecStart=/opt/grape-agent/.venv/bin/grape-agent
Restart=always
RestartSec=3
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```

创建 `/etc/systemd/system/grape-agent-webterm-bridge.service`：

```ini
[Unit]
Description=Grape-Agent Webterm Bridge
After=network.target grape-agent.service
Requires=grape-agent.service

[Service]
Type=simple
User=miniagent
Group=miniagent
WorkingDirectory=/opt/grape-agent
ExecStart=/opt/grape-agent/.venv/bin/grape-agent-webterm-bridge --config /home/miniagent/.grape-agent/config/config.yaml
Restart=always
RestartSec=3
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```

加载并启动：

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now grape-agent.service
sudo systemctl enable --now grape-agent-webterm-bridge.service
```

检查状态与日志：

```bash
systemctl status grape-agent --no-pager
systemctl status grape-agent-webterm-bridge --no-pager
journalctl -u grape-agent -f
journalctl -u grape-agent-webterm-bridge -f
```

## 5. 打包成 Linux 可执行（PyInstaller）

说明：
- 需要在目标同架构 Linux 上打包（例如都为 `x86_64 + glibc`）。
- 会生成两个可执行文件：`grape-agent`、`grape-agent-webterm-bridge`。
- 配置文件仍建议放在 `/home/miniagent/.grape-agent/config/config.yaml`。

## 5.1 安装打包工具

```bash
cd /opt/grape-agent
uv sync
uv run pip install pyinstaller
mkdir -p build/entrypoints
```

## 5.2 创建打包入口

`build/entrypoints/mini_agent_main.py`：

```python
from mini_agent.cli import main

if __name__ == "__main__":
    main()
```

`build/entrypoints/mini_agent_bridge_main.py`：

```python
from mini_agent.webterm_bridge.server import main

if __name__ == "__main__":
    main()
```

## 5.3 执行打包

```bash
cd /opt/grape-agent

uv run pyinstaller --clean --onefile \
  --name grape-agent \
  --collect-all mini_agent \
  build/entrypoints/mini_agent_main.py

uv run pyinstaller --clean --onefile \
  --name grape-agent-webterm-bridge \
  --collect-all mini_agent \
  build/entrypoints/mini_agent_bridge_main.py
```

产物路径：

- `dist/grape-agent`
- `dist/grape-agent-webterm-bridge`

## 5.4 可执行版 systemd

把二进制放到 `/opt/grape-agent/bin/` 后，服务文件可改为：

```ini
# grape-agent.service
ExecStart=/opt/grape-agent/bin/grape-agent

# grape-agent-webterm-bridge.service
ExecStart=/opt/grape-agent/bin/grape-agent-webterm-bridge --config /home/miniagent/.grape-agent/config/config.yaml
```

其他字段保持不变，重新加载并重启：

```bash
sudo systemctl daemon-reload
sudo systemctl restart grape-agent grape-agent-webterm-bridge
```

## 6. 升级流程建议

## 6.1 源码部署升级

```bash
sudo -iu miniagent
cd /opt/grape-agent
git pull
uv sync
sudo systemctl restart grape-agent grape-agent-webterm-bridge
```

## 6.2 可执行部署升级

1. 在同版本 Linux 构建新二进制。
2. 替换 `/opt/grape-agent/bin/grape-agent*`。
3. 重启两个服务。

## 7. 常见问题

1. `401 unauthorized`（Bridge 调用失败）
- 检查插件里 `Bridge Token` 与 `webterm_bridge.token` 是否一致。

2. Bridge 报 `gateway connect failed`
- 检查 `grape-agent` 是否已启动。
- 检查 `gateway.enabled=true` 且端口监听在 `127.0.0.1:8765`。

3. Feishu 无回复
- 检查 `channels.feishu.enabled=true`。
- 检查 `app_id/app_secret` 是否正确。
- 查看 `journalctl -u grape-agent -f` 日志中是否有鉴权失败。

4. 打包后二进制启动报缺模块
- 重新打包并确保使用 `--collect-all mini_agent`。
- 在目标机与打包机保持一致的 Python/系统架构。
