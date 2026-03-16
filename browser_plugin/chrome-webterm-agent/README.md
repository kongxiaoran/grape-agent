# Chrome Webterm Agent Plugin (MVP)

## 功能

- 自动创建并维护会话（默认随机 `host/scope/user`，支持一键刷新会话）
- 当前版本默认不采集终端上下文（仅基于模板提示词 + 用户输入）
- 支持配置并保存多套提示词模板（可切换，编辑区默认折叠）
- 支持导入 `.txt` 作为补充提示词
- 提供用户输入区与 agent 输出展示区

## 快速使用

1. 启动 `grape-agent`（需开启 gateway）。
2. 启动 `grape-agent-webterm-bridge`。
3. Chrome 打开 `chrome://extensions`，开启开发者模式，加载本目录。
4. 打开堡垒机页面，点击插件图标打开 side panel。
5. 插件会自动打开会话，不需要手动配置和手动打开。
6. 按需配置提示词后，在“用户输入”区提问并查看 agent 输出。

## 注意

- 插件现在默认放开 `http://*/*` 与 `https://*/*`，如需收敛权限可按实际堡垒机域名修改。
- 默认 bridge 地址和 token 分别是 `http://127.0.0.1:8766` 与 `change-me-webterm-bridge-token`。
- 可通过 `set_bridge_config` 在运行时动态覆盖，适配本地/远端桥接服务。
