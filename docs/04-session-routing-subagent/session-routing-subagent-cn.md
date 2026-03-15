# 会话、路由与 Subagent（概念 / 原理 / 实现）

## 概念

该层决定“消息属于哪个会话”和“由哪个 agent 处理”，并支持子代理编排。

## 原理

- 会话键：`agent:{agent_id}:{channel}:{session_id}`
- 路由规则按 channel/account/chat 匹配目标 agent
- Subagent 工具提供跨会话调度能力，并受深度策略限制

## 实现

核心文件：

- `mini_agent/session_store.py`
- `mini_agent/routing/resolver.py`
- `mini_agent/routing/session_key.py`
- `mini_agent/agents/orchestrator.py`
- `mini_agent/tools/sessions_spawn_tool.py`
- `mini_agent/tools/sessions_send_tool.py`
- `mini_agent/tools/sessions_history_tool.py`
- `mini_agent/tools/sessions_list_tool.py`

关键策略：

- 每会话互斥锁，避免并发污染
- 子代理最大深度 `max_depth`，防止递归爆炸
- 叶子节点禁用敏感会话工具

## 验证

1. 配置两个 agent profile
2. 配置路由规则，将不同来源导向不同 agent
3. 执行 `sessions_spawn -> sessions_send` 验证子代理链路

## 代码行号引用

- 会话 key 规范：`agent:{agent_id}:{channel}:{chat_id}`  
  `mini_agent/routing/session_key.py:6`
- 路由解析与规则匹配：`RoutingResolver.resolve()`  
  `mini_agent/routing/resolver.py:11`, `mini_agent/routing/resolver.py:38`
- 会话存储与会话锁：`AgentSessionStore` / `AgentSession.lock`  
  `mini_agent/session_store.py:14`, `mini_agent/session_store.py:40`, `mini_agent/session_store.py:64`
- Subagent 编排与深度限制：`SessionOrchestrator.spawn()`  
  `mini_agent/agents/orchestrator.py:32`, `mini_agent/agents/orchestrator.py:53`, `mini_agent/agents/orchestrator.py:69`
- 叶子节点禁用会话工具策略：`SubagentPolicy`  
  `mini_agent/agents/policy.py:11`, `mini_agent/agents/policy.py:16`
