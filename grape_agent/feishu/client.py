"""Thin Feishu API client wrapper based on lark-oapi SDK."""

from __future__ import annotations

import json
from typing import Any

from .types import FeishuSendResult


class FeishuClient:
    """Feishu API wrapper for message send/reply and bot info."""

    def __init__(self, app_id: str, app_secret: str, domain: str = "feishu"):
        self.app_id = app_id
        self.app_secret = app_secret
        self.domain = domain
        self._sdk = None
        self._client = None
        self.bot_open_id: str | None = None
        self.bot_name: str | None = None

    def _load_sdk(self):
        if self._sdk is not None:
            return self._sdk
        try:
            import lark_oapi as lark
        except ImportError as exc:
            raise ImportError("lark-oapi is required. Install with: pip install lark-oapi") from exc

        self._sdk = lark
        return lark

    def get_sdk(self):
        """Expose imported SDK module for WebSocket server initialization."""
        return self._load_sdk()

    def _get_client(self):
        if self._client is not None:
            return self._client

        lark = self._load_sdk()
        domain = lark.LARK_DOMAIN if self.domain == "lark" else lark.FEISHU_DOMAIN

        self._client = (
            lark.Client.builder().app_id(self.app_id).app_secret(self.app_secret).domain(domain).build()
        )
        return self._client

    @staticmethod
    def _extract_response(response: Any) -> tuple[bool, dict[str, Any], str]:
        """Normalize lark response into (ok, data, error)."""
        try:
            ok = bool(response.success())
        except Exception:
            ok = False

        code = getattr(response, "code", None)
        msg = getattr(response, "msg", None)
        raw_data = getattr(response, "data", None)
        data: dict[str, Any] = {}
        if isinstance(raw_data, dict):
            data = raw_data
        elif raw_data is not None:
            data = {
                key: value
                for key, value in vars(raw_data).items()
                if not key.startswith("_")
            }

        if ok:
            return True, data, ""

        return False, data, f"API error: code={code}, msg={msg}"

    def get_bot_info_sync(self) -> tuple[str | None, str | None]:
        """Fetch bot identity (open_id/name) synchronously."""
        if self.bot_open_id is not None:
            return self.bot_open_id, self.bot_name

        lark = self._load_sdk()
        client = self._get_client()
        from lark_oapi.core.model.base_request import BaseRequest

        request = (
            BaseRequest.builder()
            .http_method(lark.HttpMethod.GET)
            .uri("/open-apis/bot/v3/info")
            .token_types([lark.AccessTokenType.TENANT])
            .build()
        )

        response = client.request(request)
        ok, data, _ = self._extract_response(response)
        if not ok:
            return None, None

        # Both shapes appear in SDK wrappers; handle both.
        bot_data = data.get("bot") if isinstance(data.get("bot"), dict) else data.get("data", {}).get("bot", {})
        if isinstance(bot_data, dict):
            self.bot_open_id = bot_data.get("open_id")
            self.bot_name = bot_data.get("app_name") or bot_data.get("name")

        return self.bot_open_id, self.bot_name

    async def get_bot_info(self) -> tuple[str | None, str | None]:
        """Async wrapper for bot identity lookup."""
        return self.get_bot_info_sync()

    async def send_message(
        self,
        receive_id: str,
        text: str,
        receive_id_type: str = "chat_id",
    ) -> FeishuSendResult:
        """Send plain text message to chat or user."""
        content = json.dumps({"text": text}, ensure_ascii=False)
        return await self.send_message_content(
            receive_id=receive_id,
            msg_type="text",
            content=content,
            receive_id_type=receive_id_type,
        )

    async def send_message_content(
        self,
        receive_id: str,
        msg_type: str,
        content: str,
        receive_id_type: str = "chat_id",
    ) -> FeishuSendResult:
        """Send raw message content with explicit msg_type."""
        self._load_sdk()
        client = self._get_client()
        import lark_oapi.api.im.v1 as lark_im_v1

        request = (
            lark_im_v1.CreateMessageRequest.builder()
            .receive_id_type(receive_id_type)
            .request_body(
                lark_im_v1.CreateMessageRequestBody.builder()
                .receive_id(receive_id)
                .msg_type(msg_type)
                .content(content)
                .build()
            )
            .build()
        )

        response = client.im.v1.message.create(request)
        ok, data, err = self._extract_response(response)
        if not ok:
            return FeishuSendResult(success=False, error=err, raw=data)

        msg_id = None
        if hasattr(response, "data") and hasattr(response.data, "message_id"):
            msg_id = response.data.message_id

        return FeishuSendResult(success=True, message_id=msg_id, raw=data)

    async def reply_message(
        self,
        message_id: str,
        text: str,
        reply_in_thread: bool = False,
    ) -> FeishuSendResult:
        """Reply to existing message."""
        content = json.dumps({"text": text}, ensure_ascii=False)
        return await self.reply_message_content(
            message_id=message_id,
            msg_type="text",
            content=content,
            reply_in_thread=reply_in_thread,
        )

    async def reply_message_content(
        self,
        message_id: str,
        msg_type: str,
        content: str,
        reply_in_thread: bool = False,
    ) -> FeishuSendResult:
        """Reply to existing message with explicit msg_type/content."""
        self._load_sdk()
        client = self._get_client()
        import lark_oapi.api.im.v1 as lark_im_v1

        body_builder = (
            lark_im_v1.ReplyMessageRequestBody.builder()
            .msg_type(msg_type)
            .content(content)
        )
        if reply_in_thread:
            body_builder = body_builder.reply_in_thread(True)

        request = (
            lark_im_v1.ReplyMessageRequest.builder()
            .message_id(message_id)
            .request_body(body_builder.build())
            .build()
        )

        response = client.im.v1.message.reply(request)
        ok, data, err = self._extract_response(response)
        if not ok:
            return FeishuSendResult(success=False, error=err, raw=data)

        reply_id = None
        if hasattr(response, "data") and hasattr(response.data, "message_id"):
            reply_id = response.data.message_id

        return FeishuSendResult(success=True, message_id=reply_id, raw=data)

    async def update_message_content(
        self,
        message_id: str,
        content: str,
        msg_type: str = "interactive",
    ) -> FeishuSendResult:
        """Update an existing message content.

        Uses patch first for minimal payload updates; falls back to update with msg_type
        when patch fails.
        """
        self._load_sdk()
        client = self._get_client()
        import lark_oapi.api.im.v1 as lark_im_v1

        patch_request = (
            lark_im_v1.PatchMessageRequest.builder()
            .message_id(message_id)
            .request_body(
                lark_im_v1.PatchMessageRequestBody.builder()
                .content(content)
                .build()
            )
            .build()
        )
        patch_response = client.im.v1.message.patch(patch_request)
        ok, data, err = self._extract_response(patch_response)
        if ok:
            return FeishuSendResult(success=True, message_id=message_id, raw=data)

        update_request = (
            lark_im_v1.UpdateMessageRequest.builder()
            .message_id(message_id)
            .request_body(
                lark_im_v1.UpdateMessageRequestBody.builder()
                .msg_type(msg_type)
                .content(content)
                .build()
            )
            .build()
        )
        update_response = client.im.v1.message.update(update_request)
        ok2, data2, err2 = self._extract_response(update_response)
        if ok2:
            return FeishuSendResult(success=True, message_id=message_id, raw=data2)

        merged_error = f"patch failed ({err}); update failed ({err2})"
        return FeishuSendResult(success=False, error=merged_error, raw=data2 or data)
