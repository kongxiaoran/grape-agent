"""Tests for webterm bridge utility helpers."""

from mini_agent.webterm_bridge.utils import classify_command_risk, extract_json_object, wrap_command


def test_extract_json_object_direct():
    parsed = extract_json_object('{"command":"tail -n 200 /var/log/app.log","risk":"low"}')
    assert parsed is not None
    assert parsed["command"].startswith("tail")


def test_extract_json_object_from_markdown_fence():
    text = """建议如下:
```json
{"command":"grep -n error app.log","risk":"medium","reason":"定位报错"}
```
"""
    parsed = extract_json_object(text)
    assert parsed is not None
    assert parsed["risk"] == "medium"


def test_wrap_command_adds_markers():
    marker, wrapped = wrap_command("tail -n 10 app.log", trace_id="tr_1")
    assert marker == "tr_1"
    assert "__MA_BEGIN_tr_1__" in wrapped
    assert "__MA_END_tr_1__$rc" in wrapped


def test_classify_command_risk():
    deny = ["rm", "shutdown"]
    allow = ["grep", "tail"]
    assert classify_command_risk("grep -n error app.log", deny, allow) == "low"
    assert classify_command_risk("rm -rf /tmp/xx", deny, allow) == "high"
    assert classify_command_risk("python script.py", deny, allow) == "medium"
