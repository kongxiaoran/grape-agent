"""
Grape Agent - Interactive Runtime Example

Usage:
    grape-agent [--workspace DIR] [--task TASK]

Examples:
    grape-agent                              # Use current directory as workspace (interactive mode)
    grape-agent --workspace /path/to/dir     # Use specific workspace directory (interactive mode)
    grape-agent --task "create a file"       # Execute a task non-interactively
"""

import argparse
import asyncio
import importlib.metadata
import inspect
import os
import platform
import re
import shutil
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path
from time import perf_counter
from typing import List
from uuid import uuid4

from prompt_toolkit import PromptSession
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.completion import Completer, Completion, WordCompleter
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.styles import Style

from mini_agent.agent import Agent
from mini_agent.agents import AgentRegistry, SessionOrchestrator, SubagentPolicy
from mini_agent.channels.runtime import ChannelRuntime, build_default_registry
from mini_agent.channels.types import ChannelContext
from mini_agent.channels.logging import set_channel_log_quiet
from mini_agent.config import Config
from mini_agent.cron import CronDelivery, CronExecutor, CronScheduler, CronStore
from mini_agent.gateway.handlers import register_builtin_handlers
from mini_agent.gateway.protocol import GatewayContext
from mini_agent.gateway.router import GatewayRouter
from mini_agent.gateway.server import GatewayServer
from mini_agent.runtime_factory import (
    add_workspace_tools as add_workspace_tools_shared,
    create_turn_memory_hook,
    build_session_tools,
    build_runtime_bundle,
    initialize_base_tools as initialize_base_tools_shared,
)
from mini_agent.session_store import AgentSessionStore
from mini_agent.tools.base import Tool
from mini_agent.tools.sessions_history_tool import SessionsHistoryTool
from mini_agent.tools.sessions_list_tool import SessionsListTool
from mini_agent.tools.sessions_send_tool import SessionsSendTool
from mini_agent.tools.sessions_spawn_tool import SessionsSpawnTool
from mini_agent.tools.mcp_loader import cleanup_mcp_connections
from mini_agent.ui import ConsoleRenderer
from mini_agent.utils import calculate_display_width, pad_to_width, truncate_with_ellipsis


# ANSI color codes
class Colors:
    """Terminal color definitions"""

    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"

    # Foreground colors
    BLACK = "\033[30m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"

    # Bright colors
    BRIGHT_BLACK = "\033[90m"
    BRIGHT_RED = "\033[91m"
    BRIGHT_GREEN = "\033[92m"
    BRIGHT_YELLOW = "\033[93m"
    BRIGHT_BLUE = "\033[94m"
    BRIGHT_MAGENTA = "\033[95m"
    BRIGHT_CYAN = "\033[96m"
    BRIGHT_WHITE = "\033[97m"

    # Background colors
    BG_RED = "\033[41m"
    BG_GREEN = "\033[42m"
    BG_YELLOW = "\033[43m"
    BG_BLUE = "\033[44m"
    BG_BLACK = "\033[40m"
    SOFT_BORDER = "\033[38;5;114m"
    SOFT_ACCENT = "\033[38;5;114m"


def get_agent_version() -> str:
    """Resolve grape-agent package version."""
    try:
        return importlib.metadata.version("grape-agent")
    except importlib.metadata.PackageNotFoundError:
        return "0.1.0"
    except Exception:
        return "0.1.0"


class CommandCompleter(Completer):
    """Custom completer for slash commands that shows suggestions immediately after typing /"""

    COMMANDS = ["/help", "/clear", "/history", "/stats", "/log", "/config", "/exit", "/quit", "/q"]

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor

        # Only show completions when text starts with /
        if not text.startswith("/"):
            return

        # Get the current word being typed
        word = text

        # Filter commands that start with what the user typed
        for cmd in self.COMMANDS:
            if cmd.startswith(word):
                yield Completion(
                    cmd,
                    start_position=-len(word),
                    display=cmd,
                )


ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*m")


def display_path(path: Path) -> str:
    """Display path with home abbreviation, e.g. /Users/kxr/a -> ~/a."""
    resolved = str(path.expanduser())
    home = str(Path.home())
    if resolved == home:
        return "~"
    prefix = home + "/"
    if resolved.startswith(prefix):
        return "~/" + resolved[len(prefix) :]
    return resolved


def wrap_display_text(text: str, width: int) -> list[str]:
    """Wrap text by terminal display width (ANSI-safe width calculation)."""
    if width <= 0:
        return [""]

    def take_by_width(s: str, limit: int) -> tuple[str, str]:
        if not s:
            return "", ""
        acc: list[str] = []
        used = 0
        for idx, ch in enumerate(s):
            ch_w = calculate_display_width(ch)
            if used + ch_w > limit:
                return "".join(acc), s[idx:]
            acc.append(ch)
            used += ch_w
        return "".join(acc), ""

    source = text.rstrip()
    if not source:
        return [""]

    words = source.split(" ")
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = word if not current else f"{current} {word}"
        if calculate_display_width(candidate) <= width:
            current = candidate
            continue

        if current:
            lines.append(current)
            current = ""

        if calculate_display_width(word) <= width:
            current = word
            continue

        remainder = word
        while remainder:
            part, remainder = take_by_width(remainder, width)
            if not part:
                break
            lines.append(part)

    if current:
        lines.append(current)

    if not lines:
        plain = ANSI_ESCAPE_RE.sub("", source)
        return [truncate_with_ellipsis(plain, width)] if plain else [""]
    return lines


def get_log_directory() -> Path:
    """Get the log directory path."""
    return Path.home() / ".grape-agent" / "log"


def show_log_directory(open_file_manager: bool = True, style: str = "legacy") -> None:
    """Show log directory contents and optionally open file manager.

    Args:
        open_file_manager: Whether to open the system file manager
    """
    log_dir = get_log_directory()

    if style == "claude":
        print(f"\n{Colors.DIM}Log Directory: {display_path(log_dir)}{Colors.RESET}")
    else:
        print(f"\n{Colors.BRIGHT_CYAN}📁 Log Directory: {log_dir}{Colors.RESET}")

    if not log_dir.exists() or not log_dir.is_dir():
        if style == "claude":
            print(f"{Colors.DIM}Log directory does not exist: {display_path(log_dir)}{Colors.RESET}\n")
        else:
            print(f"{Colors.RED}Log directory does not exist: {log_dir}{Colors.RESET}\n")
        return

    log_files = list(log_dir.glob("*.log"))

    if not log_files:
        print(f"{Colors.DIM}No log files found in directory.{Colors.RESET}\n")
        return

    # Sort by modification time (newest first)
    log_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)

    print(f"{Colors.DIM}{'─' * 60}{Colors.RESET}")
    if style == "claude":
        print(f"{Colors.DIM}Available Log Files (newest first):{Colors.RESET}")
    else:
        print(f"{Colors.BOLD}{Colors.BRIGHT_YELLOW}Available Log Files (newest first):{Colors.RESET}")

    for i, log_file in enumerate(log_files[:10], 1):
        mtime = datetime.fromtimestamp(log_file.stat().st_mtime)
        size = log_file.stat().st_size
        size_str = f"{size:,}" if size < 1024 else f"{size / 1024:.1f}K"
        if style == "claude":
            print(f"  {i:2d}. {log_file.name}")
            print(f"      {Colors.DIM}Modified: {mtime.strftime('%Y-%m-%d %H:%M:%S')}, Size: {size_str}{Colors.RESET}")
        else:
            print(f"  {Colors.GREEN}{i:2d}.{Colors.RESET} {Colors.BRIGHT_WHITE}{log_file.name}{Colors.RESET}")
            print(f"      {Colors.DIM}Modified: {mtime.strftime('%Y-%m-%d %H:%M:%S')}, Size: {size_str}{Colors.RESET}")

    if len(log_files) > 10:
        print(f"  {Colors.DIM}... and {len(log_files) - 10} more files{Colors.RESET}")

    print(f"{Colors.DIM}{'─' * 60}{Colors.RESET}")

    # Open file manager
    if open_file_manager:
        _open_directory_in_file_manager(log_dir)

    print()


