"""CLI rendering abstraction with multiple styles."""

from __future__ import annotations

import json
import re
import sys
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Iterable

from mini_agent.schema import ProviderEvent, TokenUsage
from mini_agent.tools.base import ToolResult
from mini_agent.utils import calculate_display_width


class Colors:
    """ANSI color definitions for terminal rendering."""

    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"

    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"

    BRIGHT_BLUE = "\033[94m"
    BRIGHT_CYAN = "\033[96m"
    BRIGHT_WHITE = "\033[97m"


@dataclass
class RendererOptions:
    """UI renderer options."""

    style: str = "claude"  # legacy|compact|claude
    show_thinking: bool = True
    show_tool_args: bool = False
    show_timing: bool = False
    show_steps: bool = False
    render_markdown: bool = True
    arg_value_max_chars: int = 120
    result_preview_chars: int = 220


class ConsoleRenderer:
    """Render Agent execution events in terminal."""

    def __init__(self, options: RendererOptions | None = None):
        self.options = options or RendererOptions()
        self._activity_callback: Callable[[], None] | None = None
        self._thinking_thread: threading.Thread | None = None
        self._thinking_stop = threading.Event()
        self._thinking_start_ts: float | None = None
        self._thinking_last_width = 0
        self._thinking_line_active = False

    def set_activity_callback(self, callback: Callable[[], None] | None) -> None:
        """Set callback fired when renderer emits visible activity."""
        self._activity_callback = callback

    def _notify_activity(self) -> None:
        if self._activity_callback is not None:
            try:
                self._activity_callback()
            except Exception:
                pass

    @classmethod
    def from_runtime(cls, ui_config: Any = None, style_override: str | None = None) -> "ConsoleRenderer":
        style = style_override or getattr(ui_config, "style", "claude")
        show_thinking = getattr(ui_config, "show_thinking", True)
        show_tool_args = getattr(ui_config, "show_tool_args", False)
        show_timing = getattr(ui_config, "show_timing", False)
        show_steps = getattr(ui_config, "show_steps", style == "legacy")
        render_markdown = getattr(ui_config, "render_markdown", True)
        return cls(
            RendererOptions(
                style=style,
                show_thinking=show_thinking,
                show_tool_args=show_tool_args,
                show_timing=show_timing,
                show_steps=show_steps,
                render_markdown=render_markdown,
            )
        )

    def step_start(self, step: int, max_steps: int) -> None:
        if not self.options.show_steps:
            return
        if self.options.style == "legacy":
            box_width = 58
            step_text = f"{Colors.BOLD}{Colors.BRIGHT_CYAN}💭 Step {step}/{max_steps}{Colors.RESET}"
            step_display_width = calculate_display_width(step_text)
            padding = max(0, box_width - 1 - step_display_width)
            print(f"\n{Colors.DIM}╭{'─' * box_width}╮{Colors.RESET}")
            print(f"{Colors.DIM}│{Colors.RESET} {step_text}{' ' * padding}{Colors.DIM}│{Colors.RESET}")
            print(f"{Colors.DIM}╰{'─' * box_width}╯{Colors.RESET}")
        else:
            print(f"{Colors.DIM}step {step}/{max_steps}{Colors.RESET}")

    def step_done(self, step: int, step_elapsed: float, total_elapsed: float) -> None:
        if not self.options.show_timing:
            return
        print(f"\n{Colors.DIM}⏱️  Step {step} completed in {step_elapsed:.2f}s (total: {total_elapsed:.2f}s){Colors.RESET}")

    def start_thinking_status(self) -> None:
        """Start dynamic thinking status line (Claude style only)."""
        if self.options.style != "claude":
            return
        self.stop_thinking_status(None)

        self._thinking_stop.clear()
        self._thinking_start_ts = time.perf_counter()
        self._thinking_last_width = 0
        self._thinking_line_active = True

        def _worker() -> None:
            frames = [
                f"{Colors.DIM}✳{Colors.RESET}",
                f"{Colors.RESET}✳{Colors.RESET}",
                f"{Colors.BOLD}✳{Colors.RESET}",
                f"{Colors.RESET}✳{Colors.RESET}",
            ]
            index = 0
            while not self._thinking_stop.is_set():
                elapsed = 0.0
                if self._thinking_start_ts is not None:
                    elapsed = max(0.0, time.perf_counter() - self._thinking_start_ts)
                line = f"{frames[index]} {Colors.DIM}thinking... ({self._format_elapsed(elapsed)}){Colors.RESET}"
                self._rewrite_status_line(line)
                index = (index + 1) % len(frames)
                interval = 1.0
                if self._thinking_stop.wait(timeout=interval):
                    break

        self._thinking_thread = threading.Thread(target=_worker, name="thinking-indicator", daemon=True)
        self._thinking_thread.start()

    def stop_thinking_status(self, usage: TokenUsage | None) -> None:
        """Stop dynamic thinking line and print final static summary."""
        if self.options.style != "claude":
            return
        if not self._thinking_line_active:
            return

        self._thinking_stop.set()
        if self._thinking_thread is not None:
            self._thinking_thread.join(timeout=0.3)
        self._thinking_thread = None

        elapsed = 0.0
        if self._thinking_start_ts is not None:
            elapsed = max(0.0, time.perf_counter() - self._thinking_start_ts)
        total_tokens = usage.total_tokens if usage is not None else 0
        has_real_tokens = total_tokens > 0
        if has_real_tokens:
            final_line = (
                f"{Colors.DIM}✳ thinking... "
                f"({self._format_elapsed(elapsed)} · {self._format_tokens(total_tokens)} tokens){Colors.RESET}"
            )
        else:
            final_line = f"{Colors.DIM}✳ thinking... ({self._format_elapsed(elapsed)}){Colors.RESET}"
        self._clear_status_line()
        print(final_line)
        self._thinking_start_ts = None
        self._thinking_last_width = 0
        self._thinking_line_active = False

    def thinking(self, text: str | None) -> None:
        if not text or not self.options.show_thinking:
            return
        if self.options.style == "claude":
            return
        self._notify_activity()
        shown = text if len(text) <= 1200 else text[:1200] + "..."
        print(f"\n{Colors.BOLD}{Colors.MAGENTA}🧠 Thinking:{Colors.RESET}")
        print(f"{Colors.DIM}{shown}{Colors.RESET}")

    def provider_events(self, events: Iterable[ProviderEvent] | None) -> None:
        if not events:
            return
        for event in events:
            self.provider_event(event)

    def provider_event(self, event: ProviderEvent) -> None:
        self._notify_activity()
        if event.event_type == "server_tool_use":
            name = self._friendly_name(event.name)
            query = self._extract_query(event.payload)
            if query:
                text = f'{name}("{query}")'
                print(f"\n{self._event_bullet()} {self._event_text(text)}")
            else:
                print(f"\n{self._event_bullet()} {self._event_text(name)}")
            return
        if event.event_type == "tool_result":
            if self.options.style == "claude":
                print(f"{Colors.DIM}{Colors.GREEN}●{Colors.RESET} {self._event_text('Provider tool completed')}")
            else:
                print(f"{Colors.GREEN}✓ Provider tool completed{Colors.RESET}")
            return

        label = self._friendly_name(event.name or event.event_type)
        print(f"\n{self._event_bullet()} {self._event_text(label)}")

    def tool_call(self, function_name: str, arguments: dict[str, Any]) -> None:
        self._notify_activity()
        if self.options.style == "claude":
            label = self._compact_tool_call_label(function_name, arguments)
            print(f"\n{self._event_bullet()} {self._event_text(label)}")
            print(f"{Colors.DIM}  └ Running...{Colors.RESET}")
            return

        summary = self._summarize_args(arguments)
        if summary:
            print(f"\n{self._event_bullet()} {self._event_text(f'{function_name}({summary})')}")
        else:
            print(f"\n{self._event_bullet()} {self._event_text(f'{function_name}()')}")

        if self.options.show_tool_args:
            display_args = self._truncate_arg_values(arguments)
            args_json = json.dumps(display_args, indent=2, ensure_ascii=False)
            print(f"{Colors.DIM}{args_json}{Colors.RESET}")

    def tool_result(self, function_name: str, result: ToolResult) -> None:
        self._notify_activity()
        if self.options.style == "claude":
            if result.success:
                print(f"{Colors.DIM}  └ {self._compact_tool_result_summary(function_name, result)}{Colors.RESET}")
            else:
                error = (result.error or "Tool failed").strip().splitlines()[0]
                if len(error) > 180:
                    error = error[:180] + "..."
                print(f"{Colors.DIM}  └ {Colors.RED}Failed: {error}{Colors.RESET}")
            return

        if result.success:
            preview = result.content or ""
            preview = preview.replace("\n", " ").strip()
            if len(preview) > self.options.result_preview_chars:
                preview = preview[: self.options.result_preview_chars] + "..."
            suffix = f": {preview}" if preview else ""
            if self.options.style == "claude":
                print(f"{Colors.DIM}{Colors.GREEN}●{Colors.RESET} {self._event_text(function_name)}{suffix}")
            else:
                print(f"{Colors.GREEN}✓ {function_name}{Colors.RESET}{suffix}")
            return
        print(f"{Colors.RED}✗ {function_name}: {result.error}{Colors.RESET}")

    def assistant_content(self, content: str | None) -> None:
        if not content:
            return
        self._notify_activity()
        print()
        rendered = self._render_markdown_text(content) if self.options.render_markdown else content
        print(rendered)

    def _friendly_name(self, name: str | None) -> str:
        key = (name or "provider_tool").lower()
        mapping = {
            "web_search": "Web Search",
            "web_search_prime": "Web Search",
            "web_search_20250305": "Web Search",
        }
        return mapping.get(key, name or "Provider Tool")

    def _rewrite_status_line(self, line: str) -> None:
        plain_width = calculate_display_width(self._strip_ansi(line))
        pad = max(0, self._thinking_last_width - plain_width)
        sys.stdout.write("\r" + line + (" " * pad))
        sys.stdout.flush()
        self._thinking_last_width = plain_width

    def _clear_status_line(self) -> None:
        if self._thinking_last_width <= 0:
            return
        sys.stdout.write("\r" + (" " * self._thinking_last_width) + "\r")
        sys.stdout.flush()

    def _format_tokens(self, tokens: int) -> str:
        if tokens >= 1_000_000:
            return f"{tokens / 1_000_000:.1f}m"
        if tokens >= 1_000:
            return f"{tokens / 1_000:.1f}k"
        return str(tokens)

    def _format_elapsed(self, elapsed: float) -> str:
        if elapsed < 60:
            return f"{elapsed:.1f}s"
        total = int(elapsed)
        minutes, seconds = divmod(total, 60)
        if minutes < 60:
            return f"{minutes}m {seconds}s"
        hours, minutes = divmod(minutes, 60)
        return f"{hours}h {minutes}m"

    def _compact_tool_call_label(self, function_name: str, arguments: dict[str, Any]) -> str:
        fn = function_name.strip()
        lower = fn.lower()

        if lower == "bash":
            command = str(arguments.get("command", "")).replace("\n", " ").strip()
            if len(command) > 72:
                command = command[:72] + "..."
            return f"Bash({command})" if command else "Bash"

        if lower in {"read", "read_file"}:
            path = arguments.get("file_path") or arguments.get("path") or arguments.get("filename") or ""
            text = str(path).strip()
            if len(text) > 72:
                text = text[:72] + "..."
            return f"Read({text})" if text else "Read"

        if lower in {"write", "write_file"}:
            path = arguments.get("file_path") or arguments.get("path") or arguments.get("filename") or ""
            text = str(path).strip()
            if len(text) > 72:
                text = text[:72] + "..."
            return f"Write({text})" if text else "Write"

        if lower in {"edit", "edit_file"}:
            path = arguments.get("file_path") or arguments.get("path") or ""
            text = str(path).strip()
            if len(text) > 72:
                text = text[:72] + "..."
            return f"Edit({text})" if text else "Edit"

        if lower == "record_note":
            category = str(arguments.get("category", "")).strip()
            return f"RecordNote({category})" if category else "RecordNote"

        summary = self._summarize_args(arguments)
        title = fn.replace("_", " ").title()
        return f"{title}({summary})" if summary else title

    def _compact_tool_result_summary(self, function_name: str, result: ToolResult) -> str:
        lower = function_name.strip().lower()
        if lower in {"read", "read_file"}:
            chars = len(result.content or "")
            return f"Read complete ({chars} chars)"
        if lower in {"write", "write_file", "edit", "edit_file"}:
            return "Update complete"
        if lower == "record_note":
            return "Note saved"
        if lower == "bash":
            content = (result.content or "").strip()
            if not content:
                return "Done"
            first = content.splitlines()[0].strip()
            if len(first) > 90:
                first = first[:90] + "..."
            return f"Done: {first}"
        return "Done"

    def _event_bullet(self) -> str:
        if self.options.style == "claude":
            return f"{Colors.DIM}{Colors.BRIGHT_CYAN}⏺{Colors.RESET}"
        return f"{Colors.BRIGHT_CYAN}⏺{Colors.RESET}"

    def _event_text(self, text: str) -> str:
        if self.options.style == "claude":
            return f"{Colors.DIM}{text}{Colors.RESET}"
        return f"{Colors.BRIGHT_CYAN}{text}{Colors.RESET}"

    def _extract_query(self, payload: Any) -> str | None:
        if not isinstance(payload, dict):
            return None
        inner = payload.get("input")
        if isinstance(inner, dict):
            for key in ("search_query", "query", "q"):
                value = inner.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
        for key in ("search_query", "query", "q"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    def _summarize_args(self, arguments: dict[str, Any]) -> str:
        if not arguments:
            return ""
        chunks: list[str] = []
        for key, value in arguments.items():
            value_str = str(value).replace("\n", " ").strip()
            if len(value_str) > self.options.arg_value_max_chars:
                value_str = value_str[: self.options.arg_value_max_chars] + "..."
            chunks.append(f"{key}={value_str}")
        summary = ", ".join(chunks)
        if len(summary) > 240:
            summary = summary[:240] + "..."
        return summary

    def _truncate_arg_values(self, arguments: dict[str, Any]) -> dict[str, Any]:
        truncated: dict[str, Any] = {}
        for key, value in arguments.items():
            value_str = str(value)
            if len(value_str) > 200:
                truncated[key] = value_str[:200] + "..."
            else:
                truncated[key] = value
        return truncated

    def _render_markdown_text(self, text: str) -> str:
        """Render a subset of markdown for terminal readability."""
        lines = text.splitlines()
        out: list[str] = []
        i = 0
        in_code_block = False
        code_fence = ""

        while i < len(lines):
            line = lines[i]
            stripped = line.strip()

            if stripped.startswith("```"):
                in_code_block = not in_code_block
                code_fence = stripped[3:].strip() if in_code_block else ""
                if in_code_block:
                    label = f" [{code_fence}]" if code_fence else ""
                    out.append(f"{Colors.DIM}--- code{label} ---{Colors.RESET}")
                else:
                    out.append(f"{Colors.DIM}--- end code ---{Colors.RESET}")
                i += 1
                continue

            if in_code_block:
                out.append(f"{Colors.BRIGHT_WHITE}{line}{Colors.RESET}")
                i += 1
                continue

            if self._looks_like_table_header(lines, i):
                block, next_index = self._consume_table(lines, i)
                out.extend(self._render_table_block(block))
                i = next_index
                continue

            rendered = self._render_inline_markdown(line)
            out.append(rendered)
            i += 1

        return "\n".join(out)

    def _render_inline_markdown(self, line: str) -> str:
        if not line:
            return line

        bold_heading = re.fullmatch(r"\*\*([^*]+)\*\*", line.strip())
        if bold_heading:
            return f"{Colors.BOLD}{bold_heading.group(1)}{Colors.RESET}"

        heading = re.match(r"^(#{1,6})\s+(.*)$", line)
        if heading:
            return f"{Colors.BOLD}{heading.group(2)}{Colors.RESET}"

        # [text](url) -> text (url)
        line = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1 (\2)", line)
        # `code`
        line = re.sub(r"`([^`]+)`", rf"{Colors.CYAN}\1{Colors.RESET}", line)
        # **bold**
        line = re.sub(r"\*\*([^*]+)\*\*", rf"{Colors.BOLD}\1{Colors.RESET}", line)
        # *italic* (render as dim to keep readable)
        line = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", rf"{Colors.DIM}\1{Colors.RESET}", line)
        return line

    def _looks_like_table_header(self, lines: list[str], index: int) -> bool:
        if index + 1 >= len(lines):
            return False
        header = lines[index].strip()
        sep = lines[index + 1].strip()
        if "|" not in header or "|" not in sep:
            return False
        # markdown separator row like |---|:---:|
        return bool(re.fullmatch(r"\|?[\s:\-|\t]+\|?", sep))

    def _consume_table(self, lines: list[str], index: int) -> tuple[list[str], int]:
        block = [lines[index], lines[index + 1]]
        i = index + 2
        while i < len(lines):
            candidate = lines[i]
            if "|" not in candidate:
                break
            if not candidate.strip():
                break
            block.append(candidate)
            i += 1
        return block, i

    def _render_table_block(self, block: list[str]) -> list[str]:
        rows: list[list[str]] = []
        for raw in block:
            stripped = raw.strip()
            if not stripped:
                continue
            # skip markdown separator row
            if re.fullmatch(r"\|?[\s:\-|\t]+\|?", stripped):
                continue
            cells = [self._render_inline_markdown(cell.strip()) for cell in stripped.strip("|").split("|")]
            rows.append(cells)

        if not rows:
            return []

        col_count = max(len(r) for r in rows)
        for r in rows:
            if len(r) < col_count:
                r.extend([""] * (col_count - len(r)))

        widths = [0] * col_count
        for c in range(col_count):
            widths[c] = max(calculate_display_width(self._strip_ansi(r[c])) for r in rows)

        def border(ch: str = "-") -> str:
            return "+" + "+".join((ch * (w + 2) for w in widths)) + "+"

        rendered: list[str] = [border("-")]
        for idx, row in enumerate(rows):
            padded_cells = []
            for c, val in enumerate(row):
                display = calculate_display_width(self._strip_ansi(val))
                pad = widths[c] - display
                padded_cells.append(f" {val}{' ' * pad} ")
            rendered.append("|" + "|".join(padded_cells) + "|")
            rendered.append(border("-" if idx == 0 else "-"))
        return rendered

    def _strip_ansi(self, text: str) -> str:
        return re.sub(r"\x1b\[[0-9;]*m", "", text)
