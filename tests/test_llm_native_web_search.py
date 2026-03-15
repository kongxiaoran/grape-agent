"""Unit tests for model-native web search tool injection."""

import asyncio
from types import SimpleNamespace

from mini_agent.llm.anthropic_client import AnthropicClient
from mini_agent.llm.openai_client import OpenAIClient


class _CreateRecorder:
    def __init__(self, fail_on_web_search_once: bool = False):
        self.calls: list[dict] = []
        self.fail_on_web_search_once = fail_on_web_search_once
        self._failed = False

    async def __call__(self, **kwargs):
        self.calls.append(kwargs)
        tools = kwargs.get("tools") or []
        has_web_search = any(
            isinstance(t, dict) and str(t.get("type", "")).startswith("web_search")
            for t in tools
        )
        if self.fail_on_web_search_once and has_web_search and not self._failed:
            self._failed = True
            raise RuntimeError("unsupported tool type web_search")
        return SimpleNamespace(ok=True)


def test_openai_injects_native_web_search_for_glm5():
    client = OpenAIClient(
        api_key="test-key",
        api_base="https://example.invalid/v1",
        model="GLM-5",
        native_web_search={
            "enabled": True,
            "model_patterns": ["glm-5"],
            "tool_type": "web_search",
            "web_search": {"enable": "True"},
        },
    )
    recorder = _CreateRecorder()
    client.client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=recorder))
    )

    asyncio.run(
        client._make_api_request(
            api_messages=[{"role": "user", "content": "hello"}],
            tools=[
                {
                    "name": "get_weather",
                    "description": "Get weather",
                    "input_schema": {"type": "object", "properties": {}, "required": []},
                }
            ],
        )
    )

    assert len(recorder.calls) == 1
    tools = recorder.calls[0]["tools"]
    assert any(t.get("type") == "web_search" for t in tools)
    assert any(t.get("type") == "function" for t in tools)


def test_openai_no_native_web_search_when_model_not_matched():
    client = OpenAIClient(
        api_key="test-key",
        api_base="https://example.invalid/v1",
        model="MiniMax-M2.5",
        native_web_search={
            "enabled": True,
            "model_patterns": ["glm-5"],
            "tool_type": "web_search",
            "web_search": {"enable": "True"},
        },
    )
    recorder = _CreateRecorder()
    client.client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=recorder))
    )

    asyncio.run(
        client._make_api_request(
            api_messages=[{"role": "user", "content": "hello"}],
            tools=None,
        )
    )

    assert len(recorder.calls) == 1
    assert "tools" not in recorder.calls[0]


def test_anthropic_fallback_without_native_web_search_on_error():
    client = AnthropicClient(
        api_key="test-key",
        api_base="https://example.invalid/anthropic",
        model="GLM-5",
        native_web_search={
            "enabled": True,
            "model_patterns": ["glm-5"],
            "tool_type": "web_search",
            "web_search": {"enable": "True"},
        },
    )
    recorder = _CreateRecorder(fail_on_web_search_once=True)
    client.client = SimpleNamespace(messages=SimpleNamespace(create=recorder))

    asyncio.run(
        client._make_api_request(
            system_message="system",
            api_messages=[{"role": "user", "content": "hello"}],
            tools=[
                {
                    "name": "get_weather",
                    "description": "Get weather",
                    "input_schema": {"type": "object", "properties": {}, "required": []},
                }
            ],
        )
    )

    assert len(recorder.calls) == 2
    first_tools = recorder.calls[0]["tools"]
    second_tools = recorder.calls[1]["tools"]
    assert any(str(t.get("type", "")).startswith("web_search") for t in first_tools)
    assert any(t.get("type") == "web_search_20250305" for t in first_tools if isinstance(t, dict))
    assert any(t.get("name") == "web_search" for t in first_tools if isinstance(t, dict))
    assert not any(str(t.get("type", "")).startswith("web_search") for t in second_tools)