def _open_directory_in_file_manager(directory: Path) -> None:
    """Open directory in system file manager (cross-platform)."""
    system = platform.system()

    try:
        if system == "Darwin":
            subprocess.run(["open", str(directory)], check=False)
        elif system == "Windows":
            subprocess.run(["explorer", str(directory)], check=False)
        elif system == "Linux":
            subprocess.run(["xdg-open", str(directory)], check=False)
    except FileNotFoundError:
        print(f"{Colors.YELLOW}Could not open file manager. Please navigate manually.{Colors.RESET}")
    except Exception as e:
        print(f"{Colors.YELLOW}Error opening file manager: {e}{Colors.RESET}")


def read_log_file(filename: str, style: str = "legacy") -> None:
    """Read and display a specific log file.

    Args:
        filename: The log filename to read
    """
    log_dir = get_log_directory()
    log_file = log_dir / filename

    if not log_file.exists() or not log_file.is_file():
        if style == "claude":
            print(f"\n{Colors.DIM}Log file not found: {display_path(log_file)}{Colors.RESET}\n")
        else:
            print(f"\n{Colors.RED}❌ Log file not found: {log_file}{Colors.RESET}\n")
        return

    if style == "claude":
        print(f"\n{Colors.DIM}Reading: {display_path(log_file)}{Colors.RESET}")
    else:
        print(f"\n{Colors.BRIGHT_CYAN}📄 Reading: {log_file}{Colors.RESET}")
    print(f"{Colors.DIM}{'─' * 80}{Colors.RESET}")

    try:
        with open(log_file, "r", encoding="utf-8") as f:
            content = f.read()
        print(content)
        print(f"{Colors.DIM}{'─' * 80}{Colors.RESET}")
        if style == "claude":
            print(f"\n{Colors.DIM}End of file{Colors.RESET}\n")
        else:
            print(f"\n{Colors.GREEN}✅ End of file{Colors.RESET}\n")
    except Exception as e:
        if style == "claude":
            print(f"\n{Colors.DIM}Error reading file: {e}{Colors.RESET}\n")
        else:
            print(f"\n{Colors.RED}❌ Error reading file: {e}{Colors.RESET}\n")


def print_banner(style: str = "legacy"):
    """Print welcome banner with proper alignment"""
    if style == "claude":
        # Claude style: minimal, no box
        print()
        return

    BOX_WIDTH = 58
    banner_text = f"{Colors.BOLD}🤖 Grape Agent - Multi-turn Interactive Session{Colors.RESET}"
    banner_width = calculate_display_width(banner_text)

    # Center the text with proper padding
    total_padding = BOX_WIDTH - banner_width
    left_padding = total_padding // 2
    right_padding = total_padding - left_padding

    print()
    print(f"{Colors.BOLD}{Colors.BRIGHT_CYAN}╔{'═' * BOX_WIDTH}╗{Colors.RESET}")
    print(
        f"{Colors.BOLD}{Colors.BRIGHT_CYAN}║{Colors.RESET}{' ' * left_padding}{banner_text}{' ' * right_padding}{Colors.BOLD}{Colors.BRIGHT_CYAN}║{Colors.RESET}"
    )
    print(f"{Colors.BOLD}{Colors.BRIGHT_CYAN}╚{'═' * BOX_WIDTH}╝{Colors.RESET}")
    print()


def print_help(style: str = "legacy"):
    """Print help information"""
    if style == "claude":
        help_text = """
Available Commands:
  /help       Show this help message
  /clear      Clear session history (keep system prompt)
  /history    Show current session message count
  /stats      Show session statistics
  /log        Show log directory and recent files
  /log <file> Read a specific log file
  /config     Show current config file path
  /config <path>  Switch to specified config file
  /exit       Exit program (also: exit, quit, q)

Keyboard Shortcuts:
  Esc         Cancel current agent execution
  Ctrl+C      Exit program
  Ctrl+U      Clear current input line
  Ctrl+L      Clear screen
  Ctrl+J      Insert newline (also Ctrl+Enter)
  Tab         Auto-complete commands
  Up/Down     Browse command history
  Right       Accept auto-suggestion
"""
        print(f"\n{Colors.DIM}{help_text.strip()}{Colors.RESET}\n")
        return

    help_text = f"""
{Colors.BOLD}{Colors.BRIGHT_YELLOW}Available Commands:{Colors.RESET}
  {Colors.BRIGHT_GREEN}/help{Colors.RESET}      - Show this help message
  {Colors.BRIGHT_GREEN}/clear{Colors.RESET}     - Clear session history (keep system prompt)
  {Colors.BRIGHT_GREEN}/history{Colors.RESET}   - Show current session message count
  {Colors.BRIGHT_GREEN}/stats{Colors.RESET}     - Show session statistics
  {Colors.BRIGHT_GREEN}/log{Colors.RESET}       - Show log directory and recent files
  {Colors.BRIGHT_GREEN}/log <file>{Colors.RESET} - Read a specific log file
  {Colors.BRIGHT_GREEN}/config{Colors.RESET}    - Show current config file path
  {Colors.BRIGHT_GREEN}/config <path>{Colors.RESET} - Switch to specified config file
  {Colors.BRIGHT_GREEN}/exit{Colors.RESET}      - Exit program (also: exit, quit, q)

{Colors.BOLD}{Colors.BRIGHT_YELLOW}Keyboard Shortcuts:{Colors.RESET}
  {Colors.BRIGHT_CYAN}Esc{Colors.RESET}        - Cancel current agent execution
  {Colors.BRIGHT_CYAN}Ctrl+C{Colors.RESET}     - Exit program
  {Colors.BRIGHT_CYAN}Ctrl+U{Colors.RESET}     - Clear current input line
  {Colors.BRIGHT_CYAN}Ctrl+L{Colors.RESET}     - Clear screen
  {Colors.BRIGHT_CYAN}Ctrl+J{Colors.RESET}     - Insert newline (also Ctrl+Enter)
  {Colors.BRIGHT_CYAN}Tab{Colors.RESET}        - Auto-complete commands
  {Colors.BRIGHT_CYAN}↑/↓{Colors.RESET}        - Browse command history
  {Colors.BRIGHT_CYAN}→{Colors.RESET}          - Accept auto-suggestion

{Colors.BOLD}{Colors.BRIGHT_YELLOW}Usage:{Colors.RESET}
  - Enter your task directly, Agent will help you complete it
  - Agent remembers all conversation content in this session
  - Use {Colors.BRIGHT_GREEN}/clear{Colors.RESET} to start a new session
  - Press {Colors.BRIGHT_CYAN}Enter{Colors.RESET} to submit your message
  - Use {Colors.BRIGHT_CYAN}Ctrl+J{Colors.RESET} to insert line breaks within your message
"""
    print(help_text)


