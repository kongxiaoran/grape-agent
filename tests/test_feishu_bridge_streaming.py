"""Tests for Feishu bridge progressive chunk streaming behavior."""

from __future__ import annotations

import json
import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from grape_agent.config import Config
from grape_agent.feishu.bridge import FeishuAgentBridge
from grape_agent.feishu.types import FeishuChatType, FeishuIncomingMessage, FeishuMessageType, FeishuSendResult


def _write_config(path: Path, content: dict) -> Path:
    path.write_text(json.dumps(content), encoding="utf-8")
    return path


def _build_config(
    tmp_path: Path,
    *,
    streaming_enabled: bool = False,
    chunk_size: int = 600,
    interval_ms: int = 0,
    reply_all_chunks: bool = False,
    progress_card_enabled: bool = False,
    progress_card_start_sec: int = 5,
    progress_card_update_sec: int = 3,
    progress_card_tail_lines: int = 5,
) -> Config:
    config_path = _write_config(
        tmp_path / "settings.json",
        {
            "api_key": "test-key",
            "channels": {
                "feishu": {
                    "enabled": True,
                    "default_account": "main",
                    "accounts": {
                        "main": {
                            "app_id": "cli_test",
                            "app_secret": "secret",
                        },
                    },
                    "render_mode": "raw",
                    "streaming": {
                        "enabled": streaming_enabled,
                        "chunk_size": chunk_size,
                        "interval_ms": interval_ms,
                        "reply_all_chunks": reply_all_chunks,
                        "progress_card_enabled": progress_card_enabled,
                        "progress_card_start_sec": progress_card_start_sec,
                        "progress_card_update_sec": progress_card_update_sec,
                        "progress_card_tail_lines": progress_card_tail_lines,
                    },
                },
            },
        },
    )
    return Config.from_json(config_path)


def _build_inbound() -> FeishuIncomingMessage:
    return FeishuIncomingMessage(
        message_id="om_in_1",
        chat_id="oc_chat_1",
        chat_type=FeishuChatType.P2P,
        message_type=FeishuMessageType.TEXT,
        content="hello",
        raw_content='{"text":"hello"}',
        sender_open_id="ou_user_1",
        sender_user_id="ou_user_1",
    )


class _DummyClient:
    def __init__(self):
        self.app_id = "cli_test"
        self.bot_open_id = None
        self.sent: list[tuple[str, str, str, str]] = []
        self.replied: list[tuple[str, str, str, bool]] = []
        self.updated: list[tuple[str, str, str]] = []

    async def send_message_content(self, receive_id: str, msg_type: str, content: str, receive_id_type: str = "chat_id"):
        self.sent.append((receive_id, msg_type, content, receive_id_type))
        return FeishuSendResult(success=True, message_id="om_sent")

    async def reply_message_content(
        self,
        message_id: str,
        msg_type: str,
        content: str,
        reply_in_thread: bool = False,
    ):
        self.replied.append((message_id, msg_type, content, reply_in_thread))
        return FeishuSendResult(success=True, message_id=f"om_reply_{len(self.replied)}")

    async def update_message_content(
        self,
        message_id: str,
        content: str,
        msg_type: str = "interactive",
    ):
        self.updated.append((message_id, msg_type, content))
        return FeishuSendResult(success=True, message_id=message_id)


class _FakeAgent:
    def __init__(self, delay_sec: float, tool_outputs: list[str] | None = None, result: str = "done"):
        self.delay_sec = delay_sec
        self.tool_outputs = tool_outputs or []
        self.result = result
        self.messages: list[SimpleNamespace] = [SimpleNamespace(role="system", content="sys"), SimpleNamespace(role="user", content="task")]

    async def run(self) -> str:
        tool_call = SimpleNamespace(function=SimpleNamespace(name="bash", arguments={"command": "echo run"}))
        self.messages.append(SimpleNamespace(role="assistant", content="", tool_calls=[tool_call]))
        for output in self.tool_outputs:
            self.messages.append(SimpleNamespace(role="tool", name="bash", content=output))
        await asyncio.sleep(self.delay_sec)
        self.messages.append(SimpleNamespace(role="assistant", content=self.result, tool_calls=None))
        return self.result


@pytest.mark.asyncio
async def test_bridge_chunk_reply_non_stream_mode(tmp_path):
    cfg = _build_config(tmp_path, streaming_enabled=False)
    bridge = FeishuAgentBridge(feishu_client=_DummyClient(), agent_config=cfg, workspace_root=tmp_path / "ws")
    inbound = _build_inbound()
    replied: list[str] = []

    async def _fake_reply(_inbound, text: str, prefer_reply: bool = True, force_text: bool = False):  # noqa: ARG001
        replied.append(text)

    bridge._reply = _fake_reply  # type: ignore[method-assign]
    await bridge._send_chunked_reply(inbound, "a" * 3200)

    assert len(replied) == 1
    assert replied[0].startswith("[1/2]\n")
    assert len(bridge.feishu_client.sent) == 1
    _, msg_type, content, receive_id_type = bridge.feishu_client.sent[0]
    assert msg_type == "post"
    assert receive_id_type == "chat_id"
    parsed = json.loads(content)
    assert "[2/2]" in parsed["zh_cn"]["content"][0][0]["text"]


