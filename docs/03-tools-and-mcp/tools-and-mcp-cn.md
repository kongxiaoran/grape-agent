# 工具系统与 MCP（概念 / 原理 / 实现）

## 概念

工具系统是 Agent 的执行面：模型决定“调用什么”，工具负责“真正执行”。

## 原理

- 每个工具暴露统一 schema（名称、参数、描述）
- Agent 按 `tool_call` 路由执行工具并回填结果
- MCP 工具作为外部扩展接入，统一纳入工具列表

## 实现

核心文件：

- `grape_agent/tools/base.py`
- `grape_agent/tools/file_tools.py`
- `grape_agent/tools/bash_tool.py`
- `grape_agent/tools/mcp_loader.py`
- `grape_agent/tools/skill_tool.py`

关键能力：

- 文件读写编辑工具（`read_file` / `write_file` / `edit_file`）
- Bash 工具（`bash` / `bash_output` / `bash_kill`）
- MCP 动态加载
- Skill 元数据注入与按需展开（`get_skill`）

## 验证

1. 问题触发 `read_file` / `write_file` / `bash` 任一工具
2. 检查输出结果与工具日志一致
3. 开启 MCP 后验证工具数量变化

## 常见问题

- MCP 工具未加载：检查 `mcp_config_path` 与超时配置
- Bash 风险命令：建议结合 allowlist/denylist 做策略限制

## 代码行号引用

- 工具抽象基类：`Tool` / `ToolResult`  
  `grape_agent/tools/base.py:8`
- 文件工具实现与真实工具名（`read_file/write_file/edit_file`）  
  `grape_agent/tools/file_tools.py:63`, `grape_agent/tools/file_tools.py:155`, `grape_agent/tools/file_tools.py:212`
- Bash 工具与后台进程相关工具（`bash`）  
  `grape_agent/tools/bash_tool.py:217`, `grape_agent/tools/bash_tool.py:238`
- MCP 动态加载与超时配置  
  `grape_agent/tools/mcp_loader.py:21`, `grape_agent/tools/mcp_loader.py:46`, `grape_agent/tools/mcp_loader.py:183`
- Skill 按需展开工具（`get_skill`）  
  `grape_agent/tools/skill_tool.py:13`, `grape_agent/tools/skill_tool.py:57`