def print_session_info(agent: Agent, workspace_dir: Path, model: str, style: str = "legacy"):
    """Print session information with proper alignment"""
    if style == "claude":
        # Claude style: minimal info, no box
        print(f"{Colors.DIM}Model: {model} · Workspace: {workspace_dir}{Colors.RESET}")
        print()
        return

    BOX_WIDTH = 58

    def print_info_line(text: str):
        """Print a single info line with proper padding"""
        # Account for leading space
        text_width = calculate_display_width(text)
        padding = max(0, BOX_WIDTH - 1 - text_width)
        print(f"{Colors.DIM}│{Colors.RESET} {text}{' ' * padding}{Colors.DIM}│{Colors.RESET}")

    # Top border
    print(f"{Colors.DIM}┌{'─' * BOX_WIDTH}┐{Colors.RESET}")

    # Header (centered)
    header_text = f"{Colors.BRIGHT_CYAN}Session Info{Colors.RESET}"
    header_width = calculate_display_width(header_text)
    header_padding_total = BOX_WIDTH - 1 - header_width  # -1 for leading space
    header_padding_left = header_padding_total // 2
    header_padding_right = header_padding_total - header_padding_left
    print(f"{Colors.DIM}│{Colors.RESET} {' ' * header_padding_left}{header_text}{' ' * header_padding_right}{Colors.DIM}│{Colors.RESET}")

    # Divider
    print(f"{Colors.DIM}├{'─' * BOX_WIDTH}┤{Colors.RESET}")

    # Info lines
    print_info_line(f"Model: {model}")
    print_info_line(f"Workspace: {workspace_dir}")
    print_info_line(f"Message History: {len(agent.messages)} messages")
    print_info_line(f"Available Tools: {len(agent.tools)} tools")

    # Bottom border
    print(f"{Colors.DIM}└{'─' * BOX_WIDTH}┘{Colors.RESET}")
    print()
    print(f"{Colors.DIM}Type {Colors.BRIGHT_GREEN}/help{Colors.DIM} for help, {Colors.BRIGHT_GREEN}/exit{Colors.DIM} to quit{Colors.RESET}")
    print()


