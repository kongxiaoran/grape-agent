"""Configuration management module

Provides unified configuration loading and management functionality
"""

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field


class RetryConfig(BaseModel):
    """Retry configuration"""

    enabled: bool = True
    max_retries: int = 3
    initial_delay: float = 1.0
    max_delay: float = 60.0
    exponential_base: float = 2.0


class NativeWebSearchConfig(BaseModel):
    """Model-native web search configuration (OpenAI protocol)."""

    enabled: bool = True
    model_patterns: list[str] = Field(default_factory=lambda: ["glm-5"])
    tool_type: str = "web_search"
    web_search: dict[str, Any] = Field(default_factory=lambda: {"enable": "True"})


class LLMConfig(BaseModel):
    """LLM configuration"""

    api_key: str
    api_base: str = "https://api.minimax.io"
    model: str = "MiniMax-M2.5"
    provider: str = "anthropic"  # "anthropic" or "openai"
    retry: RetryConfig = Field(default_factory=RetryConfig)
    native_web_search: NativeWebSearchConfig = Field(default_factory=NativeWebSearchConfig)


class AgentConfig(BaseModel):
    """Agent configuration"""

    max_steps: int = 50
    workspace_dir: str = "./workspace"
    system_prompt_path: str = "system_prompt.md"


class AgentProfileConfig(BaseModel):
    """Per-agent override configuration."""

    workspace: str | None = None
    model: str | None = None
    system_prompt_path: str | None = None


class AgentsConfig(BaseModel):
    """Agent profile registry configuration."""

    default_agent_id: str = "main"
    profiles: dict[str, AgentProfileConfig] = Field(default_factory=dict)


class RoutingRuleConfig(BaseModel):
    """One routing rule entry."""

    agent_id: str
    channel: str | None = None
    account_id: str | None = None
    chat_type: Literal["direct", "group"] | None = None
    chat_id: str | None = None


class RoutingConfig(BaseModel):
    """Routing configuration."""

    default_agent_id: str = "main"
    rules: list[RoutingRuleConfig] = Field(default_factory=list)


class SubagentPolicyConfig(BaseModel):
    """Subagent orchestration policy."""

    enabled: bool = True
    max_depth: int = Field(default=2, ge=0, le=8)
    deny_tools_leaf: list[str] = Field(
        default_factory=lambda: [
            "sessions_spawn",
            "sessions_list",
            "sessions_history",
            "sessions_send",
        ]
    )


class MCPConfig(BaseModel):
    """MCP (Model Context Protocol) timeout configuration"""

    connect_timeout: float = 10.0  # Connection timeout (seconds)
    execute_timeout: float = 60.0  # Tool execution timeout (seconds)
    sse_read_timeout: float = 120.0  # SSE read timeout (seconds)


class ToolsConfig(BaseModel):
    """Tools configuration"""

    # Basic tools (file operations, bash)
    enable_file_tools: bool = True
    enable_bash: bool = True
    enable_note: bool = True

    # Skills
    enable_skills: bool = True
    skills_dir: str = "./skills"

    # MCP tools
    enable_mcp: bool = True
    mcp_config_path: str = "mcp.json"
    mcp: MCPConfig = Field(default_factory=MCPConfig)


class UIConfig(BaseModel):
    """CLI rendering configuration."""

    style: Literal["legacy", "compact", "claude"] = "claude"
    show_thinking: bool = True
    show_tool_args: bool = False
    show_timing: bool = False
    show_steps: bool = False
    render_markdown: bool = True


class FeishuStreamingConfig(BaseModel):
    """Feishu progressive streaming config.

    Note: this is chunk-based progressive delivery, not model token streaming.
    """

    enabled: bool = False
    chunk_size: int = Field(default=600, ge=100, le=3000)
    interval_ms: int = Field(default=120, ge=0, le=5000)
    reply_all_chunks: bool = False
    progress_ping_sec: int = Field(default=0, ge=0, le=300)
    progress_card_enabled: bool = True
    progress_card_start_sec: int = Field(default=5, ge=1, le=300)
    progress_card_update_sec: int = Field(default=3, ge=1, le=60)
    progress_card_tail_lines: int = Field(default=5, ge=1, le=20)


