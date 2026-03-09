"""Shared runtime construction for CLI and IM channels."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from mini_agent.config import Config
from mini_agent.llm import LLMClient
from mini_agent.retry import RetryConfig as RetryConfigBase
from mini_agent.schema import LLMProvider
from mini_agent.tools.base import Tool
from mini_agent.tools.bash_tool import BashKillTool, BashOutputTool, BashTool
from mini_agent.tools.file_tools import EditTool, ReadTool, WriteTool
from mini_agent.tools.mcp_loader import load_mcp_tools_async, set_mcp_timeout_config
from mini_agent.tools.note_tool import SessionNoteTool
from mini_agent.tools.skill_tool import create_skill_tools


LogFn = Callable[[str], None] | None


@dataclass
class RuntimeBundle:
    """Reusable runtime components for creating Agent sessions."""

    llm_client: LLMClient
    base_tools: list[Tool]
    system_prompt: str
    skill_loader: object | None = None


def _emit(log: LogFn, message: str) -> None:
    if log is not None:
        log(message)


def create_llm_client(config: Config, on_retry: Callable[[Exception, int], None] | None = None) -> LLMClient:
    """Create an LLM client from project config."""
    retry_cfg = config.llm.retry
    retry_config = RetryConfigBase(
        enabled=retry_cfg.enabled,
        max_retries=retry_cfg.max_retries,
        initial_delay=retry_cfg.initial_delay,
        max_delay=retry_cfg.max_delay,
        exponential_base=retry_cfg.exponential_base,
        retryable_exceptions=(Exception,),
    )

    provider = LLMProvider.ANTHROPIC if config.llm.provider.lower() == "anthropic" else LLMProvider.OPENAI

    llm_client = LLMClient(
        api_key=config.llm.api_key,
        provider=provider,
        api_base=config.llm.api_base,
        model=config.llm.model,
        retry_config=retry_config if retry_cfg.enabled else None,
    )

    if retry_cfg.enabled and on_retry is not None:
        llm_client.retry_callback = on_retry

    return llm_client


def apply_runtime_identity_prompt(prompt: str, config: Config) -> str:
    """Inject runtime model identity and disclosure guardrails."""
    rendered = prompt.replace("{MODEL_NAME}", config.llm.model)
    rendered = rendered.replace("{MODEL_PROVIDER}", config.llm.provider)
    rendered += (
        "\n\n## Runtime Identity Guardrails\n"
        "- If asked who you are, answer: Mini-Agent, an open-source assistant in this project.\n"
        f"- If asked which model you are using, answer with the current configured model: {config.llm.model} "
        f"(provider: {config.llm.provider}).\n"
        "- Keep this answer factual and do not invent model details.\n"
    )
    return rendered


def load_system_prompt(config: Config, log: LogFn = None) -> str:
    """Load and normalize system prompt for all channel entrypoints."""
    system_prompt_path = Config.find_config_file(config.agent.system_prompt_path)
    if system_prompt_path and system_prompt_path.exists():
        prompt = system_prompt_path.read_text(encoding="utf-8")
        _emit(log, f"loaded system prompt (from: {system_prompt_path})")
    else:
        prompt = (
            "You are Mini-Agent, an open-source AI assistant focused on practical task execution. "
            "If asked which model you use, answer truthfully with the runtime configuration."
        )
        _emit(log, "system prompt not found, using default")

    return apply_runtime_identity_prompt(prompt, config)


async def initialize_base_tools(config: Config, log: LogFn = None) -> tuple[list[Tool], object | None]:
    """Initialize tools that are independent of per-session workspace."""
    tools: list[Tool] = []
    skill_loader = None

    if config.tools.enable_bash:
        tools.append(BashOutputTool())
        _emit(log, "loaded Bash Output tool")

        tools.append(BashKillTool())
        _emit(log, "loaded Bash Kill tool")

    if config.tools.enable_skills:
        _emit(log, "loading Claude Skills...")
        try:
            skills_path = Path(config.tools.skills_dir).expanduser()
            if skills_path.is_absolute():
                skills_dir = str(skills_path)
            else:
                search_paths = [
                    skills_path,
                    Path("mini_agent") / skills_path,
                    Config.get_package_dir() / skills_path,
                ]
                skills_dir = str(skills_path)
                for path in search_paths:
                    if path.exists():
                        skills_dir = str(path.resolve())
                        break

            skill_tools, skill_loader = create_skill_tools(skills_dir)
            if skill_tools:
                tools.extend(skill_tools)
                _emit(log, "loaded Skill tool (get_skill)")
            else:
                _emit(log, "no available Skills found")
        except Exception as exc:
            _emit(log, f"failed to load Skills: {exc}")

    if config.tools.enable_mcp:
        _emit(log, "loading MCP tools...")
        try:
            mcp_cfg = config.tools.mcp
            set_mcp_timeout_config(
                connect_timeout=mcp_cfg.connect_timeout,
                execute_timeout=mcp_cfg.execute_timeout,
                sse_read_timeout=mcp_cfg.sse_read_timeout,
            )
            _emit(
                log,
                "MCP timeouts: "
                f"connect={mcp_cfg.connect_timeout}s, "
                f"execute={mcp_cfg.execute_timeout}s, "
                f"sse_read={mcp_cfg.sse_read_timeout}s",
            )

            mcp_config_path = Config.find_config_file(config.tools.mcp_config_path)
            if mcp_config_path:
                mcp_tools = await load_mcp_tools_async(str(mcp_config_path))
                if mcp_tools:
                    tools.extend(mcp_tools)
                    _emit(log, f"loaded {len(mcp_tools)} MCP tools (from: {mcp_config_path})")
                else:
                    _emit(log, "no available MCP tools found")
            else:
                _emit(log, f"MCP config file not found: {config.tools.mcp_config_path}")
        except Exception as exc:
            _emit(log, f"failed to load MCP tools: {exc}")

    return tools, skill_loader


def add_workspace_tools(
    tools: list[Tool],
    config: Config,
    workspace_dir: Path,
    include_recall_notes: bool = False,
) -> None:
    """Add workspace-dependent tools to a session tool list."""
    workspace_dir.mkdir(parents=True, exist_ok=True)

    if config.tools.enable_bash:
        tools.append(BashTool(workspace_dir=str(workspace_dir)))

    if config.tools.enable_file_tools:
        tools.extend(
            [
                ReadTool(workspace_dir=str(workspace_dir)),
                WriteTool(workspace_dir=str(workspace_dir)),
                EditTool(workspace_dir=str(workspace_dir)),
            ]
        )

    if config.tools.enable_note:
        memory_file = str(workspace_dir / ".agent_memory.json")
        tools.append(SessionNoteTool(memory_file=memory_file))
        if include_recall_notes:
            from mini_agent.tools.note_tool import RecallNoteTool

            tools.append(RecallNoteTool(memory_file=memory_file))


async def build_runtime_bundle(
    config: Config,
    log: LogFn = None,
    on_retry: Callable[[Exception, int], None] | None = None,
) -> RuntimeBundle:
    """Build reusable runtime components for Agent session creation."""
    base_tools, skill_loader = await initialize_base_tools(config, log=log)
    llm_client = create_llm_client(config, on_retry=on_retry)
    system_prompt = load_system_prompt(config, log=log)

    if skill_loader:
        skills_metadata = skill_loader.get_skills_metadata_prompt()
        if skills_metadata:
            system_prompt = system_prompt.replace("{SKILLS_METADATA}", skills_metadata)
            _emit(log, f"injected {len(skill_loader.loaded_skills)} skills metadata into system prompt")
        else:
            system_prompt = system_prompt.replace("{SKILLS_METADATA}", "")
    else:
        system_prompt = system_prompt.replace("{SKILLS_METADATA}", "")

    return RuntimeBundle(
        llm_client=llm_client,
        base_tools=base_tools,
        system_prompt=system_prompt,
        skill_loader=skill_loader,
    )