def print_claude_welcome_card(
    *,
    version: str,
    agent_id: str,
    model: str,
    provider: str,
    workspace_dir: Path,
    log_dir: Path,
    skills_count: int,
    tools_count: int,
    base_tools_count: int,
    gateway_enabled: bool,
    gateway_addr: str,
    feishu_enabled: bool,
    feishu_running: bool,
) -> None:
    """Print compact startup card inspired by Claude Code."""
    terminal_width = shutil.get_terminal_size(fallback=(100, 24)).columns
    card_width = max(50, min(104, terminal_width - 2))
    compact_mode = card_width < 82
    workspace_display = display_path(workspace_dir)
    log_display = display_path(log_dir)

    def row_single(text: str, width: int) -> None:
        cell = pad_to_width(text, width)
        print(f"{Colors.DIM}│{Colors.RESET}{cell}{Colors.DIM}│{Colors.RESET}")

    def row_split(left: str, right: str, left_w: int, right_w: int) -> None:
        left_cell = pad_to_width(left, left_w)
        right_cell = pad_to_width(right, right_w)
        print(f"{Colors.DIM}│{Colors.RESET}{left_cell}{Colors.DIM}│{Colors.RESET}{right_cell}{Colors.DIM}│{Colors.RESET}")

    def row_single_wrapped(text: str, width: int) -> None:
        wrapped = wrap_display_text(text, width)
        for segment in wrapped:
            row_single(segment, width)

    def row_split_wrapped(left: str, right: str, left_w: int, right_w: int) -> None:
        left_lines = wrap_display_text(left, left_w)
        right_lines = wrap_display_text(right, right_w)
        count = max(len(left_lines), len(right_lines))
        for idx in range(count):
            l = left_lines[idx] if idx < len(left_lines) else ""
            r = right_lines[idx] if idx < len(right_lines) else ""
            row_split(l, r, left_w, right_w)

    def expand_block_lines(items: list[str], width: int) -> list[str]:
        expanded: list[str] = []
        for item in items:
            if not item:
                expanded.append("")
                continue
            # Preserve logo whitespace; do not word-wrap glyph-art lines.
            if any(ch in item for ch in ("█", "●", "○", "◜", "◝", "╲", "╱", "/", "\\", "(", ")", "-", "'", "╵")):
                if calculate_display_width(item) > width:
                    expanded.append(truncate_with_ellipsis(item, width))
                else:
                    expanded.append(item)
                continue
            expanded.extend(wrap_display_text(item, width))
        return expanded

    def compose_logo_meta_rows(
        logo_items: list[str],
        meta_items: list[str],
        total_width: int,
    ) -> list[str]:
        """Compose a compact two-column block inside one cell: logo (left) + metadata (right)."""
        if total_width < 24:
            # Too narrow for side-by-side; fallback to stacked content.
            return [*logo_items, "", *meta_items]

        logo_width = max(calculate_display_width(item) for item in logo_items)
        logo_col = min(max(10, logo_width + 1), max(10, total_width // 2))
        meta_col = max(8, total_width - logo_col)

        rows: list[str] = []
        row_count = max(len(logo_items), len(meta_items))
        for idx in range(row_count):
            logo = logo_items[idx] if idx < len(logo_items) else ""
            meta = meta_items[idx] if idx < len(meta_items) else ""
            rows.append(pad_to_width(logo, logo_col) + pad_to_width(meta, meta_col))
        return rows

    def status_text(enabled: bool, running: bool | None = None) -> str:
        if running is None:
            return "enabled" if enabled else "disabled"
        if not enabled:
            return "disabled"
        return "connected" if running else "enabled"

    title = f" Grape Agent v{version} "
    title_padding = max(0, card_width - calculate_display_width(title))
    runtime_line = f"gateway {gateway_addr} ({status_text(gateway_enabled)}) | feishu {status_text(feishu_enabled, feishu_running)}"
    loaded_line = f"skills={skills_count} tools={tools_count} (base={base_tools_count})"
    grape_dot = f"{Colors.SOFT_ACCENT}●{Colors.RESET}"
    logo_lines = [
        "      --      ",
        "     /  \\     ",
        f"   ( {grape_dot} {grape_dot} )   ",
        f"  ( {grape_dot} {grape_dot} {grape_dot} )  ",
        f"   ( {grape_dot} {grape_dot} )   ",
        f"    ( {grape_dot} )    ",
        "      '       ",
    ]

    print()
    print(f"{Colors.SOFT_BORDER}┌{title}{'─' * title_padding}┐{Colors.RESET}")

    if compact_mode:
        row_single_wrapped(f" {Colors.BOLD}Welcome back!{Colors.RESET}", card_width)
        row_single("", card_width)
        profile_rows = compose_logo_meta_rows(
            logo_lines,
            [
                f"{model} · {provider}",
                f"{workspace_display}",
            ],
            card_width,
        )
        for line in profile_rows:
            row_single(line, card_width)
        row_single("", card_width)
        details = [
            f" {Colors.DIM}Agent{Colors.RESET}: {agent_id}",
            f" {Colors.DIM}Versions{Colors.RESET}: grape-agent={version} python={platform.python_version()}",
            f" {Colors.DIM}Log Dir{Colors.RESET}: {log_display}",
            f" {Colors.DIM}Loaded{Colors.RESET}: {loaded_line}",
            f" {Colors.DIM}Runtime{Colors.RESET}: {runtime_line}",
        ]
        for line in details:
            row_single_wrapped(line, card_width)
    else:
        left_width = max(30, min(56, int(card_width * 0.5)))
        right_width = card_width - left_width - 1
        left_profile_rows = compose_logo_meta_rows(
            logo_lines,
            [
                f"{model} · {provider}",
                f"{workspace_display}",
            ],
            left_width - 1,
        )
        left_lines = [
            f" {Colors.BOLD}Welcome back!{Colors.RESET}",
            "",
            *left_profile_rows,
        ]
        right_lines = [
            f" {Colors.SOFT_ACCENT}Runtime{Colors.RESET}",
            f" {runtime_line}",
            f" {Colors.DIM}Agent{Colors.RESET}: {agent_id}",
            f" {Colors.DIM}Versions{Colors.RESET}: grape-agent={version} python={platform.python_version()}",
            f" {Colors.DIM}Log Dir{Colors.RESET}: {log_display}",
            f" {Colors.DIM}Loaded{Colors.RESET}: {loaded_line}",
        ]
        left_expanded = expand_block_lines(left_lines, left_width)
        right_expanded = expand_block_lines(right_lines, right_width)
        for idx in range(max(len(left_expanded), len(right_expanded))):
            left_text = left_expanded[idx] if idx < len(left_expanded) else ""
            right_text = right_expanded[idx] if idx < len(right_expanded) else ""
            row_split(left_text, right_text, left_width, right_width)

    print(f"{Colors.SOFT_BORDER}└{'─' * card_width}┘{Colors.RESET}")
    print(f"{Colors.DIM}Tip: /help for shortcuts, Esc to cancel current execution.{Colors.RESET}")
    print()


def print_stats(agent: Agent, session_start: datetime):
    """Print session statistics"""
    duration = datetime.now() - session_start
    hours, remainder = divmod(int(duration.total_seconds()), 3600)
    minutes, seconds = divmod(remainder, 60)

    # Count different types of messages
    user_msgs = sum(1 for m in agent.messages if m.role == "user")
    assistant_msgs = sum(1 for m in agent.messages if m.role == "assistant")
    tool_msgs = sum(1 for m in agent.messages if m.role == "tool")

    print(f"\n{Colors.BOLD}{Colors.BRIGHT_CYAN}会话统计:{Colors.RESET}")
    print(f"{Colors.DIM}{'─' * 40}{Colors.RESET}")
    print(f"  会话时长: {hours:02d}:{minutes:02d}:{seconds:02d}")
    print(f"  消息总数: {len(agent.messages)}")
    print(f"    - 用户消息: {Colors.BRIGHT_GREEN}{user_msgs}{Colors.RESET}")
    print(f"    - 助手回复: {Colors.BRIGHT_BLUE}{assistant_msgs}{Colors.RESET}")
    print(f"    - 工具调用: {Colors.BRIGHT_YELLOW}{tool_msgs}{Colors.RESET}")
    print(f"  可用工具数: {len(agent.tools)}")
    if agent.api_total_tokens > 0:
        print(f"  API Tokens: {Colors.BRIGHT_MAGENTA}{agent.api_total_tokens:,}{Colors.RESET}")
    print(f"{Colors.DIM}{'─' * 40}{Colors.RESET}\n")


def format_elapsed_compact(seconds: float) -> str:
    """Format elapsed seconds into compact human-readable text."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    total = int(seconds)
    minutes, sec = divmod(total, 60)
    if minutes < 60:
        return f"{minutes}m {sec}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes}m"


def format_tokens_compact(tokens: int) -> str:
    """Format token count like 1.1k / 2.3m."""
    if tokens >= 1_000_000:
        return f"{tokens / 1_000_000:.1f}m"
    if tokens >= 1_000:
        return f"{tokens / 1_000:.1f}k"
    return str(tokens)


def _normalize_user_id(raw: str | None) -> str:
    """Normalize user id to a stable safe token."""
    text = str(raw or "").strip()
    if not text:
        return ""
    normalized = re.sub(r"[^a-zA-Z0-9._-]+", "_", text)
    return normalized.strip("._-")


def resolve_cli_user_id(user_id_override: str | None = None) -> str:
    """Resolve CLI user id for memory isolation.

    Priority:
    1) --user-id
    2) GRAPE_USER_ID env var
    3) ~/.grape/user_id persisted value (auto-created if missing)
    """
    cli_user = _normalize_user_id(user_id_override)
    if cli_user:
        return cli_user

    env_user = _normalize_user_id(os.environ.get("GRAPE_USER_ID"))
    if env_user:
        return env_user

    user_id_file = Path.home() / ".grape" / "user_id"
    try:
        if user_id_file.exists():
            persisted = _normalize_user_id(user_id_file.read_text(encoding="utf-8"))
            if persisted:
                return persisted
    except Exception:
        pass

    generated = f"u_{uuid4().hex[:16]}"
    try:
        user_id_file.parent.mkdir(parents=True, exist_ok=True)
        user_id_file.write_text(f"{generated}\n", encoding="utf-8")
    except Exception:
        pass
    return generated


def parse_args() -> argparse.Namespace:
    """Parse command line arguments

    Returns:
        Parsed arguments
    """
    command_name = Path(sys.argv[0]).name if sys.argv and sys.argv[0] else "grape"

    parser = argparse.ArgumentParser(
        description="Grape Agent - AI assistant with file tools and MCP support",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  grape-agent                              # Use current directory as workspace
  grape-agent --workspace /path/to/dir     # Use specific workspace directory
  grape-agent log                          # Show log directory and recent files
  grape-agent log agent_run_xxx.log        # Read a specific log file
        """,
    )
    parser.add_argument(
        "--workspace",
        "-w",
        type=str,
        default=None,
        help="Workspace directory (default: current directory)",
    )
    parser.add_argument(
        "--task",
        "-t",
        type=str,
        default=None,
        help="Execute a task non-interactively and exit",
    )
    parser.add_argument(
        "--version",
        "-v",
        action="version",
        version=f"{command_name} {get_agent_version()}",
    )
    parser.add_argument(
        "--ui-style",
        choices=["legacy", "compact", "claude"],
        default=None,
        help="Override terminal UI style for this run",
    )
    parser.add_argument(
        "--user-id",
        type=str,
        default=None,
        help="Stable user identifier for memory isolation (overrides GRAPE_USER_ID)",
    )

    # Subcommands
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # log subcommand
    log_parser = subparsers.add_parser("log", help="Show log directory or read log files")
    log_parser.add_argument(
        "filename",
        nargs="?",
        default=None,
        help="Log filename to read (optional, shows directory if omitted)",
    )

    return parser.parse_args()