@pytest.mark.asyncio
async def test_bridge_chunk_reply_stream_mode_with_send(monkeypatch, tmp_path):
    cfg = _build_config(
        tmp_path,
        streaming_enabled=True,
        chunk_size=500,
        interval_ms=10,
        reply_all_chunks=False,
    )
    bridge = FeishuAgentBridge(feishu_client=_DummyClient(), agent_config=cfg, workspace_root=tmp_path / "ws")
    inbound = _build_inbound()
    replied: list[str] = []
    sleep_calls: list[float] = []

    async def _fake_reply(_inbound, text: str, prefer_reply: bool = True, force_text: bool = False):  # noqa: ARG001
        replied.append(text)

    async def _fake_sleep(seconds: float):
        sleep_calls.append(seconds)

    monkeypatch.setattr("grape_agent.feishu.bridge.asyncio.sleep", _fake_sleep)
    bridge._reply = _fake_reply  # type: ignore[method-assign]
    await bridge._send_chunked_reply(inbound, "b" * 1200)

    assert len(replied) == 1
    assert len(bridge.feishu_client.sent) == 2
    assert len(sleep_calls) == 2


@pytest.mark.asyncio
async def test_bridge_chunk_reply_stream_mode_with_reply_all(monkeypatch, tmp_path):
    cfg = _build_config(
        tmp_path,
        streaming_enabled=True,
        chunk_size=500,
        interval_ms=5,
        reply_all_chunks=True,
    )
    bridge = FeishuAgentBridge(feishu_client=_DummyClient(), agent_config=cfg, workspace_root=tmp_path / "ws")
    inbound = _build_inbound()
    replied: list[str] = []
    sleep_calls: list[float] = []

    async def _fake_reply(_inbound, text: str, prefer_reply: bool = True, force_text: bool = False):  # noqa: ARG001
        replied.append(text)

    async def _fake_sleep(seconds: float):
        sleep_calls.append(seconds)

    monkeypatch.setattr("grape_agent.feishu.bridge.asyncio.sleep", _fake_sleep)
    bridge._reply = _fake_reply  # type: ignore[method-assign]
    await bridge._send_chunked_reply(inbound, "c" * 1200)

    assert len(replied) == 3
    assert len(bridge.feishu_client.sent) == 0
    assert len(sleep_calls) == 2


@pytest.mark.asyncio
async def test_bridge_progress_ping_loop_sends_keepalive(monkeypatch, tmp_path):
    cfg = _build_config(tmp_path, streaming_enabled=True)
    cfg.channels.feishu.streaming.progress_ping_sec = 1
    bridge = FeishuAgentBridge(feishu_client=_DummyClient(), agent_config=cfg, workspace_root=tmp_path / "ws")
    inbound = _build_inbound()
    replied: list[str] = []
    sleep_calls: list[float] = []

    async def _fake_reply(_inbound, text: str, prefer_reply: bool = True, force_text: bool = False):  # noqa: ARG001
        replied.append(text)

    async def _fake_sleep(seconds: float):
        sleep_calls.append(seconds)
        if len(sleep_calls) >= 2:
            raise asyncio.CancelledError

    monkeypatch.setattr("grape_agent.feishu.bridge.asyncio.sleep", _fake_sleep)
    bridge._reply = _fake_reply  # type: ignore[method-assign]

    with pytest.raises(asyncio.CancelledError):
        await bridge._progress_ping_loop(inbound)

    assert replied == ["还在处理中，请稍候…"]
    assert sleep_calls[0] == 1.0


@pytest.mark.asyncio
async def test_bridge_progress_card_not_created_for_short_task(tmp_path):
    cfg = _build_config(
        tmp_path,
        streaming_enabled=True,
        progress_card_enabled=True,
        progress_card_start_sec=2,
        progress_card_update_sec=1,
    )
    client = _DummyClient()
    bridge = FeishuAgentBridge(feishu_client=client, agent_config=cfg, workspace_root=tmp_path / "ws")
    session = SimpleNamespace(agent=_FakeAgent(delay_sec=0.1, tool_outputs=["one"]))
    inbound = _build_inbound()

    result = await bridge._run_agent_with_progress_ping(session, inbound)

    assert result == "done"
    assert client.replied == []
    assert client.updated == []


@pytest.mark.asyncio
async def test_bridge_progress_card_updates_with_tail_lines(tmp_path):
    cfg = _build_config(
        tmp_path,
        streaming_enabled=True,
        progress_card_enabled=True,
        progress_card_start_sec=1,
        progress_card_update_sec=1,
        progress_card_tail_lines=5,
    )
    client = _DummyClient()
    bridge = FeishuAgentBridge(feishu_client=client, agent_config=cfg, workspace_root=tmp_path / "ws")
    outputs = [f"line-{i}" for i in range(1, 8)]
    session = SimpleNamespace(agent=_FakeAgent(delay_sec=2.2, tool_outputs=outputs))
    inbound = _build_inbound()

    result = await bridge._run_agent_with_progress_ping(session, inbound)

    assert result == "done"
    assert len(client.replied) == 1
    assert client.replied[0][1] == "interactive"
    assert len(client.updated) >= 1

    _, _, final_content = client.updated[-1]
    parsed = json.loads(final_content)
    markdown = parsed["body"]["elements"][0]["content"]

    assert "任务已完成" in markdown
    assert "line-7" in markdown
    assert "line-1" not in markdown
