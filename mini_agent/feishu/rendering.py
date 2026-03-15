"""Feishu outbound rendering helpers.

Aligns with OpenClaw-style render mode:
- raw  -> post
- card -> interactive markdown card
- auto -> interactive for code-block/table, otherwise post
"""

from __future__ import annotations

import json
import re
from typing import Literal

RenderMode = Literal["auto", "raw", "card"]
MessageType = Literal["text", "post", "interactive"]


def should_use_card(text: str) -> bool:
    """Detect markdown patterns that are better rendered as interactive card."""
    return bool(re.search(r"```[\s\S]*?```", text) or re.search(r"\|.+\|[\r\n]+\|[-:| ]+\|", text))


def resolve_message_type(text: str, render_mode: RenderMode) -> MessageType:
    if render_mode == "card":
        return "interactive"
    if render_mode == "raw":
        return "post"
    if should_use_card(text):
        return "interactive"
    return "post"


def build_post_payload(text: str) -> str:
    payload = {
        "zh_cn": {
            "title": "",
            "content": [[{"tag": "md", "text": text}]],
        },
        "en_us": {
            "title": "",
            "content": [[{"tag": "md", "text": text}]],
        },
    }
    return json.dumps(payload, ensure_ascii=False)


def build_markdown_card(text: str) -> str:
    payload = {
        "schema": "2.0",
        "config": {"wide_screen_mode": True},
        "body": {"elements": [{"tag": "markdown", "content": text}]},
    }
    return json.dumps(payload, ensure_ascii=False)


def build_text_payload(text: str) -> str:
    return json.dumps({"text": text}, ensure_ascii=False)


def build_payload_by_type(message_type: MessageType, text: str) -> str:
    if message_type == "interactive":
        return build_markdown_card(text)
    if message_type == "post":
        return build_post_payload(text)
    return build_text_payload(text)


def build_progress_card(
    status: str,
    elapsed_sec: int,
    recent_lines: list[str],
    history_lines: list[str] | None = None,
    recent_limit: int = 5,
) -> str:
    """Build a progress card with collapsible history panel.

    Args:
        status: Status text (e.g., "任务处理中", "任务已完成")
        elapsed_sec: Elapsed time in seconds
        recent_lines: List of recent output lines to always show
        history_lines: List of older lines to put in collapsible panel
        recent_limit: Number of recent lines to show (for display purposes)

    Returns:
        JSON string of the interactive card
    """
    elements = []

    # Status header
    status_emoji = {
        "running": "⏳",
        "completed": "✅",
        "failed": "❌",
    }.get(status, "⏳")
    status_text = {
        "running": "任务处理中",
        "completed": "任务已完成",
        "failed": "任务失败",
    }.get(status, status)

    elements.append({
        "tag": "markdown",
        "content": f"**{status_emoji} {status_text}**  \n耗时：`{elapsed_sec}s`",
    })

    # Collapsible history panel (if there's history beyond recent lines)
    if history_lines and len(history_lines) > 0:
        history_text = "\n".join(history_lines)
        # Escape code blocks in history
        history_text = history_text.replace("```", "'''")
        elements.append({
            "tag": "collapsible-panel",
            "header": {
                "template": "grey",
                "title": {
                    "tag": "plain_text",
                    "content": f"历史消息 ({len(history_lines)} 条)",
                },
                "collapsed": True,
            },
            "elements": [
                {
                    "tag": "markdown",
                    "content": f"```text\n{history_text}\n```",
                }
            ],
        })

    # Recent output section
    if recent_lines:
        recent_text = "\n".join(recent_lines)
        # Escape code blocks
        recent_text = recent_text.replace("```", "'''")
        elements.append({
            "tag": "markdown",
            "content": f"**最新输出**\n```text\n{recent_text}\n```",
        })
    else:
        elements.append({
            "tag": "markdown",
            "content": "**最新输出**\n(暂无)",
        })

    card = {
        "schema": "2.0",
        "config": {"wide_screen_mode": True},
        "body": {"elements": elements},
    }
    return json.dumps(card, ensure_ascii=False)

