"""Feishu card rendering helpers with fallback."""

from __future__ import annotations

from mini_agent.feishu.rendering import build_markdown_card, build_text_payload


def build_card_with_fallback(text: str) -> tuple[str, str]:
    """Build interactive card payload; fallback to text payload on error."""
    try:
        return "interactive", build_markdown_card(text)
    except Exception:
        return "text", build_text_payload(text)