async def initialize_base_tools(config: Config):
    """Initialize base tools (independent of workspace)

    These tools are loaded from package configuration and don't depend on workspace.
    Note: File tools are now workspace-dependent and initialized in add_workspace_tools()

    Args:
        config: Configuration object

    Returns:
        Tuple of (list of tools, skill loader if skills enabled)
    """

    def _log(message: str) -> None:
        lower = message.lower()
        if lower.startswith("loading "):
            print(f"{Colors.BRIGHT_CYAN}{message[0].upper() + message[1:]}{Colors.RESET}")
            return
        if "injected" in lower:
            print(f"{Colors.GREEN}✅ {message[0].upper() + message[1:]}{Colors.RESET}")
            return
        if lower.startswith("loaded ") and "mcp timeouts" not in lower:
            print(f"{Colors.GREEN}✅ {message[0].upper() + message[1:]}{Colors.RESET}")
            return
        if lower.startswith("mcp timeouts"):
            print(f"{Colors.DIM}  {message}{Colors.RESET}")
            return
        print(f"{Colors.YELLOW}⚠️  {message[0].upper() + message[1:]}{Colors.RESET}")

    tools, skill_loader = await initialize_base_tools_shared(config, log=_log)
    print()
    return tools, skill_loader


def add_workspace_tools(tools: List[Tool], config: Config, workspace_dir: Path):
    """Add workspace-dependent tools

    These tools need to know the workspace directory.

    Args:
        tools: Existing tools list to add to
        config: Configuration object
        workspace_dir: Workspace directory path
    """
    add_workspace_tools_shared(tools=tools, config=config, workspace_dir=workspace_dir)
    if config.tools.enable_bash:
        print(f"{Colors.GREEN}✅ Loaded Bash tool (cwd: {workspace_dir}){Colors.RESET}")
    if config.tools.enable_file_tools:
        print(f"{Colors.GREEN}✅ Loaded file operation tools (workspace: {workspace_dir}){Colors.RESET}")
    if config.tools.enable_note:
        print(f"{Colors.GREEN}✅ Loaded session note tool{Colors.RESET}")


async def _quiet_cleanup():
    """Clean up MCP connections, suppressing noisy asyncgen teardown tracebacks."""
    # Silence the asyncgen finalization noise that anyio/mcp emits when
    # stdio_client's task group is torn down across tasks.  The handler is
    # intentionally NOT restored: asyncgen finalization happens during
    # asyncio.run() shutdown (after run_agent returns), so restoring the
    # handler here would still let the noise through.  Since this runs
    # right before process exit, swallowing late exceptions is safe.
    loop = asyncio.get_event_loop()
    loop.set_exception_handler(lambda _loop, _ctx: None)
    try:
        await cleanup_mcp_connections()
    except Exception:
        pass


