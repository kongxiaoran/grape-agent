"""Anthropic LLM client implementation."""

import logging
from typing import Any

import anthropic

from ..retry import RetryConfig, async_retry
from ..schema import FunctionCall, LLMResponse, Message, ProviderEvent, TokenUsage, ToolCall
from .base import LLMClientBase

logger = logging.getLogger(__name__)


class AnthropicClient(LLMClientBase):
    """LLM client using Anthropic's protocol.

    This client uses the official Anthropic SDK and supports:
    - Extended thinking content
    - Tool calling
    - Retry logic
    """

    def __init__(
        self,
        api_key: str,
        api_base: str = "https://api.minimaxi.com/anthropic",
        model: str = "MiniMax-M2.5",
        native_web_search: dict[str, Any] | None = None,
        retry_config: RetryConfig | None = None,
    ):
        """Initialize Anthropic client.

        Args:
            api_key: API key for authentication
            api_base: Base URL for the API (default: MiniMax Anthropic endpoint)
            model: Model name to use (default: MiniMax-M2.5)
            native_web_search: Model-native web search configuration
            retry_config: Optional retry configuration
        """
        super().__init__(api_key, api_base, model, retry_config)
        self.native_web_search = native_web_search or {}

        # Initialize Anthropic async client
        self.client = anthropic.AsyncAnthropic(
            base_url=api_base,
            api_key=api_key,
            default_headers={"Authorization": f"Bearer {api_key}"},
        )

    def _native_web_search_enabled_for_model(self) -> bool:
        """Whether native web search should be injected for current model."""
        if not self.native_web_search.get("enabled", False):
            return False
        patterns = self.native_web_search.get("model_patterns", [])
        if not patterns:
            return True
        model_lower = self.model.lower()
        return any(str(pattern).lower() in model_lower for pattern in patterns)

    def _build_native_web_search_tool(self) -> dict[str, Any]:
        """Build provider-specific native web search tool payload."""
        configured_type = str(self.native_web_search.get("tool_type", "web_search")).strip() or "web_search"
        # Anthropic-compatible endpoints require server tool type/version, not OpenAI-style {"type":"web_search","web_search":...}
        tool_type = "web_search_20250305" if configured_type == "web_search" else configured_type
        tool = {
            "type": tool_type,
            "name": str(self.native_web_search.get("tool_name", "web_search")).strip() or "web_search",
        }

        # Map optional settings to Anthropic web search schema
        web_search_payload = self.native_web_search.get("web_search", {})
        if isinstance(web_search_payload, dict):
            if "max_uses" in web_search_payload:
                tool["max_uses"] = web_search_payload["max_uses"]
            if "allowed_domains" in web_search_payload:
                tool["allowed_domains"] = web_search_payload["allowed_domains"]
            if "blocked_domains" in web_search_payload:
                tool["blocked_domains"] = web_search_payload["blocked_domains"]
            if "user_location" in web_search_payload:
                tool["user_location"] = web_search_payload["user_location"]
        return tool

    async def _make_api_request(
        self,
        system_message: str | None,
        api_messages: list[dict[str, Any]],
        tools: list[Any] | None = None,
    ) -> anthropic.types.Message:
        """Execute API request (core method that can be retried).

        Args:
            system_message: Optional system message
            api_messages: List of messages in Anthropic format
            tools: Optional list of tools

        Returns:
            Anthropic Message response

        Raises:
            Exception: API call failed
        """
        params = {
            "model": self.model,
            "max_tokens": 16384,
            "messages": api_messages,
        }

        if system_message:
            params["system"] = system_message

        request_tools = self._convert_tools(tools) if tools else []
        native_tool_added = False
        if self._native_web_search_enabled_for_model():
            native_tool = self._build_native_web_search_tool()
            existing_types = {
                tool.get("type")
                for tool in request_tools
                if isinstance(tool, dict) and tool.get("type")
            }
            if native_tool.get("type") not in existing_types:
                request_tools.append(native_tool)
                native_tool_added = True

        if request_tools:
            params["tools"] = request_tools

        # Use Anthropic SDK's async messages.create
        try:
            response = await self.client.messages.create(**params)
        except Exception as exc:
            if not native_tool_added:
                raise
            logger.warning("Native web_search tool failed, retrying without it: %s", exc)
            fallback_tools = self._convert_tools(tools) if tools else []
            if fallback_tools:
                params["tools"] = fallback_tools
            else:
                params.pop("tools", None)
            response = await self.client.messages.create(**params)
        return response

    def _convert_tools(self, tools: list[Any]) -> list[dict[str, Any]]:
        """Convert tools to Anthropic format.

        Anthropic tool format:
        {
            "name": "tool_name",
            "description": "Tool description",
            "input_schema": {
                "type": "object",
                "properties": {...},
                "required": [...]
            }
        }

        Args:
            tools: List of Tool objects or dicts

        Returns:
            List of tools in Anthropic dict format
        """
        result = []
        for tool in tools:
            if isinstance(tool, dict):
                result.append(tool)
            elif hasattr(tool, "to_schema"):
                # Tool object with to_schema method
                result.append(tool.to_schema())
            else:
                raise TypeError(f"Unsupported tool type: {type(tool)}")
        return result

    def _convert_messages(self, messages: list[Message]) -> tuple[str | None, list[dict[str, Any]]]:
        """Convert internal messages to Anthropic format.

        Args:
            messages: List of internal Message objects

        Returns:
            Tuple of (system_message, api_messages)
        """
        system_message = None
        api_messages = []

        for msg in messages:
            if msg.role == "system":
                system_message = msg.content
                continue

            # For user and assistant messages
            if msg.role in ["user", "assistant"]:
                # Handle assistant messages with thinking or tool calls
                if msg.role == "assistant" and (msg.thinking or msg.tool_calls):
                    # Build content blocks for assistant with thinking and/or tool calls
                    content_blocks = []

                    # Add thinking block if present
                    if msg.thinking:
                        content_blocks.append({"type": "thinking", "thinking": msg.thinking})

                    # Add text content if present
                    if msg.content:
                        content_blocks.append({"type": "text", "text": msg.content})

                    # Add tool use blocks
                    if msg.tool_calls:
                        for tool_call in msg.tool_calls:
                            content_blocks.append(
                                {
                                    "type": "tool_use",
                                    "id": tool_call.id,
                                    "name": tool_call.function.name,
                                    "input": tool_call.function.arguments,
                                }
                            )

                    api_messages.append({"role": "assistant", "content": content_blocks})
                else:
                    api_messages.append({"role": msg.role, "content": msg.content})

            # For tool result messages
            elif msg.role == "tool":
                # Anthropic uses user role with tool_result content blocks
                api_messages.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": msg.tool_call_id,
                                "content": msg.content,
                            }
                        ],
                    }
                )

        return system_message, api_messages

    def _prepare_request(
        self,
        messages: list[Message],
        tools: list[Any] | None = None,
    ) -> dict[str, Any]:
        """Prepare the request for Anthropic API.

        Args:
            messages: List of conversation messages
            tools: Optional list of available tools

        Returns:
            Dictionary containing request parameters
        """
        system_message, api_messages = self._convert_messages(messages)

        return {
            "system_message": system_message,
            "api_messages": api_messages,
            "tools": tools,
        }

    def _parse_response(self, response: anthropic.types.Message) -> LLMResponse:
        """Parse Anthropic response into LLMResponse.

        Args:
            response: Anthropic Message response

        Returns:
            LLMResponse object
        """
        # Extract text content, thinking, and tool calls
        text_content = ""
        thinking_content = ""
        tool_calls = []
        provider_events: list[ProviderEvent] = []

        for block in response.content:
            if block.type == "text":
                text_content += block.text
            elif block.type == "thinking":
                thinking_content += block.thinking
            elif block.type == "tool_use":
                # Parse Anthropic tool_use block
                tool_calls.append(
                    ToolCall(
                        id=block.id,
                        type="function",
                        function=FunctionCall(
                            name=block.name,
                            arguments=block.input,
                        ),
                    )
                )
            elif block.type == "server_tool_use":
                provider_events.append(
                    ProviderEvent(
                        source="anthropic",
                        event_type="server_tool_use",
                        name=getattr(block, "name", None),
                        payload={
                            "id": getattr(block, "id", None),
                            "input": getattr(block, "input", None),
                        },
                    )
                )
            elif block.type == "tool_result":
                provider_events.append(
                    ProviderEvent(
                        source="anthropic",
                        event_type="tool_result",
                        payload={
                            "tool_use_id": getattr(block, "tool_use_id", None),
                            "content": getattr(block, "content", None),
                        },
                    )
                )

        # Extract token usage from response.
        # Keep total as actual prompt+completion tokens and expose cache stats separately.
        usage = None
        if hasattr(response, "usage") and response.usage:
            input_tokens = response.usage.input_tokens or 0
            output_tokens = response.usage.output_tokens or 0
            cache_read_tokens = getattr(response.usage, "cache_read_input_tokens", 0) or 0
            cache_creation_tokens = getattr(response.usage, "cache_creation_input_tokens", 0) or 0
            usage = TokenUsage(
                prompt_tokens=input_tokens,
                completion_tokens=output_tokens,
                total_tokens=input_tokens + output_tokens,
                cache_read_tokens=cache_read_tokens,
                cache_creation_tokens=cache_creation_tokens,
            )

        return LLMResponse(
            content=text_content,
            thinking=thinking_content if thinking_content else None,
            tool_calls=tool_calls if tool_calls else None,
            provider_events=provider_events if provider_events else None,
            finish_reason=response.stop_reason or "stop",
            usage=usage,
        )

    async def generate(
        self,
        messages: list[Message],
        tools: list[Any] | None = None,
    ) -> LLMResponse:
        """Generate response from Anthropic LLM.

        Args:
            messages: List of conversation messages
            tools: Optional list of available tools

        Returns:
            LLMResponse containing the generated content
        """
        # Prepare request
        request_params = self._prepare_request(messages, tools)

        # Make API request with retry logic
        if self.retry_config.enabled:
            # Apply retry logic
            retry_decorator = async_retry(config=self.retry_config, on_retry=self.retry_callback)
            api_call = retry_decorator(self._make_api_request)
            response = await api_call(
                request_params["system_message"],
                request_params["api_messages"],
                request_params["tools"],
            )
        else:
            # Don't use retry
            response = await self._make_api_request(
                request_params["system_message"],
                request_params["api_messages"],
                request_params["tools"],
            )

        # Parse and return response
        return self._parse_response(response)
