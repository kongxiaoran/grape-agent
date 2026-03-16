"""Tests for provider-native event parsing."""

from types import SimpleNamespace

from grape_agent.llm.anthropic_client import AnthropicClient


def test_anthropic_parse_response_provider_events():
    client = AnthropicClient(
        api_key="test-key",
        api_base="https://example.invalid/anthropic",
        model="GLM-5",
    )

    fake_response = SimpleNamespace(
        content=[
            SimpleNamespace(type="server_tool_use", id="tool_1", name="web_search_prime", input={"search_query": "openclaw"}),
            SimpleNamespace(type="tool_result", tool_use_id="tool_1", content=[{"text": "result"}]),
            SimpleNamespace(type="text", text="done"),
        ],
        usage=None,
        stop_reason="end_turn",
    )

    parsed = client._parse_response(fake_response)

    assert parsed.content == "done"
    assert parsed.provider_events is not None
    assert len(parsed.provider_events) == 2
    assert parsed.provider_events[0].event_type == "server_tool_use"
    assert parsed.provider_events[0].name == "web_search_prime"
    assert parsed.provider_events[1].event_type == "tool_result"
