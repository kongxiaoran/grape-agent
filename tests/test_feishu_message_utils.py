"""Unit tests for Feishu message helpers."""

from grape_agent.feishu.dedup import FeishuMessageDedup
from grape_agent.feishu.message_utils import chunk_text, parse_incoming_event, strip_bot_mentions
from grape_agent.feishu.types import FeishuMessageType


def test_parse_incoming_text_event_with_mentions():
    payload = {
        "sender": {"sender_id": {"open_id": "ou_user", "user_id": "u_user"}},
        "message": {
            "message_id": "om_1",
            "chat_id": "oc_1",
            "chat_type": "group",
            "message_type": "text",
            "content": '{"text":"@bot 你好"}',
            "mentions": [
                {
                    "key": "@bot",
                    "name": "bot",
                    "id": {"open_id": "ou_bot", "user_id": "u_bot"},
                }
            ],
        },
    }

    msg = parse_incoming_event(payload, bot_open_id="ou_bot")
    assert msg is not None
    assert msg.message_type == FeishuMessageType.TEXT
    assert msg.mentioned_bot is True
    assert msg.content == "@bot 你好"


def test_strip_bot_mentions():
    payload = {
        "sender": {"sender_id": {"open_id": "ou_user", "user_id": "u_user"}},
        "message": {
            "message_id": "om_2",
            "chat_id": "oc_2",
            "chat_type": "group",
            "message_type": "text",
            "content": '{"text":"@bot 帮我看下日志"}',
            "mentions": [
                {
                    "key": "@bot",
                    "name": "bot",
                    "id": {"open_id": "ou_bot"},
                }
            ],
        },
    }

    msg = parse_incoming_event(payload, bot_open_id="ou_bot")
    assert msg is not None
    cleaned = strip_bot_mentions(msg.content, msg.mentions, "ou_bot")
    assert cleaned == "帮我看下日志"


def test_chunk_text_prefers_newline():
    text = "line1\nline2\nline3\nline4"
    chunks = chunk_text(text, limit=10)
    assert len(chunks) >= 2
    assert all(chunk for chunk in chunks)


def test_dedup_persistent(tmp_path):
    dedup = FeishuMessageDedup(tmp_path / "dedup.json", ttl_seconds=3600)
    assert dedup.seen_or_record("chat:msg1") is False
    assert dedup.seen_or_record("chat:msg1") is True