class FeishuPolicyConfig(BaseModel):
    """Feishu chat policy controls."""

    require_mention: bool = True
    reply_in_thread: bool = True
    group_session_scope: Literal["group", "group_sender", "topic"] = "group"


class FeishuAccountConfig(BaseModel):
    """Feishu account credentials."""

    app_id: str
    app_secret: str
    domain: str = "feishu"  # "feishu" or "lark"


class FeishuConfig(BaseModel):
    """Embedded Feishu bot configuration."""

    enabled: bool = False
    default_account: str = "main"
    accounts: dict[str, FeishuAccountConfig] = Field(default_factory=dict)
    render_mode: Literal["auto", "raw", "card"] = "auto"
    workspace_base: str | None = None
    streaming: FeishuStreamingConfig = Field(default_factory=FeishuStreamingConfig)
    policy: FeishuPolicyConfig = Field(default_factory=FeishuPolicyConfig)


class ChannelsConfig(BaseModel):
    """Channel plugins configuration."""

    feishu: FeishuConfig = Field(default_factory=FeishuConfig)


class GatewayAuthConfig(BaseModel):
    """Gateway authentication configuration."""

    enabled: bool = True
    token: str = ""


class GatewayConfig(BaseModel):
    """Gateway control-plane server configuration."""

    enabled: bool = False
    host: str = "127.0.0.1"
    port: int = 8765
    auth: GatewayAuthConfig = Field(default_factory=GatewayAuthConfig)


class CronConfig(BaseModel):
    """Cron scheduler configuration."""

    enabled: bool = False
    store_path: str = "~/.grape-agent/cron/jobs.json"
    poll_interval_sec: float = Field(default=5.0, ge=0.5, le=300.0)
    max_concurrency: int = Field(default=2, ge=1, le=32)
    default_timeout_sec: int = Field(default=300, ge=5, le=7200)


class WebtermBridgeConfig(BaseModel):
    """Local bridge service config for browser web terminal integration."""

    enabled: bool = False
    host: str = "127.0.0.1"
    port: int = 8766
    token: str = "change-me-webterm-bridge-token"
    gateway_host: str | None = None
    gateway_port: int | None = None
    gateway_token: str | None = None
    gateway_client_id: str = "webterm-bridge"
    parent_session_key: str = "agent:main:terminal:main"
    default_agent_id: str = "main"
    max_buffer_lines: int = Field(default=400, ge=50, le=5000)
    max_context_chars: int = Field(default=12000, ge=1000, le=200000)
    command_wrap_markers: bool = True
    command_require_confirm: bool = True
    auto_execute_low_risk: bool = False
    profile_path: str = "~/.grape-agent/webterm_profiles.yaml"
    command_allowlist: list[str] = Field(
        default_factory=lambda: [
            "grep",
            "tail",
            "cat",
            "less",
            "awk",
            "sed",
            "journalctl",
            "kubectl",
            "ps",
            "top",
            "netstat",
            "ss",
            "curl",
            "ls",
            "find",
        ]
    )
    command_denylist: list[str] = Field(
        default_factory=lambda: [
            "rm",
            "reboot",
            "shutdown",
            "mkfs",
            "userdel",
            "iptables",
            "poweroff",
            "init",
        ]
    )


class MemOSConfig(BaseModel):
    """MemOS cloud memory configuration."""

    enabled: bool = False
    api_key: str = ""
    conversation_id: str = ""
    query_prefix: str = ""

    # Automatic memory lifecycle (OpenClaw-style): recall before turn, add after turn.
    auto_recall_enabled: bool = True
    auto_add_enabled: bool = True
    add_include_assistant: bool = True
    add_async_mode: bool = True
    add_throttle_sec: float = 0.0

    # Recall controls.
    recall_memory_limit_number: int = 6
    recall_preference_limit_number: int = 4
    recall_include_preference: bool = True
    recall_include_tool_memory: bool = False
    recall_tool_memory_limit_number: int = 4
    recall_max_items: int = 8
    recall_max_item_chars: int = 220
    recall_min_relativity: float = 0.0

    # Add metadata.
    source: str = "grape-agent"
    tags: list[str] = Field(default_factory=list)


