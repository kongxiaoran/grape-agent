# Webterm Bridge + Chrome 插件快速接入

## 1. 前提

- `grape-agent` 已可正常启动
- `gateway.enabled=true` 且 `gateway.auth.token` 已配置
- 本机安装 Chrome（或 Chromium 内核浏览器）

## 2. 配置

在 `grape_agent/config/config.yaml` 增加或确认：

```yaml
gateway:
  enabled: true
  host: "127.0.0.1"
  port: 8765
  auth:
    enabled: true
    token: "grape-agent-gateway-dev-token"

webterm_bridge:
  enabled: true
  host: "127.0.0.1"
  port: 8766
  token: "CHANGE_ME_WEBTERM_BRIDGE_TOKEN"
  # 可选：不填时自动复用 gateway.* 配置
  # gateway_host: "127.0.0.1"
  # gateway_port: 8765
  # gateway_token: "grape-agent-gateway-dev-token"
  parent_session_key: "agent:main:terminal:main"
  default_agent_id: "main"
  auto_execute_low_risk: false
  profile_path: "grape_agent/config/webterm_profiles.yaml"
```

如果当前环境还没有 bridge 运行依赖，请先安装：

```bash
pip install fastapi uvicorn
```

## 3. 启动

1. 启动 agent：

```bash
grape-agent
```

2. 新开一个终端，启动本地 bridge：

```bash
grape-agent-webterm-bridge
```

健康检查：

```bash
curl -s http://127.0.0.1:8766/health
```

## 4. 安装插件

插件目录：

`browser_plugin/chrome-webterm-agent`

安装步骤：

1. 打开 `chrome://extensions`
2. 开启开发者模式
3. 选择“加载已解压的扩展程序”
4. 选中 `browser_plugin/chrome-webterm-agent`

## 5. 首次使用流程

1. 打开堡垒机页面（需匹配 `manifest.json` 的 `matches`）
2. 点击插件图标打开 side panel
3. 插件会自动创建会话（随机 `host/scope/user`），无需手工打开
4. 在“提示词配置”里编辑并保存模板（支持导入 `.txt` 作为补充提示词）
5. 在“用户输入”区提问，插件会自动采集终端上下文并请求 agent
6. 在“Agent 输出”区查看回复
7. 如需重置会话，点击“刷新会话”

## 5.1 配置堡垒机场景画像（推荐）

文件：`grape_agent/config/webterm_profiles.yaml`

```yaml
profiles:
  - id: "neutral-crowd-log-center"
    match:
      host: "example-bastion.local"
      scope: "example-log-center"
      user: "example-user"
    summary: "example-service 日志中心画像（公开示例）"
    log_paths:
      - "/data/logs/example-service/app.log"
    log_patterns:
      - "app.log.*"
    command_hints:
      - "grep -nE 'ERROR|Exception' /data/logs/example-service/app.log | tail -n 200"
```

配置后，bridge 会把画像一起喂给 agent，建议命令会更贴近你的真实日志目录与规则。

## 6. 常见问题

1. side panel 显示 `401 unauthorized`
   - 检查 `Bridge Token` 是否与 `webterm_bridge.token` 一致

2. side panel 显示 `gateway connect failed`
   - 检查 `grape-agent` 是否已启动，且 gateway 在监听 `127.0.0.1:8765`

3. 插件抓不到终端输出
   - 检查当前页面是否是可注入扩展脚本的普通网页（不是 `chrome://` 等受限页面）
   - 检查堡垒机终端是否为 `xterm` 或类似 DOM 结构
   - 说明：`xterm` 的 `canvas` 通常没有可直接读取的文本，本插件会优先抓取 WebSocket 终端流，并用 DOM 文本做兜底
   - 若预览里主要是 `ping/pong`，说明抓到了传输心跳而非终端渲染内容；需要依赖 `xterm write` 采集路径

4. 命令注入失败
   - 终端输入组件选择器可能不匹配，需按实际页面改 `content_script.js` 的输入定位逻辑
   - 若终端在深层 iframe，先刷新该页面后重新“打开会话”
