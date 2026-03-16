"""Utilities for capturing and suppressing unwanted console output."""

from __future__ import annotations

import io
import sys
import threading
from contextlib import contextmanager
from typing import Callable


class OutputCapture:
    """Captures stdout/stderr output and optionally filters it."""

    def __init__(self, filter_fn: Callable[[str], bool] | None = None):
        self.filter_fn = filter_fn
        self.captured: list[str] = []
        self._original_stdout: sys.__stdout__ | None = None
        self._original_stderr: sys.__stderr__ | None = None
        self._capture_buffer = io.StringIO()
        self._lock = threading.Lock()

    def _should_capture(self, text: str) -> bool:
        if self.filter_fn is None:
            return True
        return self.filter_fn(text)

    def _make_write(self, original_write):
        def write(text: str) -> int:
            with self._lock:
                if self._should_capture(text):
                    self.captured.append(text)
                    self._capture_buffer.write(text)
                    return len(text)
                return original_write(text)
        return write

    def start(self) -> None:
        """Start capturing stdout and stderr."""
        self._original_stdout = sys.stdout
        self._original_stderr = sys.stderr

        class CapturingStream:
            def __init__(inner_self, original_stream):
                inner_self._original = original_stream
                inner_self.write = self._make_write(original_stream.write)
                inner_self.flush = original_stream.flush
                inner_self.isatty = original_stream.isatty

            def __getattr__(inner_self, name):
                return getattr(inner_self._original, name)

        sys.stdout = CapturingStream(self._original_stdout)
        sys.stderr = CapturingStream(self._original_stderr)

    def stop(self) -> list[str]:
        """Stop capturing and return captured lines."""
        if self._original_stdout is not None:
            sys.stdout = self._original_stdout
        if self._original_stderr is not None:
            sys.stderr = self._original_stderr
        return self.captured

    def get_output(self) -> str:
        """Get all captured output as a single string."""
        return self._capture_buffer.getvalue()


@contextmanager
def capture_output(filter_fn: Callable[[str], bool] | None = None):
    """Context manager for capturing stdout/stderr.

    Args:
        filter_fn: Optional function that returns True if the text should be captured
                  (suppressed from normal output). If None, all output is captured.

    Example:
        # Capture all output
        with capture_output() as cap:
            print("this will be captured")
        print(f"Captured: {cap.get_output()}")

        # Capture only specific patterns
        def is_sdk_log(text):
            return "[Lark]" in text or "connected to wss://" in text

        with capture_output(filter_fn=is_sdk_log) as cap:
            some_sdk_operation()  # SDK logs will be captured, other prints go through
    """
    capture = OutputCapture(filter_fn)
    capture.start()
    try:
        yield capture
    finally:
        capture.stop()


@contextmanager
def suppress_lark_logs():
    """Context manager specifically for suppressing lark-oapi SDK connection logs.

    The lark-oapi SDK outputs connection messages like:
        [Lark] [2026-03-16 10:20:15,872] [INFO] connected to wss://...

    This context manager captures and suppresses these logs while allowing
    other output to pass through normally.
    """
    def is_lark_log(text: str) -> bool:
        lark_indicators = [
            "[Lark]",
            "[lark",
            "connected to wss://",
            "lark_oapi",
            "feishu.cn/ws",
            "larksuite.com/ws",
        ]
        text_lower = text.lower()
        return any(indicator.lower() in text_lower for indicator in lark_indicators)

    capture = OutputCapture(filter_fn=is_lark_log)
    capture.start()
    try:
        yield capture
    finally:
        capture.stop()