async def run_agent(
    workspace_dir: Path,
    task: str = None,
    ui_style_override: str | None = None,
    user_id_override: str | None = None,
):
    """Run Agent in interactive or non-interactive mode.

    Args:
        workspace_dir: Workspace directory path
        task: If provided, execute this task and exit (non-interactive mode)
    """
    session_start = datetime.now()

    # 1. Load configuration from package directory
    config_path = Config.get_default_config_path()

    if not config_path.exists():
        print(f"{Colors.RED}❌ Configuration file not found{Colors.RESET}")
        print()
        print(f"{Colors.BRIGHT_CYAN}📦 Configuration Search Path:{Colors.RESET}")
        print(f"  {Colors.DIM}1) mini_agent/config/settings.json{Colors.RESET} (development)")
        print(f"  {Colors.DIM}2) ~/.grape/settings.json{Colors.RESET} (user, recommended)")
        print(f"  {Colors.DIM}3) <package>/config/settings.json{Colors.RESET} (installed)")
        print(f"  {Colors.DIM}4) ~/.grape-agent/config/config.yaml{Colors.RESET} (legacy fallback)")
        print()
        print(f"{Colors.BRIGHT_YELLOW}📝 Manual Setup:{Colors.RESET}")
        user_config_dir = Path.home() / ".grape"
        example_config = Config.get_package_dir() / "config" / "settings.json"
        print(f"  {Colors.DIM}mkdir -p {user_config_dir}{Colors.RESET}")
        print(f"  {Colors.DIM}cp {example_config} {user_config_dir}/settings.json{Colors.RESET}")
        print(f"  {Colors.DIM}# Then edit {user_config_dir}/settings.json to add your API Key{Colors.RESET}")
        print()
        return

    try:
        config = Config.from_yaml(config_path)
    except FileNotFoundError:
        print(f"{Colors.RED}❌ Error: Configuration file not found: {config_path}{Colors.RESET}")
        return
    except ValueError as e:
        print(f"{Colors.RED}❌ Error: {e}{Colors.RESET}")
        print(f"{Colors.YELLOW}Please check the configuration file format{Colors.RESET}")
        return
    except Exception as e:
        print(f"{Colors.RED}❌ Error: Failed to load configuration file: {e}{Colors.RESET}")
        return

    if ui_style_override:
        config.ui.style = ui_style_override

    cli_user_id = resolve_cli_user_id(user_id_override)

    # Quiet noisy Feishu/Lark SDK logging in CLI mode.
    try:
        import logging

        for name in ("Lark", "lark", "lark_oapi"):
            logger = logging.getLogger(name)
            logger.setLevel(logging.WARNING)
            logger.propagate = False
    except Exception:
        pass

    session_store = AgentSessionStore()
    agent_registry = AgentRegistry(config)
    subagent_policy = SubagentPolicy.from_config(config)
    set_channel_log_quiet(config.ui.style == "claude")
    channel_context = ChannelContext(config=config, config_path=config_path, session_store=session_store)
    channel_runtime = ChannelRuntime(
        registry=build_default_registry(),
        context=channel_context,
    )
    gateway_server: GatewayServer | None = None
    cron_store: CronStore | None = None
    cron_scheduler: CronScheduler | None = None

    try:
        def print_user_input_line(text: str) -> None:
            if config.ui.style != "claude":
                return
            lines = text.splitlines() or [text]
            for line in lines:
                print(f"{Colors.BG_BLACK}{Colors.BRIGHT_WHITE} {line} {Colors.RESET}")
        channel_context.on_inbound_message = lambda text: print_user_input_line(text)

        def on_retry(exception: Exception, attempt: int):
            print(f"\n{Colors.BRIGHT_YELLOW}⚠️  LLM call failed (attempt {attempt}): {str(exception)}{Colors.RESET}")
            initial_delay = config.llm.retry.initial_delay
            exponential_base = config.llm.retry.exponential_base
            max_delay = config.llm.retry.max_delay
            next_delay = min(max_delay, initial_delay * (exponential_base ** max(0, attempt - 1)))
            print(f"{Colors.DIM}   Retrying in {next_delay:.1f}s (attempt {attempt + 1})...{Colors.RESET}")

        def runtime_log(message: str) -> None:
            lower = message.lower()
            normalized = message[0].upper() + message[1:] if message else message
            if config.ui.style == "claude":
                if lower.startswith(("loaded ", "loading ", "injected ", "mcp timeouts", "no available mcp tools")):
                    return
                print(f"{Colors.DIM}{normalized}{Colors.RESET}")
                return
            if lower.startswith("loading "):
                print(f"{Colors.BRIGHT_CYAN}{normalized}{Colors.RESET}")
                return
            if lower.startswith("loaded ") and "mcp timeouts" not in lower:
                print(f"{Colors.GREEN}✅ {normalized}{Colors.RESET}")
                return
            if lower.startswith("injected "):
                print(f"{Colors.GREEN}✅ {normalized}{Colors.RESET}")
                return
            if lower.startswith("mcp timeouts"):
                print(f"{Colors.DIM}  {message}{Colors.RESET}")
                return
            print(f"{Colors.YELLOW}⚠️  {normalized}{Colors.RESET}")

        runtime_bundle_cache: dict[str, object] = {}
        runtime_cache_lock = asyncio.Lock()
        orchestrator: SessionOrchestrator | None = None

        async def get_runtime_bundle(agent_id: str):
            profile = agent_registry.get(agent_id)
            cache_key = profile.id
            cached = runtime_bundle_cache.get(cache_key)
            if cached is not None:
                return cached

            async with runtime_cache_lock:
                cached = runtime_bundle_cache.get(cache_key)
                if cached is not None:
                    return cached

                runtime_config = config.model_copy(deep=True)
                if profile.model:
                    runtime_config.llm.model = profile.model
                if profile.system_prompt_path:
                    runtime_config.agent.system_prompt_path = profile.system_prompt_path
                built = await build_runtime_bundle(config=runtime_config, log=runtime_log, on_retry=on_retry)
                runtime_bundle_cache[cache_key] = built
                return built

        async def create_managed_session(
            *,
            agent_id: str,
            channel: str,
            session_id: str,
            parent_key: str | None = None,
            depth: int = 0,
        ):
            profile = agent_registry.get(agent_id)
            resolved_agent_id = profile.id
            existing = session_store.get(channel, session_id, agent_id=resolved_agent_id)
            if existing is not None:
                return existing

            runtime_bundle = await get_runtime_bundle(resolved_agent_id)
            workspace_path = profile.workspace / channel / session_id
            workspace_path.mkdir(parents=True, exist_ok=True)
            session_key = session_store.make_key(channel, session_id, agent_id=resolved_agent_id)
            memory_sender_id = cli_user_id if channel in {"terminal", "cli"} else None

            def _factory() -> Agent:
                extra_tools: list[Tool] = []
                if orchestrator is not None and subagent_policy.enabled:
                    extra_tools.extend(
                        [
                            SessionsSpawnTool(orchestrator, session_key),
                            SessionsListTool(orchestrator, session_key),
                            SessionsHistoryTool(orchestrator, session_key),
                            SessionsSendTool(orchestrator, session_key),
                        ]
                    )
                deny_tool_names = set(subagent_policy.deny_tools_leaf) if subagent_policy.is_leaf(depth) else set()
                session_tools = build_session_tools(
                    base_tools=runtime_bundle.base_tools,
                    config=config,
                    workspace_dir=workspace_path,
                    include_recall_notes=True,
                    channel=channel,
                    chat_id=session_id,
                    sender_id=memory_sender_id,
                    agent_id=resolved_agent_id,
                    extra_tools=extra_tools,
                    deny_tool_names=deny_tool_names,
                    log=runtime_log,
                )
                turn_memory_hook = create_turn_memory_hook(
                    config=config,
                    channel=channel,
                    chat_id=session_id,
                    sender_id=memory_sender_id,
                    agent_id=resolved_agent_id,
                    log=runtime_log,
                )
                return Agent(
                    llm_client=runtime_bundle.llm_client,
                    system_prompt=runtime_bundle.system_prompt,
                    tools=session_tools,
                    max_steps=config.agent.max_steps,
                    workspace_dir=str(workspace_path),
                    ui_renderer=ConsoleRenderer.from_runtime(config.ui),
                    turn_memory_hook=turn_memory_hook,
                )

            return await session_store.get_or_create(
                channel=channel,
                session_id=session_id,
                factory=_factory,
                agent_id=resolved_agent_id,
                parent_key=parent_key,
                depth=depth,
            )

        orchestrator = SessionOrchestrator(
            session_store=session_store,
            create_session=create_managed_session,
            enabled=subagent_policy.enabled,
            max_depth=subagent_policy.max_depth,
        )
        channel_context.subagent_orchestrator = orchestrator

        await channel_runtime.start()

        main_runtime_bundle = await get_runtime_bundle(agent_registry.default_agent_id)

        if config.llm.retry.enabled and config.ui.style != "claude":
            print(f"{Colors.GREEN}✅ LLM retry mechanism enabled (max {config.llm.retry.max_retries} retries){Colors.RESET}")
        if config.ui.style != "claude":
            print()

        if config.cron.enabled:
            cron_store = CronStore(store_path=config.cron.store_path)
            cron_executor = CronExecutor(
                create_session=create_managed_session,
                default_timeout_sec=config.cron.default_timeout_sec,
            )
            cron_delivery = CronDelivery(channels_runtime=channel_runtime)
            cron_scheduler = CronScheduler(
                store=cron_store,
                executor=cron_executor,
                delivery=cron_delivery,
                poll_interval_sec=config.cron.poll_interval_sec,
                max_concurrency=config.cron.max_concurrency,
            )
            await cron_scheduler.start()

        gateway_ctx = GatewayContext(
            app_name="grape-agent",
            started_at=session_start,
            config=config,
            gateway_config=config.gateway,
            session_store=session_store,
            channels_runtime=channel_runtime,
            subagent_orchestrator=orchestrator,
            cron_store=cron_store,
            cron_scheduler=cron_scheduler,
        )
        gateway_router = GatewayRouter(context=gateway_ctx)
        register_builtin_handlers(gateway_router)
        gateway_server = GatewayServer(config=config.gateway, router=gateway_router)
        await gateway_server.start()

        terminal_session = await create_managed_session(
            agent_id=agent_registry.default_agent_id,
            channel="terminal",
            session_id="main",
        )
        agent = terminal_session.agent

        # 8. Display welcome information
        if not task and config.ui.style == "legacy":
            print_banner()
            print_session_info(agent, workspace_dir, main_runtime_bundle.llm_client.model)
        elif not task and config.ui.style == "claude":
            channels_snapshot = channel_runtime.snapshot()
            feishu_status = channels_snapshot.get("channels", {}).get("feishu", {})
            skill_loader = main_runtime_bundle.skill_loader
            skills_count = len(getattr(skill_loader, "loaded_skills", {})) if skill_loader is not None else 0
            print_claude_welcome_card(
                version=get_agent_version(),
                agent_id=terminal_session.agent_id,
                model=main_runtime_bundle.llm_client.model,
                provider=config.llm.provider,
                workspace_dir=workspace_dir,
                log_dir=get_log_directory(),
                skills_count=skills_count,
                tools_count=len(agent.tools),
                base_tools_count=len(main_runtime_bundle.base_tools),
                gateway_enabled=config.gateway.enabled,
                gateway_addr=f"{config.gateway.host}:{config.gateway.port}",
                feishu_enabled=bool(feishu_status.get("enabled", False)),
                feishu_running=bool(feishu_status.get("running", False)),
            )

        # 8.5 Non-interactive mode
        if task:
            if config.ui.style == "claude":
                print()
                print_user_input_line(task)
            else:
                print(
                    f"\n{Colors.BRIGHT_BLUE}Agent{Colors.RESET} {Colors.DIM}›{Colors.RESET} {Colors.DIM}Executing task...{Colors.RESET}\n"
                )
            agent.add_user_message(task)
            try:
                await agent.run()
            except Exception as e:
                print(f"\n{Colors.RED}❌ Error: {e}{Colors.RESET}")
            finally:
                print_stats(agent, session_start)
            return

        # 9. Setup prompt_toolkit session
        command_completer = CommandCompleter()

        if config.ui.style == "claude":
            prompt_style = Style.from_dict(
                {
                    "prompt": "#a0a0a0",
                    "separator": "#8a8a8a",
                }
            )
        else:
            prompt_style = Style.from_dict(
                {
                    "prompt": "#00ff00 bold",
                    "separator": "#666666",
                }
            )

        kb = KeyBindings()

        @kb.add("c-u")
        def _(event):
            event.current_buffer.reset()

        @kb.add("c-l")
        def _(event):
            event.app.renderer.clear()

        @kb.add("c-j")
        def _(event):
            event.current_buffer.insert_text("\n")

        history_file = Path.home() / ".grape-agent" / ".history"
        history_file.parent.mkdir(parents=True, exist_ok=True)
        session = PromptSession(
            history=FileHistory(str(history_file)),
            auto_suggest=AutoSuggestFromHistory(),
            completer=command_completer,
            style=prompt_style,
            key_bindings=kb,
        )
        prompt_async_supports_erase = "erase_when_done" in inspect.signature(session.prompt_async).parameters

        def _erase_prompt_echo(prompt_text: str, text: str) -> None:
            """Best-effort fallback when prompt_toolkit lacks erase_when_done."""
            if not text or not sys.stdout.isatty():
                return
            cols = max(20, shutil.get_terminal_size(fallback=(100, 24)).columns)
            width = max(1, calculate_display_width(prompt_text + text))
            wrapped_lines = max(1, (width + cols - 1) // cols)
            for _ in range(wrapped_lines):
                # Cursor to previous line start, then clear full line.
                sys.stdout.write("\x1b[F\x1b[2K")
            sys.stdout.write("\r")
            sys.stdout.flush()

        # 10. Interactive loop
        while True:
            try:
                if config.ui.style == "claude":
                    prompt_text = "> "
                    prompt_message = prompt_text
                else:
                    prompt_text = "You › "
                    prompt_message = [("class:prompt", "You"), ("", " › ")]
                prompt_kwargs = {
                    "multiline": False,
                    "enable_history_search": True,
                }
                if config.ui.style == "claude" and prompt_async_supports_erase:
                    prompt_kwargs["erase_when_done"] = True

                raw_input = await session.prompt_async(
                    prompt_message,
                    **prompt_kwargs,
                )
                if config.ui.style == "claude" and not prompt_async_supports_erase:
                    _erase_prompt_echo(prompt_text, raw_input)
                user_input = raw_input.strip()

                if not user_input:
                    continue

                if config.ui.style == "claude":
                    print_user_input_line(user_input)

                if user_input.startswith("/"):
                    command = user_input.lower()

                    if command in ["/exit", "/quit", "/q"]:
                        if config.ui.style == "claude":
                            print(f"\n{Colors.DIM}Goodbye.{Colors.RESET}\n")
                        else:
                            print(f"\n{Colors.BRIGHT_YELLOW}👋 Goodbye! Thanks for using Grape Agent{Colors.RESET}\n")
                        print_stats(agent, session_start)
                        break

                    elif command == "/help":
                        print_help(style=config.ui.style)
                        continue

                    elif command == "/clear":
                        old_count = len(agent.messages)
                        session_store.pop("terminal", "main", agent_id=terminal_session.agent_id)
                        terminal_session = await create_managed_session(
                            agent_id=terminal_session.agent_id,
                            channel="terminal",
                            session_id="main",
                        )
                        agent = terminal_session.agent
                        if config.ui.style == "claude":
                            print(f"{Colors.DIM}Cleared {old_count - 1} messages, started a new session.{Colors.RESET}\n")
                        else:
                            print(f"{Colors.GREEN}✅ Cleared {old_count - 1} messages, starting new session{Colors.RESET}\n")
                        continue

                    elif command == "/history":
                        if config.ui.style == "claude":
                            print(f"\n{Colors.DIM}Current session message count: {len(agent.messages)}{Colors.RESET}\n")
                        else:
                            print(f"\n{Colors.BRIGHT_CYAN}Current session message count: {len(agent.messages)}{Colors.RESET}\n")
                        continue

                    elif command == "/stats":
                        print_stats(agent, session_start)
                        continue

                    elif command == "/log" or command.startswith("/log "):
                        parts = user_input.split(maxsplit=1)
                        if len(parts) == 1:
                            show_log_directory(open_file_manager=True, style=config.ui.style)
                        else:
                            filename = parts[1].strip("\"'")
                            read_log_file(filename, style=config.ui.style)
                        continue

                    elif command == "/config" or command.startswith("/config "):
                        parts = user_input.split(maxsplit=1)
                        if len(parts) == 1:
                            # Show current config path
                            if config.ui.style == "claude":
                                print(f"{Colors.DIM}Current config: {display_path(config_path)}{Colors.RESET}\n")
                            else:
                                print(f"{Colors.BRIGHT_CYAN}📄 Current config: {config_path}{Colors.RESET}\n")
                        else:
                            # Switch to new config
                            new_config_path = Path(parts[1].strip("\"'")).expanduser().absolute()
                            if not new_config_path.exists():
                                if config.ui.style == "claude":
                                    print(f"{Colors.DIM}Config file not found: {display_path(new_config_path)}{Colors.RESET}\n")
                                else:
                                    print(f"{Colors.RED}❌ Config file not found: {new_config_path}{Colors.RESET}\n")
                                continue

                            try:
                                # Load new config
                                new_config = Config.from_yaml(new_config_path)

                                # Update config reference
                                config = new_config
                                channel_context.config = new_config

                                # Clear runtime cache to force re-initialization
                                runtime_bundle_cache.clear()

                                # Re-create current session with new config
                                old_count = len(agent.messages)
                                session_store.pop("terminal", "main", agent_id=terminal_session.agent_id)
                                terminal_session = await create_managed_session(
                                    agent_id=terminal_session.agent_id,
                                    channel="terminal",
                                    session_id="main",
                                )
                                agent = terminal_session.agent

                                config_path = new_config_path
                                if config.ui.style == "claude":
                                    print(f"{Colors.DIM}Switched to config: {display_path(config_path)}{Colors.RESET}")
                                    print(f"{Colors.DIM}Cleared {old_count - 1} messages, started a new session with new config.{Colors.RESET}\n")
                                else:
                                    print(f"{Colors.GREEN}✅ Switched to config: {config_path}{Colors.RESET}")
                                    print(f"{Colors.GREEN}✅ Cleared {old_count - 1} messages, started a new session{Colors.RESET}\n")

                            except Exception as e:
                                if config.ui.style == "claude":
                                    print(f"{Colors.DIM}Failed to load config: {e}{Colors.RESET}\n")
                                else:
                                    print(f"{Colors.RED}❌ Failed to load config: {e}{Colors.RESET}\n")
                        continue

                    else:
                        if config.ui.style == "claude":
                            print(f"{Colors.DIM}Unknown command: {user_input}{Colors.RESET}")
                            print(f"{Colors.DIM}Type /help to see available commands.{Colors.RESET}\n")
                        else:
                            print(f"{Colors.RED}❌ Unknown command: {user_input}{Colors.RESET}")
                            print(f"{Colors.DIM}Type /help to see available commands{Colors.RESET}\n")
                        continue

                if user_input.lower() in ["exit", "quit", "q"]:
                    print(f"\n{Colors.BRIGHT_YELLOW}👋 Goodbye! Thanks for using Grape Agent{Colors.RESET}\n")
                    print_stats(agent, session_start)
                    break

                if config.ui.style != "claude":
                    print(
                        f"\n{Colors.BRIGHT_BLUE}Agent{Colors.RESET} {Colors.DIM}›{Colors.RESET} {Colors.DIM}Thinking... (Esc to cancel){Colors.RESET}\n"
                    )
                agent.add_user_message(user_input)

                cancel_event = asyncio.Event()
                agent.cancel_event = cancel_event

                esc_listener_stop = threading.Event()
                esc_cancelled = [False]

                def esc_key_listener():
                    if platform.system() == "Windows":
                        try:
                            import msvcrt

                            while not esc_listener_stop.is_set():
                                if msvcrt.kbhit():
                                    char = msvcrt.getch()
                                    if char == b"\x1b":
                                        print(f"\n{Colors.BRIGHT_YELLOW}⏹️  Esc pressed, cancelling...{Colors.RESET}")
                                        esc_cancelled[0] = True
                                        cancel_event.set()
                                        break
                                esc_listener_stop.wait(0.05)
                        except Exception:
                            pass
                        return

                    try:
                        import select
                        import termios
                        import tty

                        fd = sys.stdin.fileno()
                        old_settings = termios.tcgetattr(fd)

                        try:
                            tty.setcbreak(fd)
                            while not esc_listener_stop.is_set():
                                rlist, _, _ = select.select([sys.stdin], [], [], 0.05)
                                if rlist:
                                    char = sys.stdin.read(1)
                                    if char == "\x1b":
                                        print(f"\n{Colors.BRIGHT_YELLOW}⏹️  Esc pressed, cancelling...{Colors.RESET}")
                                        esc_cancelled[0] = True
                                        cancel_event.set()
                                        break
                        finally:
                            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
                    except Exception:
                        pass

                esc_thread = threading.Thread(target=esc_key_listener, daemon=True)
                esc_thread.start()

                try:
                    agent_task = asyncio.create_task(agent.run())
                    while not agent_task.done():
                        if esc_cancelled[0]:
                            cancel_event.set()
                        await asyncio.sleep(0.1)
                    _ = agent_task.result()

                except asyncio.CancelledError:
                    print(f"\n{Colors.BRIGHT_YELLOW}⚠️  Agent execution cancelled{Colors.RESET}")
                finally:
                    agent.cancel_event = None
                    esc_listener_stop.set()
                    esc_thread.join(timeout=0.2)

                if config.ui.style != "claude":
                    print(f"\n{Colors.DIM}{'─' * 60}{Colors.RESET}\n")
                else:
                    print()

            except KeyboardInterrupt:
                print(f"\n\n{Colors.BRIGHT_YELLOW}👋 Interrupt signal detected, exiting...{Colors.RESET}\n")
                print_stats(agent, session_start)
                break

            except Exception as e:
                print(f"\n{Colors.RED}❌ Error: {e}{Colors.RESET}")
                print(f"{Colors.DIM}{'─' * 60}{Colors.RESET}\n")

    finally:
        try:
            if cron_scheduler is not None:
                await cron_scheduler.stop()
            if gateway_server is not None:
                await gateway_server.stop()
            await channel_runtime.stop()
            await _quiet_cleanup()
        except KeyboardInterrupt:
            # Exit cleanly without noisy traceback during shutdown.
            pass
        finally:
            set_channel_log_quiet(False)


def main():
    """Main entry point for CLI"""
    # Parse command line arguments
    args = parse_args()

    # Handle log subcommand
    if args.command == "log":
        if args.filename:
            read_log_file(args.filename)
        else:
            show_log_directory(open_file_manager=True)
        return

    # Determine workspace directory
    # Expand ~ to user home directory for portability
    if args.workspace:
        workspace_dir = Path(args.workspace).expanduser().absolute()
    else:
        # Use current working directory
        workspace_dir = Path.cwd()

    # Ensure workspace directory exists
    workspace_dir.mkdir(parents=True, exist_ok=True)

    # Run the agent (config always loaded from package directory)
    asyncio.run(
        run_agent(
            workspace_dir,
            task=args.task,
            ui_style_override=args.ui_style,
            user_id_override=args.user_id,
        )
    )


if __name__ == "__main__":
    main()
