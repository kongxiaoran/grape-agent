# 模型接入与提示词注入（概念 / 原理 / 实现）

## 概念

该层负责统一不同模型协议（Anthropic/OpenAI 风格）并输出统一 `LLMResponse`。

## 原理

- 配置中心决定 provider、model、api_base、retry
- 请求前注入运行时身份与规则（模型披露、日期策略、搜索策略）
- 响应后标准化为：`content`, `tool_calls`, `usage`, `provider_events`（其中 `provider_events` 主要由 Anthropic 侧 server tool 事件提供）

## 实现

核心文件：

- `grape_agent/llm/anthropic_client.py`
- `grape_agent/llm/openai_client.py`
- `grape_agent/runtime_factory.py`
- `grape_agent/schema/schema.py`

关键点：

- `TokenUsage` 已区分 `prompt/completion/total`
- Anthropic cache token 单独记录，不混入 `total_tokens`
- Native web search 按模型匹配策略启用

## 验证

1. 使用支持联网的模型
2. 发起“最新信息”查询
3. 观察 provider event 与 usage 输出是否合理

## 常见问题

- 422 工具参数错误：检查 provider 对 tool schema 的要求差异
- 日期答非所问：检查运行时日期注入与系统提示词规则

## 代码行号引用

- 运行时身份与日期护栏注入：`apply_runtime_identity_prompt()`  
  `grape_agent/runtime_factory.py:70`
- LLM 客户端构建与 provider/model 选择：`create_llm_client()`  
  `grape_agent/runtime_factory.py:41`, `grape_agent/runtime_factory.py:53`, `grape_agent/runtime_factory.py:55`
- 统一响应结构定义（`LLMResponse` / `TokenUsage` / `ProviderEvent`）  
  `grape_agent/schema/schema.py:40`, `grape_agent/schema/schema.py:50`, `grape_agent/schema/schema.py:59`
- Anthropic provider events 与 usage 解析  
  `grape_agent/llm/anthropic_client.py:294`, `grape_agent/llm/anthropic_client.py:322`
- OpenAI usage 解析（provider_events 当前为 `None`）  
  `grape_agent/llm/openai_client.py:289`, `grape_agent/llm/openai_client.py:302`