class Config(BaseModel):
    """Main configuration class"""

    llm: LLMConfig
    agent: AgentConfig
    agents: AgentsConfig = Field(default_factory=AgentsConfig)
    routing: RoutingConfig = Field(default_factory=RoutingConfig)
    subagents: SubagentPolicyConfig = Field(default_factory=SubagentPolicyConfig)
    ui: UIConfig = Field(default_factory=UIConfig)
    tools: ToolsConfig
    channels: ChannelsConfig = Field(default_factory=ChannelsConfig)
    gateway: GatewayConfig = Field(default_factory=GatewayConfig)
    cron: CronConfig = Field(default_factory=CronConfig)
    webterm_bridge: WebtermBridgeConfig = Field(default_factory=WebtermBridgeConfig)
    memos: MemOSConfig = Field(default_factory=MemOSConfig)

    @classmethod
    def load(cls) -> "Config":
        """Load configuration from the default search path."""
        config_path = cls.get_default_config_path()
        if not config_path.exists():
            raise FileNotFoundError(
                "Configuration file not found. Place settings.json at ~/.grape/settings.json "
                "or use mini_agent/config/settings.json in development mode."
            )
        return cls.from_yaml(config_path)

    @classmethod
    def from_yaml(cls, config_path: str | Path) -> "Config":
        """Load configuration from YAML file

        Args:
            config_path: Configuration file path

        Returns:
            Config instance

        Raises:
            FileNotFoundError: Configuration file does not exist
            ValueError: Invalid configuration format or missing required fields
        """
        config_path = Path(config_path)

        if not config_path.exists():
            raise FileNotFoundError(f"Configuration file does not exist: {config_path}")

        with open(config_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if not data:
            raise ValueError("Configuration file is empty")

        # Parse LLM configuration
        if "api_key" not in data:
            raise ValueError("Configuration file missing required field: api_key")

        if not data["api_key"] or data["api_key"] == "YOUR_API_KEY_HERE":
            raise ValueError("Please configure a valid API Key")

        # Parse retry configuration
        retry_data = data.get("retry", {})
        retry_config = RetryConfig(
            enabled=retry_data.get("enabled", True),
            max_retries=retry_data.get("max_retries", 3),
            initial_delay=retry_data.get("initial_delay", 1.0),
            max_delay=retry_data.get("max_delay", 60.0),
            exponential_base=retry_data.get("exponential_base", 2.0),
        )

        native_web_search_data = data.get("native_web_search", {})
        if not isinstance(native_web_search_data, dict):
            native_web_search_data = {}
        native_web_search_config = NativeWebSearchConfig(
            enabled=native_web_search_data.get("enabled", True),
            model_patterns=native_web_search_data.get("model_patterns", ["glm-5"]),
            tool_type=native_web_search_data.get("tool_type", "web_search"),
            web_search=native_web_search_data.get("web_search", {"enable": "True"}),
        )

        llm_config = LLMConfig(
            api_key=data["api_key"],
            api_base=data.get("api_base", "https://api.minimax.io"),
            model=data.get("model", "MiniMax-M2.5"),
            provider=data.get("provider", "anthropic"),
            retry=retry_config,
            native_web_search=native_web_search_config,
        )

        # Parse Agent configuration
        agent_config = AgentConfig(
            max_steps=data.get("max_steps", 50),
            workspace_dir=data.get("workspace_dir", "./workspace"),
            system_prompt_path=data.get("system_prompt_path", "system_prompt.md"),
        )

        # Parse agent profile configuration (M3)
        agents_data = data.get("agents", {})
        profiles_raw = agents_data.get("profiles", {}) if isinstance(agents_data, dict) else {}
        profiles: dict[str, AgentProfileConfig] = {}
        if isinstance(profiles_raw, dict):
            for profile_id, raw in profiles_raw.items():
                if not isinstance(raw, dict):
                    raw = {}
                key = str(profile_id).strip()
                if not key:
                    continue
                profiles[key] = AgentProfileConfig(
                    workspace=raw.get("workspace"),
                    model=raw.get("model"),
                    system_prompt_path=raw.get("system_prompt_path"),
                )
        agents_config = AgentsConfig(
            default_agent_id=(agents_data.get("default_agent_id", "main") if isinstance(agents_data, dict) else "main"),
            profiles=profiles,
        )

        # Parse routing configuration (M3)
        routing_data = data.get("routing", {})
        rules_raw = routing_data.get("rules", []) if isinstance(routing_data, dict) else []
        rules: list[RoutingRuleConfig] = []
        if isinstance(rules_raw, list):
            for raw in rules_raw:
                if not isinstance(raw, dict):
                    continue
                agent_id = str(raw.get("agent_id", "")).strip()
                if not agent_id:
                    continue
                rules.append(
                    RoutingRuleConfig(
                        agent_id=agent_id,
                        channel=raw.get("channel"),
                        account_id=raw.get("account_id"),
                        chat_type=raw.get("chat_type"),
                        chat_id=raw.get("chat_id"),
                    )
                )
        routing_config = RoutingConfig(
            default_agent_id=(
                routing_data.get("default_agent_id", agents_config.default_agent_id)
                if isinstance(routing_data, dict)
                else agents_config.default_agent_id
            ),
            rules=rules,
        )

        # Parse subagent policy (M4)
        subagents_data = data.get("subagents", {})
        subagents_config = SubagentPolicyConfig(
            enabled=(subagents_data.get("enabled", True) if isinstance(subagents_data, dict) else True),
            max_depth=(subagents_data.get("max_depth", 2) if isinstance(subagents_data, dict) else 2),
            deny_tools_leaf=(
                subagents_data.get("deny_tools_leaf", ["sessions_spawn", "sessions_list", "sessions_history", "sessions_send"])
                if isinstance(subagents_data, dict)
                else ["sessions_spawn", "sessions_list", "sessions_history", "sessions_send"]
            ),
        )

        # Parse UI configuration
        ui_data = data.get("ui", {})
        ui_config = UIConfig(
            style=(ui_data.get("style", "claude") if isinstance(ui_data, dict) else "claude"),
            show_thinking=(ui_data.get("show_thinking", True) if isinstance(ui_data, dict) else True),
            show_tool_args=(ui_data.get("show_tool_args", False) if isinstance(ui_data, dict) else False),
            show_timing=(ui_data.get("show_timing", False) if isinstance(ui_data, dict) else False),
            show_steps=(ui_data.get("show_steps", False) if isinstance(ui_data, dict) else False),
            render_markdown=(ui_data.get("render_markdown", True) if isinstance(ui_data, dict) else True),
        )

        # Parse tools configuration
        tools_data = data.get("tools", {})

        # Parse MCP configuration
        mcp_data = tools_data.get("mcp", {})
        mcp_config = MCPConfig(
            connect_timeout=mcp_data.get("connect_timeout", 10.0),
            execute_timeout=mcp_data.get("execute_timeout", 60.0),
            sse_read_timeout=mcp_data.get("sse_read_timeout", 120.0),
        )

        tools_config = ToolsConfig(
            enable_file_tools=tools_data.get("enable_file_tools", True),
            enable_bash=tools_data.get("enable_bash", True),
            enable_note=tools_data.get("enable_note", True),
            enable_skills=tools_data.get("enable_skills", True),
            skills_dir=tools_data.get("skills_dir", "./skills"),
            enable_mcp=tools_data.get("enable_mcp", True),
            mcp_config_path=tools_data.get("mcp_config_path", "mcp.json"),
            mcp=mcp_config,
        )

        # Parse channel plugins configuration (M2)
        if "feishu" in data:
            raise ValueError("top-level 'feishu' config is not supported; use 'channels.feishu'")

        channels_data = data.get("channels", {})
        feishu_data = channels_data.get("feishu", {}) if isinstance(channels_data, dict) else {}
        streaming_data = feishu_data.get("streaming", {}) if isinstance(feishu_data, dict) else {}
        policy_data = feishu_data.get("policy", {}) if isinstance(feishu_data, dict) else {}
        accounts_raw = feishu_data.get("accounts", {}) if isinstance(feishu_data, dict) else {}
        accounts: dict[str, FeishuAccountConfig] = {}
        if isinstance(accounts_raw, dict):
            for account_id, raw in accounts_raw.items():
                key = str(account_id).strip()
                if not key or not isinstance(raw, dict):
                    continue
                app_id = str(raw.get("app_id", "")).strip()
                app_secret = str(raw.get("app_secret", "")).strip()
                if not app_id or not app_secret:
                    raise ValueError(f"channels.feishu.accounts.{key} requires app_id and app_secret")
                accounts[key] = FeishuAccountConfig(
                    app_id=app_id,
                    app_secret=app_secret,
                    domain=raw.get("domain", "feishu"),
                )

        default_account = str(feishu_data.get("default_account", "main")).strip() if isinstance(feishu_data, dict) else "main"
        feishu_config = FeishuConfig(
            enabled=feishu_data.get("enabled", False),
            default_account=default_account or "main",
            accounts=accounts,
            render_mode=feishu_data.get("render_mode", "auto"),
            workspace_base=feishu_data.get("workspace_base"),
            streaming=FeishuStreamingConfig(
                enabled=streaming_data.get("enabled", False),
                chunk_size=streaming_data.get("chunk_size", 600),
                interval_ms=streaming_data.get("interval_ms", 120),
                reply_all_chunks=streaming_data.get("reply_all_chunks", False),
                progress_ping_sec=streaming_data.get("progress_ping_sec", 0),
                progress_card_enabled=streaming_data.get("progress_card_enabled", True),
                progress_card_start_sec=streaming_data.get("progress_card_start_sec", 5),
                progress_card_update_sec=streaming_data.get("progress_card_update_sec", 3),
                progress_card_tail_lines=streaming_data.get("progress_card_tail_lines", 5),
            ),
            policy=FeishuPolicyConfig(
                require_mention=policy_data.get("require_mention", True),
                reply_in_thread=policy_data.get("reply_in_thread", True),
                group_session_scope=policy_data.get("group_session_scope", "group"),
            ),
        )
        if feishu_config.enabled and not feishu_config.accounts:
            raise ValueError("channels.feishu.accounts is required when channels.feishu.enabled=true")
        if feishu_config.enabled and feishu_config.default_account not in feishu_config.accounts:
            raise ValueError("channels.feishu.default_account must exist in channels.feishu.accounts")
        channels_config = ChannelsConfig(feishu=feishu_config)

        # Parse gateway control-plane configuration
        gateway_data = data.get("gateway", {})
        gateway_auth_data = gateway_data.get("auth", {})
        gateway_config = GatewayConfig(
            enabled=gateway_data.get("enabled", False),
            host=gateway_data.get("host", "127.0.0.1"),
            port=gateway_data.get("port", 8765),
            auth=GatewayAuthConfig(
                enabled=gateway_auth_data.get("enabled", True),
                token=gateway_auth_data.get("token", ""),
            ),
        )

        cron_data = data.get("cron", {})
        cron_config = CronConfig(
            enabled=(cron_data.get("enabled", False) if isinstance(cron_data, dict) else False),
            store_path=(cron_data.get("store_path", "~/.grape-agent/cron/jobs.json") if isinstance(cron_data, dict) else "~/.grape-agent/cron/jobs.json"),
            poll_interval_sec=(cron_data.get("poll_interval_sec", 5.0) if isinstance(cron_data, dict) else 5.0),
            max_concurrency=(cron_data.get("max_concurrency", 2) if isinstance(cron_data, dict) else 2),
            default_timeout_sec=(cron_data.get("default_timeout_sec", 300) if isinstance(cron_data, dict) else 300),
        )

        webterm_data = data.get("webterm_bridge", {})
        webterm_config = WebtermBridgeConfig(
            enabled=(webterm_data.get("enabled", False) if isinstance(webterm_data, dict) else False),
            host=(webterm_data.get("host", "127.0.0.1") if isinstance(webterm_data, dict) else "127.0.0.1"),
            port=(webterm_data.get("port", 8766) if isinstance(webterm_data, dict) else 8766),
            token=(
                webterm_data.get("token", "change-me-webterm-bridge-token")
                if isinstance(webterm_data, dict)
                else "change-me-webterm-bridge-token"
            ),
            gateway_host=(webterm_data.get("gateway_host") if isinstance(webterm_data, dict) else None),
            gateway_port=(webterm_data.get("gateway_port") if isinstance(webterm_data, dict) else None),
            gateway_token=(webterm_data.get("gateway_token") if isinstance(webterm_data, dict) else None),
            gateway_client_id=(
                webterm_data.get("gateway_client_id", "webterm-bridge")
                if isinstance(webterm_data, dict)
                else "webterm-bridge"
            ),
            parent_session_key=(
                webterm_data.get("parent_session_key", "agent:main:terminal:main")
                if isinstance(webterm_data, dict)
                else "agent:main:terminal:main"
            ),
            default_agent_id=(
                webterm_data.get("default_agent_id", "main") if isinstance(webterm_data, dict) else "main"
            ),
            max_buffer_lines=(
                webterm_data.get("max_buffer_lines", 400) if isinstance(webterm_data, dict) else 400
            ),
            max_context_chars=(
                webterm_data.get("max_context_chars", 12000) if isinstance(webterm_data, dict) else 12000
            ),
            command_wrap_markers=(
                webterm_data.get("command_wrap_markers", True) if isinstance(webterm_data, dict) else True
            ),
            command_require_confirm=(
                webterm_data.get("command_require_confirm", True) if isinstance(webterm_data, dict) else True
            ),
            auto_execute_low_risk=(
                webterm_data.get("auto_execute_low_risk", False) if isinstance(webterm_data, dict) else False
            ),
            profile_path=(
                webterm_data.get("profile_path", "~/.grape-agent/webterm_profiles.yaml")
                if isinstance(webterm_data, dict)
                else "~/.grape-agent/webterm_profiles.yaml"
            ),
            command_allowlist=(
                webterm_data.get(
                    "command_allowlist",
                    [
                        "grep",
                        "tail",
                        "cat",
                        "less",
                        "awk",
                        "sed",
                        "journalctl",
                        "kubectl",
                        "ps",
                        "top",
                        "netstat",
                        "ss",
                        "curl",
                        "ls",
                        "find",
                    ],
                )
                if isinstance(webterm_data, dict)
                else [
                    "grep",
                    "tail",
                    "cat",
                    "less",
                    "awk",
                    "sed",
                    "journalctl",
                    "kubectl",
                    "ps",
                    "top",
                    "netstat",
                    "ss",
                    "curl",
                    "ls",
                    "find",
                ]
            ),
            command_denylist=(
                webterm_data.get(
                    "command_denylist",
                    [
                        "rm",
                        "reboot",
                        "shutdown",
                        "mkfs",
                        "userdel",
                        "iptables",
                        "poweroff",
                        "init",
                    ],
                )
                if isinstance(webterm_data, dict)
                else [
                    "rm",
                    "reboot",
                    "shutdown",
                    "mkfs",
                    "userdel",
                    "iptables",
                    "poweroff",
                    "init",
                ]
            ),
        )

        if gateway_config.enabled and gateway_config.auth.enabled and not gateway_config.auth.token:
            raise ValueError("gateway.auth.token is required when gateway and auth are enabled")
        if webterm_config.enabled and not webterm_config.token:
            raise ValueError("webterm_bridge.token is required when webterm_bridge.enabled=true")

        # Parse MemOS configuration
        memos_data = data.get("memos", {})
        memos_dict = memos_data if isinstance(memos_data, dict) else {}
        memos_config = MemOSConfig(
            enabled=bool(memos_dict.get("enabled", False)),
            api_key=str(memos_dict.get("api_key", "") or ""),
            conversation_id=str(memos_dict.get("conversation_id", "") or ""),
            query_prefix=str(memos_dict.get("query_prefix", "") or ""),
            auto_recall_enabled=bool(memos_dict.get("auto_recall_enabled", True)),
            auto_add_enabled=bool(memos_dict.get("auto_add_enabled", True)),
            add_include_assistant=bool(memos_dict.get("add_include_assistant", True)),
            add_async_mode=bool(memos_dict.get("add_async_mode", True)),
            add_throttle_sec=float(memos_dict.get("add_throttle_sec", 0.0) or 0.0),
            recall_memory_limit_number=int(memos_dict.get("recall_memory_limit_number", 6) or 6),
            recall_preference_limit_number=int(memos_dict.get("recall_preference_limit_number", 4) or 4),
            recall_include_preference=bool(memos_dict.get("recall_include_preference", True)),
            recall_include_tool_memory=bool(memos_dict.get("recall_include_tool_memory", False)),
            recall_tool_memory_limit_number=int(memos_dict.get("recall_tool_memory_limit_number", 4) or 4),
            recall_max_items=int(memos_dict.get("recall_max_items", 8) or 8),
            recall_max_item_chars=int(memos_dict.get("recall_max_item_chars", 220) or 220),
            recall_min_relativity=float(memos_dict.get("recall_min_relativity", 0.0) or 0.0),
            source=str(memos_dict.get("source", "grape-agent") or "grape-agent"),
            tags=[str(tag) for tag in (memos_dict.get("tags", []) or []) if str(tag).strip()],
        )

        return cls(
            llm=llm_config,
            agent=agent_config,
            agents=agents_config,
            routing=routing_config,
            subagents=subagents_config,
            ui=ui_config,
            tools=tools_config,
            channels=channels_config,
            gateway=gateway_config,
            cron=cron_config,
            webterm_bridge=webterm_config,
            memos=memos_config,
        )

    @staticmethod
    def get_package_dir() -> Path:
        """Get the package installation directory

        Returns:
            Path to the mini_agent package directory
        """
        # Get the directory where this config.py file is located
        return Path(__file__).parent

    @classmethod
    def find_config_file(cls, filename: str) -> Path | None:
        """Find configuration file with priority order

        Search for config file in the following order of priority:
        1) mini_agent/config/{filename} in current directory (development mode)
        2) ~/.grape/{filename} in user home directory (Grape default)
        3) ~/.grape-agent/config/{filename} in user home directory (legacy fallback)
        4) {package}/mini_agent/config/{filename} in package installation directory

        Args:
            filename: Configuration file name (e.g., "settings.json", "mcp.json", "system_prompt.md")

        Returns:
            Path to found config file, or None if not found
        """
        # Priority 1: Development mode - current directory's config/ subdirectory
        dev_config = Path.cwd() / "mini_agent" / "config" / filename
        if dev_config.exists():
            return dev_config

        # Priority 2: User config directory
        grape_user_config = Path.home() / ".grape" / filename
        if grape_user_config.exists():
            return grape_user_config

        # Priority 3: Legacy user config directory
        legacy_user_config = Path.home() / ".grape-agent" / "config" / filename
        if legacy_user_config.exists():
            return legacy_user_config

        # Priority 4: Package installation directory's config/ subdirectory
        package_config = cls.get_package_dir() / "config" / filename
        if package_config.exists():
            return package_config

        return None

    @classmethod
    def get_default_config_path(cls) -> Path:
        """Get the default config file path with priority search

        Returns:
            Path to settings.json (prioritizes:
            ~/.grape/settings.json > legacy config.yaml > dev/package settings.json)
        """
        # Priority 1: Grape user config (new default)
        user_settings = Path.home() / ".grape" / "settings.json"
        if user_settings.exists():
            return user_settings

        # Legacy fallback for backward compatibility
        legacy_path = cls.find_config_file("config.yaml")
        if legacy_path:
            return legacy_path

        # Development/package settings.json fallback
        dev_settings = Path.cwd() / "mini_agent" / "config" / "settings.json"
        if dev_settings.exists():
            return dev_settings
        package_settings = cls.get_package_dir() / "config" / "settings.json"
        if package_settings.exists():
            return package_settings

        # Fallback to package settings.json for error message purposes
        return package_settings
