"""
Mini Agent - Interactive Runtime Example

Usage:
    mini-agent [--workspace DIR] [--task TASK]

Examples:
    mini-agent                              # Use current directory as workspace (interactive mode)
    mini-agent --workspace /path/to/dir     # Use specific workspace directory (interactive mode)
    mini-agent --task "create a file"       # Execute a task non-interactively
"""

import argparse
import asyncio
import platform
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import List

from prompt_toolkit import PromptSession
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.styles import Style

from mini_agent.agent import Agent
from mini_agent.config import Config
from mini_agent.runtime_factory import (
    add_workspace_tools as add_workspace_tools_shared,
    build_runtime_bundle,
    initialize_base_tools as initialize_base_tools_shared,
)
from mini_agent.session_store import AgentSessionStore
from mini_agent.tools.base import Tool
from mini_agent.tools.mcp_loader import cleanup_mcp_connections
from mini_agent.utils import calculate_display_width


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


def get_log_directory() -> Path:
    """Get the log directory path."""
    return Path.home() / ".mini-agent" / "log"


def show_log_directory(open_file_manager: bool = True) -> None:
    """Show log directory contents and optionally open file manager.

    Args:
        open_file_manager: Whether to open the system file manager
    """
    log_dir = get_log_directory()

    print(f"\n{Colors.BRIGHT_CYAN}📁 Log Directory: {log_dir}{Colors.RESET}")

    if not log_dir.exists() or not log_dir.is_dir():
        print(f"{Colors.RED}Log directory does not exist: {log_dir}{Colors.RESET}\n")
        return

    log_files = list(log_dir.glob("*.log"))

    if not log_files:
        print(f"{Colors.YELLOW}No log files found in directory.{Colors.RESET}\n")
        return

    # Sort by modification time (newest first)
    log_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)

    print(f"{Colors.DIM}{'─' * 60}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BRIGHT_YELLOW}Available Log Files (newest first):{Colors.RESET}")

    for i, log_file in enumerate(log_files[:10], 1):
        mtime = datetime.fromtimestamp(log_file.stat().st_mtime)
        size = log_file.stat().st_size
        size_str = f"{size:,}" if size < 1024 else f"{size / 1024:.1f}K"
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


def read_log_file(filename: str) -> None:
    """Read and display a specific log file.

    Args:
        filename: The log filename to read
    """
    log_dir = get_log_directory()
    log_file = log_dir / filename

    if not log_file.exists() or not log_file.is_file():
        print(f"\n{Colors.RED}❌ Log file not found: {log_file}{Colors.RESET}\n")
        return

    print(f"\n{Colors.BRIGHT_CYAN}📄 Reading: {log_file}{Colors.RESET}")
    print(f"{Colors.DIM}{'─' * 80}{Colors.RESET}")

    try:
        with open(log_file, "r", encoding="utf-8") as f:
            content = f.read()
        print(content)
        print(f"{Colors.DIM}{'─' * 80}{Colors.RESET}")
        print(f"\n{Colors.GREEN}✅ End of file{Colors.RESET}\n")
    except Exception as e:
        print(f"\n{Colors.RED}❌ Error reading file: {e}{Colors.RESET}\n")


def print_banner():
    """Print welcome banner with proper alignment"""
    BOX_WIDTH = 58
    banner_text = f"{Colors.BOLD}🤖 Mini Agent - Multi-turn Interactive Session{Colors.RESET}"
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


