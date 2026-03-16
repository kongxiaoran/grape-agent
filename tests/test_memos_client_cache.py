import sys
import types

import mini_agent.tools.memos_memory_tool as memos_memory_tool


class _DummyMemOSClient:
    def __init__(self, api_key=None):
        self.api_key = api_key


def test_get_client_caches_by_api_key(monkeypatch):
    memos_pkg = types.ModuleType("memos")
    memos_api_pkg = types.ModuleType("memos.api")
    memos_client_mod = types.ModuleType("memos.api.client")
    memos_client_mod.MemOSClient = _DummyMemOSClient
    memos_api_pkg.client = memos_client_mod
    memos_pkg.api = memos_api_pkg

    monkeypatch.setitem(sys.modules, "memos", memos_pkg)
    monkeypatch.setitem(sys.modules, "memos.api", memos_api_pkg)
    monkeypatch.setitem(sys.modules, "memos.api.client", memos_client_mod)
    monkeypatch.setattr(memos_memory_tool, "_memos_available", True)
    monkeypatch.setattr(memos_memory_tool, "_memos_clients", {})

    first = memos_memory_tool._get_client("key_a")
    second = memos_memory_tool._get_client("key_a")
    third = memos_memory_tool._get_client("key_b")

    assert first is second
    assert first is not third
    assert first.api_key == "key_a"
    assert third.api_key == "key_b"
