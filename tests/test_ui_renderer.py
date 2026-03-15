"""Tests for console renderer behavior."""

from mini_agent.schema import ProviderEvent
from mini_agent.ui.renderer import ConsoleRenderer, RendererOptions


def test_renderer_claude_hides_step_headers_and_timing(capsys):
    renderer = ConsoleRenderer(RendererOptions(style="claude", show_steps=False, show_timing=False))
    renderer.step_start(1, 100)
    renderer.step_done(1, 0.12, 0.12)
    captured = capsys.readouterr()
    assert captured.out == ""


def test_renderer_provider_event_web_search(capsys):
    renderer = ConsoleRenderer(RendererOptions(style="claude"))
    renderer.provider_event(
        ProviderEvent(
            source="anthropic",
            event_type="server_tool_use",
            name="web_search_prime",
            payload={"input": {"search_query": "openclaw latest version"}},
        )
    )
    captured = capsys.readouterr()
    assert "Web Search(\"openclaw latest version\")" in captured.out


def test_renderer_tool_call_summary(capsys):
    renderer = ConsoleRenderer(RendererOptions(style="claude", show_tool_args=False))
    renderer.tool_call("bash", {"command": "echo hello", "timeout": 30})
    captured = capsys.readouterr()
    assert "Bash(echo hello)" in captured.out
    assert "Running..." in captured.out


def test_renderer_tool_result_compact_for_claude(capsys):
    from mini_agent.tools.base import ToolResult

    renderer = ConsoleRenderer(RendererOptions(style="claude", show_tool_args=False))
    renderer.tool_result("record_note", ToolResult(success=True, content="Recorded note: hello"))
    captured = capsys.readouterr()
    assert "Note saved" in captured.out


def test_renderer_markdown_table_and_bold(capsys):
    renderer = ConsoleRenderer(RendererOptions(style="claude", render_markdown=True))
    renderer.assistant_content(
        "**当前实现状态**\n\n"
        "| 里程碑 | 状态 |\n"
        "|---|---|\n"
        "| M1 | 完成 |\n"
        "| M2 | 完成 |\n"
    )
    captured = capsys.readouterr()
    assert "当前实现状态" in captured.out
    assert "| 里程碑 " in captured.out or "| 里程碑|" in captured.out
    assert "+-" in captured.out


def test_renderer_markdown_bold_heading_line(capsys):
    renderer = ConsoleRenderer(RendererOptions(style="claude", render_markdown=True))
    renderer.assistant_content("**技术栈**\n- Python\n- FastAPI")
    captured = capsys.readouterr()
    assert "技术栈" in captured.out
    assert "**技术栈**" not in captured.out
