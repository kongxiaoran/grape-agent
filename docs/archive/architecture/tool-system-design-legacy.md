# Mini-Agent 工具系统设计文档

本文档详细解释 Mini-Agent 中"工具"的本质、实现方式以及注入机制。

---

## 1. 工具的本质

### 1.1 工具是什么？

**工具是一个 Python 类，不是 Markdown，不是纯提示词！**

每个工具都继承自 `Tool` 基类，包含以下核心部分：

| 部分 | 作用 | 示例 |
|------|------|------|
| `name` | 工具的名称（LLM 调用时用） | `"read_file"` |
| `description` | 工具的功能描述（告诉 LLM 这个工具是干嘛的） | `"Read file contents from the filesystem..."` |
| `parameters` | 参数定义（JSON Schema 格式，告诉 LLM 需要传什么参数） | `{"path": "string", "offset": "integer"}` |
| `execute()` | **真正执行的代码**（Python 函数！） | 读取文件、执行命令等 |

### 1.2 Tool 基类定义

```python
class Tool:
    """Base class for all tools."""

    @property
    def name(self) -> str:
        """Tool name."""
        raise NotImplementedError

    @property
    def description(self) -> str:
        """Tool description."""
        raise NotImplementedError

    @property
    def parameters(self) -> dict[str, Any]:
        """Tool parameters schema (JSON Schema format)."""
        raise NotImplementedError

    async def execute(self, *args, **kwargs) -> ToolResult:
        """Execute the tool with arbitrary arguments."""
        raise NotImplementedError
```

### 1.3 具体示例：ReadTool

```python
class ReadTool(Tool):
    """Read file content."""

    def __init__(self, workspace_dir: str = "."):
        self.workspace_dir = Path(workspace_dir).absolute()

    @property
    def name(self) -> str:
        return "read_file"

    @property
    def description(self) -> str:
        return "Read file contents from the filesystem..."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "..."},
                "offset": {"type": "integer", "description": "..."},
                "limit": {"type": "integer", "description": "..."},
            },
            "required": ["path"],
        }

    async def execute(self, path: str, offset: int | None = None, limit: int | None = None) -> ToolResult:
        """真正执行读取文件的代码！"""
        try:
            file_path = Path(path)
            if not file_path.is_absolute():
                file_path = self.workspace_dir / file_path
            
            with open(file_path, encoding="utf-8") as f:
                lines = f.readlines()
            
            # ... 处理逻辑 ...
            
            return ToolResult(success=True, content=content)
        except Exception as e:
            return ToolResult(success=False, content="", error=str(e))
```

---

## 2. 工具的注入机制

### 2.1 注入的本质

**简单说：就是把 Tool 类的实例添加到一个 Python 列表里！**

### 2.2 注入流程

#### 第一步：定义 Tool 类

```python
class ReadTool(Tool):
    @property
    def name(self): return "read_file"
    
    async def execute(self, path):
        # 真正的代码逻辑
        return ToolResult(...)
```

#### 第二步：创建 Tool 实例

```python
read_tool = ReadTool(workspace_dir="/path/to/workspace")
# 这是一个 Python 对象！
```

#### 第三步：添加到列表

```python
tools: list[Tool] = []
tools.append(read_tool)   # ← 就是 list.append()！
tools.append(BashTool(...))
tools.append(WriteTool(...))
```

#### 第四步：传给 Agent

```python
agent = Agent(
    llm_client=llm_client,
    tools=tools,        # ← 工具列表传给 Agent
    ...
)
```

#### 第五步：Agent 使用工具

1. 每轮把 tools 转成 schema 发给 LLM
2. LLM 返回 tool_calls: `[{"name": "read_file", "arguments": {"path": "xxx"}}]`
3. Agent 根据 name 找到对应的 Tool 实例
4. 调用 `tool.execute(**arguments)`

### 2.3 代码层面的注入

在 `runtime_factory.py` 中，`build_session_tools` 函数负责构建工具列表：

