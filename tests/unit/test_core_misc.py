"""Unit tests for instruction resolution, event formatting, tool digest."""

import pytest

from docket import core


# --- resolve_instruction ------------------------------------------------------


def test_resolve_instruction_default_template():
    out = core.resolve_instruction("alpha", None)
    assert ".agents_workspace/planning/alpha.md" in out


def test_resolve_instruction_registry_template(monkeypatch):
    monkeypatch.setattr(core, "REGISTRY_INSTRUCTION_TEMPLATE", "Do {path} please")
    assert (
        core.resolve_instruction("a/b", None)
        == "Do .agents_workspace/planning/a/b.md please"
    )


def test_resolve_instruction_override_with_path():
    assert (
        core.resolve_instruction("x", "Run {path}")
        == "Run .agents_workspace/planning/x.md"
    )


def test_resolve_instruction_override_verbatim_no_path():
    assert core.resolve_instruction("x", "just do it") == "just do it"


def test_resolve_instruction_validates_slug():
    with pytest.raises(ValueError):
        core.resolve_instruction("../x", None)


# --- format_event -------------------------------------------------------------


def test_format_event_blank_returns_none():
    assert core.format_event("   \n") is None


def test_format_event_non_json_passthrough():
    assert core.format_event("not json at all") == "not json at all"


def test_format_event_system_skipped():
    assert core.format_event('{"type": "system"}') is None


def test_format_event_assistant_text():
    ev = '{"type":"assistant","message":{"content":[{"type":"text","text":" hi "}]}}'
    assert core.format_event(ev) == "hi"


def test_format_event_assistant_tool_use_with_digest():
    ev = (
        '{"type":"assistant","message":{"content":'
        '[{"type":"tool_use","name":"Edit","input":{"file_path":"a/b.py"}}]}}'
    )
    assert core.format_event(ev) == "▸ Edit a/b.py"


def test_format_event_assistant_tool_use_no_digest():
    ev = (
        '{"type":"assistant","message":{"content":'
        '[{"type":"tool_use","name":"Think","input":{}}]}}'
    )
    assert core.format_event(ev) == "▸ Think"


def test_format_event_assistant_other_block_skipped():
    # a content block that is neither text nor tool_use is ignored
    ev = '{"type":"assistant","message":{"content":[{"type":"thinking","text":"hmm"}]}}'
    assert core.format_event(ev) is None


def test_format_event_assistant_empty_content_returns_none():
    ev = '{"type":"assistant","message":{"content":[{"type":"text","text":"   "}]}}'
    assert core.format_event(ev) is None


def test_format_event_result_success():
    assert core.format_event('{"type":"result","subtype":"success"}') == "[done]"


def test_format_event_result_is_error():
    assert core.format_event('{"type":"result","is_error":true}') == "[error] error"


def test_format_event_result_error_subtype():
    out = core.format_event('{"type":"result","subtype":"error_max_turns"}')
    assert out == "[error] error_max_turns"


def test_format_event_unknown_type_returns_none():
    assert core.format_event('{"type":"user"}') is None


# --- _tool_digest -------------------------------------------------------------


def test_tool_digest_truncates_and_first_line():
    long = "x" * 200
    assert core._tool_digest({"command": f"line1\n{long}"}) == "line1"


def test_tool_digest_empty_string_value():
    assert core._tool_digest({"file_path": ""}) == ""


def test_tool_digest_no_known_keys():
    assert core._tool_digest({"other": "z"}) == ""
