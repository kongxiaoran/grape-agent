"""Feishu channel plugin package."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .plugin import FeishuChannelPlugin

__all__ = ["FeishuChannelPlugin"]
