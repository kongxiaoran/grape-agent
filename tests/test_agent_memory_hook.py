from pathlib import Path

import pytest

from mini_agent.agent import Agent
from mini_agent.schema import LLMResponse, Message


class _DummyLLM:
    def __init__(self):
        self.calls: list[list[Message]] = []

    async def generate(self, messages: list[Message], tools=None):  # noqa: ARG002
        snapshot = [msg.model_copy(deep=True) for msg in messages]
        self.calls.append(snapshot)
        return LLMResponse(content="done", finish_reason="stop")


class _MemoryHook:
    def __init__(self):
        self.prepared: list[str] = []
        self.recorded: list[tuple[str, str, bool]] = []

    async def prepare_user_message(self, user_query: str) -> str:
        self.prepared.append(user_query)
        return f"<memories>\n  <facts>\n   - remember this\n  </facts>\n</memories>\n\nOriginal user query:\n{user_query}"

    async def record_turn(self, user_query: str, assistant_response: str, *, success: bool = True) -> None:
        self.recorded.append((user_query, assistant_response, success))


@pytest.mark.asyncio
async def test_agent_turn_memory_hook_injects_and_restores(tmp_path: Path):
    llm = _DummyLLM()
    hook = _MemoryHook()
    agent = Agent(
        llm_client=llm,
        system_prompt="system",
        tools=[],
        workspace_dir=str(tmp_path),
        turn_memory_hook=hook,
    )
    agent.add_user_message("你好")

    result = await agent.run()

    assert result == "done"
    assert hook.prepared == ["你好"]
    assert hook.recorded == [("你好", "done", True)]

    assert len(llm.calls) == 1
    first_call_user = [msg for msg in llm.calls[0] if msg.role == "user"][-1]
    assert isinstance(first_call_user.content, str)
    assert first_call_user.content.startswith("<memories>")
    assert "Original user query:\n你好" in first_call_user.content

    # Agent history should restore original user content after turn completion.
    latest_user = [msg for msg in agent.messages if msg.role == "user"][-1]
    assert latest_user.content == "你好"


@pytest.mark.asyncio
async def test_agent_turn_memory_hook_prepare_error_is_non_blocking(tmp_path: Path):
    class _BrokenPrepareHook(_MemoryHook):
        async def prepare_user_message(self, user_query: str) -> str:
            raise RuntimeError("prepare failed")

    llm = _DummyLLM()
    hook = _BrokenPrepareHook()
    agent = Agent(
        llm_client=llm,
        system_prompt="system",
        tools=[],
        workspace_dir=str(tmp_path),
        turn_memory_hook=hook,
    )
    agent.add_user_message("hello")

    result = await agent.run()

    assert result == "done"
    assert hook.recorded == [("hello", "done", True)]
    first_call_user = [msg for msg in llm.calls[0] if msg.role == "user"][-1]
    assert first_call_user.content == "hello"