def print_help():
    """Print help information"""
    help_text = f"""
{Colors.BOLD}{Colors.BRIGHT_YELLOW}Available Commands:{Colors.RESET}
  {Colors.BRIGHT_GREEN}/help{Colors.RESET}      - Show this help message
  {Colors.BRIGHT_GREEN}/clear{Colors.RESET}     - Clear session history (keep system prompt)
  {Colors.BRIGHT_GREEN}/history{Colors.RESET}   - Show current session message count
  {Colors.BRIGHT_GREEN}/stats{Colors.RESET}     - Show session statistics
  {Colors.BRIGHT_GREEN}/log{Colors.RESET}       - Show log directory and recent files
  {Colors.BRIGHT_GREEN}/log <file>{Colors.RESET} - Read a specific log file
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


def print_session_info(agent: Agent, workspace_dir: Path, model: str):
    """Print session information with proper alignment"""
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


def print_stats(agent: Agent, session_start: datetime):
    """Print session statistics"""
    duration = datetime.now() - session_start
    hours, remainder = divmod(int(duration.total_seconds()), 3600)
    minutes, seconds = divmod(remainder, 60)

    # Count different types of messages
    user_msgs = sum(1 for m in agent.messages if m.role == "user")
    assistant_msgs = sum(1 for m in agent.messages if m.role == "assistant")
    tool_msgs = sum(1 for m in agent.messages if m.role == "tool")

    print(f"\n{Colors.BOLD}{Colors.BRIGHT_CYAN}Session Statistics:{Colors.RESET}")
    print(f"{Colors.DIM}{'─' * 40}{Colors.RESET}")
    print(f"  Session Duration: {hours:02d}:{minutes:02d}:{seconds:02d}")
    print(f"  Total Messages: {len(agent.messages)}")
    print(f"    - User Messages: {Colors.BRIGHT_GREEN}{user_msgs}{Colors.RESET}")
    print(f"    - Assistant Replies: {Colors.BRIGHT_BLUE}{assistant_msgs}{Colors.RESET}")
    print(f"    - Tool Calls: {Colors.BRIGHT_YELLOW}{tool_msgs}{Colors.RESET}")
    print(f"  Available Tools: {len(agent.tools)}")
    if agent.api_total_tokens > 0:
        print(f"  API Tokens Used: {Colors.BRIGHT_MAGENTA}{agent.api_total_tokens:,}{Colors.RESET}")
    print(f"{Colors.DIM}{'─' * 40}{Colors.RESET}\n")


def parse_args() -> argparse.Namespace:
    """Parse command line arguments

    Returns:
        Parsed arguments
    """
    parser = argparse.ArgumentParser(
        description="Mini Agent - AI assistant with file tools and MCP support",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  mini-agent                              # Use current directory as workspace
  mini-agent --workspace /path/to/dir     # Use specific workspace directory
  mini-agent log                          # Show log directory and recent files
  mini-agent log agent_run_xxx.log        # Read a specific log file
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
        version="mini-agent 0.1.0",
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


async def run_agent(workspace_dir: Path, task: str = None):
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
        print(f"  {Colors.DIM}1) mini_agent/config/config.yaml{Colors.RESET} (development)")
        print(f"  {Colors.DIM}2) ~/.mini-agent/config/config.yaml{Colors.RESET} (user)")
        print(f"  {Colors.DIM}3) <package>/config/config.yaml{Colors.RESET} (installed)")
        print()
        print(f"{Colors.BRIGHT_YELLOW}🚀 Quick Setup (Recommended):{Colors.RESET}")
        print(
            f"  {Colors.BRIGHT_GREEN}curl -fsSL https://raw.githubusercontent.com/MiniMax-AI/Mini-Agent/main/scripts/setup-config.sh | bash{Colors.RESET}"
        )
        print()
        print(f"{Colors.DIM}  This will automatically:{Colors.RESET}")
        print(f"{Colors.DIM}    • Create ~/.mini-agent/config/{Colors.RESET}")
        print(f"{Colors.DIM}    • Download configuration files{Colors.RESET}")
        print(f"{Colors.DIM}    • Guide you to add your API Key{Colors.RESET}")
        print()
        print(f"{Colors.BRIGHT_YELLOW}📝 Manual Setup:{Colors.RESET}")
        user_config_dir = Path.home() / ".mini-agent" / "config"
        example_config = Config.get_package_dir() / "config" / "config-example.yaml"
        print(f"  {Colors.DIM}mkdir -p {user_config_dir}{Colors.RESET}")
        print(f"  {Colors.DIM}cp {example_config} {user_config_dir}/config.yaml{Colors.RESET}")
        print(f"  {Colors.DIM}# Then edit {user_config_dir}/config.yaml to add your API Key{Colors.RESET}")
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

    from mini_agent.feishu.embedded_runner import EmbeddedFeishuRunner

    feishu_runner = EmbeddedFeishuRunner(config=config, config_path=config_path)
    feishu_runner.start()

    try:
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

        runtime_bundle = await build_runtime_bundle(config=config, log=runtime_log, on_retry=on_retry)

        if config.llm.retry.enabled:
            print(f"{Colors.GREEN}✅ LLM retry mechanism enabled (max {config.llm.retry.max_retries} retries){Colors.RESET}")
        print()

        session_store = AgentSessionStore()

        def create_terminal_agent() -> Agent:
            terminal_tools = list(runtime_bundle.base_tools)
            add_workspace_tools(terminal_tools, config, workspace_dir)
            return Agent(
                llm_client=runtime_bundle.llm_client,
                system_prompt=runtime_bundle.system_prompt,
                tools=terminal_tools,
                max_steps=config.agent.max_steps,
                workspace_dir=str(workspace_dir),
            )

        terminal_session = await session_store.get_or_create("terminal", "main", create_terminal_agent)
        agent = terminal_session.agent

        # 8. Display welcome information
        if not task:
            print_banner()
            print_session_info(agent, workspace_dir, config.llm.model)

        # 8.5 Non-interactive mode
        if task:
            print(f"\n{Colors.BRIGHT_BLUE}Agent{Colors.RESET} {Colors.DIM}›{Colors.RESET} {Colors.DIM}Executing task...{Colors.RESET}\n")
            agent.add_user_message(task)
            try:
                await agent.run()
            except Exception as e:
                print(f"\n{Colors.RED}❌ Error: {e}{Colors.RESET}")
            finally:
                print_stats(agent, session_start)
            return

        # 9. Setup prompt_toolkit session
        command_completer = WordCompleter(
            ["/help", "/clear", "/history", "/stats", "/log", "/exit", "/quit", "/q"],
            ignore_case=True,
            sentence=True,
        )

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

        history_file = Path.home() / ".mini-agent" / ".history"
        history_file.parent.mkdir(parents=True, exist_ok=True)
        session = PromptSession(
            history=FileHistory(str(history_file)),
            auto_suggest=AutoSuggestFromHistory(),
            completer=command_completer,
            style=prompt_style,
            key_bindings=kb,
        )

        # 10. Interactive loop
        while True:
            try:
                user_input = await session.prompt_async(
                    [
                        ("class:prompt", "You"),
                        ("", " › "),
                    ],
                    multiline=False,
                    enable_history_search=True,
                )
                user_input = user_input.strip()

                if not user_input:
                    continue

                if user_input.startswith("/"):
                    command = user_input.lower()

                    if command in ["/exit", "/quit", "/q"]:
                        print(f"\n{Colors.BRIGHT_YELLOW}👋 Goodbye! Thanks for using Mini Agent{Colors.RESET}\n")
                        print_stats(agent, session_start)
                        break

                    elif command == "/help":
                        print_help()
                        continue

                    elif command == "/clear":
                        old_count = len(agent.messages)
                        session_store.pop("terminal", "main")
                        terminal_session = await session_store.get_or_create("terminal", "main", create_terminal_agent)
                        agent = terminal_session.agent
                        print(f"{Colors.GREEN}✅ Cleared {old_count - 1} messages, starting new session{Colors.RESET}\n")
                        continue

                    elif command == "/history":
                        print(f"\n{Colors.BRIGHT_CYAN}Current session message count: {len(agent.messages)}{Colors.RESET}\n")
                        continue

                    elif command == "/stats":
                        print_stats(agent, session_start)
                        continue

                    elif command == "/log" or command.startswith("/log "):
                        parts = user_input.split(maxsplit=1)
                        if len(parts) == 1:
                            show_log_directory(open_file_manager=True)
                        else:
                            filename = parts[1].strip("\"'")
                            read_log_file(filename)
                        continue

                    else:
                        print(f"{Colors.RED}❌ Unknown command: {user_input}{Colors.RESET}")
                        print(f"{Colors.DIM}Type /help to see available commands{Colors.RESET}\n")
                        continue

                if user_input.lower() in ["exit", "quit", "q"]:
                    print(f"\n{Colors.BRIGHT_YELLOW}👋 Goodbye! Thanks for using Mini Agent{Colors.RESET}\n")
                    print_stats(agent, session_start)
                    break

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

                print(f"\n{Colors.DIM}{'─' * 60}{Colors.RESET}\n")

            except KeyboardInterrupt:
                print(f"\n\n{Colors.BRIGHT_YELLOW}👋 Interrupt signal detected, exiting...{Colors.RESET}\n")
                print_stats(agent, session_start)
                break

            except Exception as e:
                print(f"\n{Colors.RED}❌ Error: {e}{Colors.RESET}")
                print(f"{Colors.DIM}{'─' * 60}{Colors.RESET}\n")

    finally:
        await _quiet_cleanup()
        feishu_runner.stop()


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
    asyncio.run(run_agent(workspace_dir, task=args.task))


if __name__ == "__main__":
    main()
