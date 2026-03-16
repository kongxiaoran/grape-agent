# 运行时主循环（概念 / 原理 / 实现）

## 概念

运行时主循环负责把一次用户输入转成可执行步骤：

1. 发送消息给模型
2. 解析工具调用
3. 执行工具并回填结果
4. 继续迭代直到得到最终回答

## 原理

- 循环上限由 `max_steps` 控制，防止无限迭代
- 每轮执行前会检查上下文 token；仅当超过阈值时触发摘要，降低 token 膨胀风险
- 循环可以被取消（Esc / Ctrl+C）并做清理，保证会话一致性

## 实现

核心代码：

- `grape_agent/agent.py`
- `grape_agent/runtime_factory.py`

关键函数：

- `Agent.run()`：主循环
- `_summarize_messages()`：上下文压缩
- `build_runtime_bundle()`：运行时依赖装配（LLM + tools + prompt）

## 验证

1. 启动 `uv run grape-agent`
2. 输入一个会触发工具的问题
3. 观察是否出现 `tool call -> tool result -> final answer`

## 常见问题

- 模型不调用工具：优先检查 system prompt 与工具 schema
- 迭代过长：降低 `max_steps`，并优化提示词目标约束

## 代码行号引用

- 主循环与步数上限：`Agent.run()` 循环条件 `while step < self.max_steps`  
  `grape_agent/agent.py:322`, `grape_agent/agent.py:343`
- 摘要触发条件（超 token 阈值才执行）：`_summarize_messages()`  
  `grape_agent/agent.py:181`, `grape_agent/agent.py:199`, `grape_agent/agent.py:202`
- 取消与清理：`_check_cancelled()`、`_cleanup_incomplete_messages()`  
  `grape_agent/agent.py:91`, `grape_agent/agent.py:101`, `grape_agent/agent.py:345`, `grape_agent/agent.py:417`