```python
def build_session_tools(
    *,
    base_tools: list[Tool],      # ← 基础工具列表
    config: Config,
    workspace_dir: Path,
    extra_tools: list[Tool] | None = None,  # ← 额外工具
    ...
) -> list[Tool]:
    """Build a session-scoped tool list."""
    
    tools = list(base_tools)     # 1. 复制基础工具
    
    add_workspace_tools(
        tools=tools,             # 2. 把工具列表传进去，往里面添加
        config=config,
        workspace_dir=workspace_dir,
    )
    
    if extra_tools:
        tools.extend(extra_tools)  # 3. 添加额外工具（如会话编排工具）
    
    return tools   # ← 返回最终的工具列表
```

`add_workspace_tools` 函数实际添加工具：

```python
def add_workspace_tools(tools: list[Tool], config: Config, workspace_dir: Path, ...):
    """Add workspace-dependent tools to a session tool list."""
    
    if config.tools.enable_bash:
        tools.append(BashTool(workspace_dir=str(workspace_dir)))   # ← 往列表里添加！

    if config.tools.enable_file_tools:
        tools.extend([                                             # ← 批量添加！
            ReadTool(workspace_dir=str(workspace_dir)),
            WriteTool(workspace_dir=str(workspace_dir)),
            EditTool(workspace_dir=str(workspace_dir)),
        ])
```

---

## 3. LLM 如何"看到"工具

Agent 会把工具转换成 schema 发给 LLM：

```python
def to_schema(self) -> dict[str, Any]:
    """Convert tool to Anthropic tool schema."""
    return {
        "name": self.name,
        "description": self.description,
        "input_schema": self.parameters,
    }
```

LLM 收到的是这样的 JSON：

```json
{
  "name": "read_file",
  "description": "Read file contents from the filesystem...",
  "input_schema": {
    "type": "object",
    "properties": {
      "path": {"type": "string"},
      "offset": {"type": "integer"},
      "limit": {"type": "integer"}
    },
    "required": ["path"]
  }
}
```

LLM 根据这个描述决定要不要调用，以及传什么参数。

---

## 4. 完整流程图

```
┌─────────────────────────────────────────────────────────────┐
│  1. 定义 Tool 类（继承 Tool 基类）                              │
│     class ReadTool(Tool):                                    │
│         @property                                            │
│         def name(self): return "read_file"                   │
│                                                                │
│         async def execute(self, path):                       │
│             # 真正的代码逻辑                                    │
│             return ToolResult(...)                            │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│  2. 创建 Tool 实例                                             │
│     read_tool = ReadTool(workspace_dir="/path/to/workspace") │
│     # 这是一个 Python 对象！                                    │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│  3. 添加到列表                                                 │
│     tools: list[Tool] = []                                   │
│     tools.append(read_tool)   # ← 就是 list.append()！        │
│     tools.append(BashTool(...))                              │
│     tools.append(WriteTool(...))                             │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│  4. 传给 Agent                                                │
│     agent = Agent(                                           │
│         llm_client=llm_client,                               │
│         tools=tools,        # ← 工具列表传给 Agent             │
│         ...                                                  │
│     )                                                        │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│  5. Agent 使用工具                                             │
│     - 每轮把 tools 转成 schema 发给 LLM                       │
│     - LLM 返回 tool_calls: [{"name": "read_file", "arguments": {"path": "xxx"}}] │
│     - Agent 根据 name 找到对应的 Tool 实例                     │
│     - 调用 tool.execute(**arguments)                          │
└─────────────────────────────────────────────────────────────┘
```

---

## 5. 总结

| 问题 | 答案 |
|------|------|
| 工具是 Markdown 吗？ | **不是**，是 Python 类 |
| 工具是提示词吗？ | **不完全是**，`description` 是给 LLM 看的提示词，但 `execute()` 是真正的 Python 代码 |
| 怎么注入的？ | **就是 `list.append()`**，把 Tool 实例添加到列表 |
| 工具怎么执行？ | Agent 根据 LLM 返回的 `name` 找到 Tool 实例，调用 `execute()` 方法 |

---

## 6. 相关源码文件

- `grape_agent/tools/base.py` - Tool 基类定义
- `grape_agent/tools/file_tools.py` - 文件操作工具（ReadTool/WriteTool/EditTool）
- `grape_agent/tools/bash_tool.py` - Shell 命令工具
- `grape_agent/runtime_factory.py` - 工具注入和装配逻辑
