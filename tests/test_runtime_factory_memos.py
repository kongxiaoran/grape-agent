from pathlib import Path

from grape_agent.config import (
    AgentConfig,
    ChannelsConfig,
    Config,
    CronConfig,
    GatewayConfig,
    LLMConfig,
    MemOSConfig,
    ToolsConfig,
    WebtermBridgeConfig,
)
from grape_agent.runtime_factory import add_workspace_tools, create_turn_memory_hook


def _make_config(*, memos_enabled: bool, memos_api_key: str) -> Config:
    return Config(
        llm=LLMConfig(api_key="test-key", provider="anthropic", model="GLM-5"),
        agent=AgentConfig(),
        tools=ToolsConfig(enable_bash=False, enable_file_tools=False, enable_note=True, enable_skills=False, enable_mcp=False),
        channels=ChannelsConfig(),
        gateway=GatewayConfig(),
        cron=CronConfig(),
        webterm_bridge=WebtermBridgeConfig(),
        memos=MemOSConfig(enabled=memos_enabled, api_key=memos_api_key),
    )


def test_add_workspace_tools_uses_memos_when_enabled_with_key(tmp_path: Path):
    config = _make_config(memos_enabled=True, memos_api_key="mpg-test")
    tools = []

    add_workspace_tools(
        tools=tools,
        config=config,
        workspace_dir=tmp_path,
        include_recall_notes=True,
        channel="terminal",
        chat_id="main",
        agent_id="main",
    )

    names = [tool.name for tool in tools]
    assert "record_note" in names
    assert "recall_notes" in names
    assert "memos_record_note" in names
    assert "memos_recall_notes" in names


def test_add_workspace_tools_falls_back_local_note_when_memos_missing_key(tmp_path: Path):
    config = _make_config(memos_enabled=True, memos_api_key="")
    tools = []

    add_workspace_tools(
        tools=tools,
        config=config,
        workspace_dir=tmp_path,
        include_recall_notes=True,
        channel="terminal",
        chat_id="main",
        agent_id="main",
    )

    # Local note tools expose the same names but have memory_file attribute.
    note_tools = [tool for tool in tools if tool.name in {"record_note", "recall_notes"}]
    assert len(note_tools) == 2
    assert all(hasattr(tool, "memory_file") for tool in note_tools)
    names = [tool.name for tool in tools]
    assert "memos_record_note" not in names
    assert "memos_recall_notes" not in names


def test_add_workspace_tools_uses_local_note_when_memos_disabled(tmp_path: Path):
    config = _make_config(memos_enabled=False, memos_api_key="mpg-test")
    tools = []

    add_workspace_tools(
        tools=tools,
        config=config,
        workspace_dir=tmp_path,
        include_recall_notes=False,
        channel="terminal",
        chat_id="main",
        agent_id="main",
    )

    names = [tool.name for tool in tools]
    assert names.count("record_note") == 1
    assert "recall_notes" not in names
    assert "memos_record_note" not in names
    assert "memos_recall_notes" not in names


def test_create_turn_memory_hook_enabled(tmp_path: Path):
    config = _make_config(memos_enabled=True, memos_api_key="mpg-test")
    hook = create_turn_memory_hook(
        config=config,
        channel="terminal",
        chat_id="main",
        agent_id="main",
    )
    assert hook is not None
    assert hook.user_id == "terminal:main"
    assert hook.conversation_id == "terminal:main"


def test_create_turn_memory_hook_uses_sender_id_when_provided(tmp_path: Path):
    config = _make_config(memos_enabled=True, memos_api_key="mpg-test")
    hook = create_turn_memory_hook(
        config=config,
        channel="terminal",
        chat_id="main",
        sender_id="user_123",
        agent_id="main",
    )
    assert hook is not None
    assert hook.user_id == "terminal:main:user_123"
    assert hook.conversation_id == "terminal:main"


def test_create_turn_memory_hook_disabled_returns_none():
    config = _make_config(memos_enabled=False, memos_api_key="mpg-test")
    hook = create_turn_memory_hook(
        config=config,
        channel="terminal",
        chat_id="main",
        agent_id="main",
    )
    assert hook is None
