# CLI 与终端交互 UI（概念 / 原理 / 实现）

## 概念

CLI 是本项目最直接的学习入口。UI 目标是“简洁、可观测、低噪音”。

## 原理

- 借鉴 Claude Code 风格：输入黑底白字、紧凑工具事件、thinking 动态行
- 默认不刷 step 框，突出关键行为（thinking、tool、answer）
- token 显示仅使用 API 返回 usage，不做估算

## 实现

核心文件：

- `mini_agent/cli.py`
- `mini_agent/ui/renderer.py`

重构点：

- 启动欢迎卡片重排（品牌 + runtime 信息）
- 输入回显与提示符清理
- thinking 行每秒刷新，结束后显示真实 token
- `/help`、`/clear`、`/log`、`/exit` 命令体验优化

## 验证

1. 运行 `uv run grape-agent`
2. 输入短问题，观察 thinking 行与 token 显示
3. 用 Ctrl+C 退出，确认无 traceback 噪音

## 代码行号引用

- UI 选项与样式（`legacy/compact/claude`）  
  `mini_agent/ui/renderer.py:36`, `mini_agent/ui/renderer.py:74`
- thinking 动态行刷新（1s）与结束 token 展示  
  `mini_agent/ui/renderer.py:111`, `mini_agent/ui/renderer.py:137`, `mini_agent/ui/renderer.py:144`, `mini_agent/ui/renderer.py:159`
- 工具事件紧凑展示（provider/tool）  
  `mini_agent/ui/renderer.py:184`, `mini_agent/ui/renderer.py:190`, `mini_agent/ui/renderer.py:211`, `mini_agent/ui/renderer.py:230`
- CLI 输入框与 `/help`、`/clear`、`/log`、`/exit` 命令处理  
  `mini_agent/cli.py:1047`, `mini_agent/cli.py:1085`, `mini_agent/cli.py:1148`, `mini_agent/cli.py:1152`, `mini_agent/cli.py:1178`
- Ctrl+C 退出时清理（gateway/channels/cron/MCP）  
  `mini_agent/cli.py:1278`, `mini_agent/cli.py:1287`
