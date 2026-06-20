"""Unit tests for the headless run generator (subprocess mocked)."""

import pytest

from docket import core, tracker
from tests.conftest import write_plan

OK_EVENTS = [
    '{"type":"system"}',
    '{"type":"assistant","message":{"content":[{"type":"text","text":"working"}]}}',
    '{"type":"result","subtype":"success"}',
]


def test_run_implement_success_flips_to_implemented(project, fake_popen_factory):
    write_plan(project, "alpha")
    captured = fake_popen_factory(OK_EVENTS, returncode=0)
    spawned = []
    lines = list(
        core.run_implement(project, "alpha", "instr-text", on_spawn=spawned.append)
    )

    assert spawned, "on_spawn must receive the proc handle"
    assert captured["proc"].stdin.written == "instr-text"
    assert captured["proc"].stdin.closed
    assert "working" in lines
    assert lines[-1] == "[docket] run completed"
    assert tracker.read_record(project, "alpha")["status"] == "implemented"
    # the lock is released afterwards
    assert core.project_lock(project.path).acquire(blocking=False)


def test_run_implement_failure_reverts_to_ready(project, fake_popen_factory):
    write_plan(project, "alpha")
    fake_popen_factory(['{"type":"result","is_error":true}'], returncode=2)
    lines = list(core.run_implement(project, "alpha", "instr"))
    assert lines[-1] == "[docket] run ended (rc=2)"
    assert tracker.read_record(project, "alpha")["status"] == "ready"


def test_run_implement_passes_model_and_tools(project, fake_popen_factory):
    write_plan(project, "alpha")
    project.model = "claude-sonnet-4-6"
    project.allowed_tools = ["Read", "Edit"]
    captured = fake_popen_factory(OK_EVENTS, returncode=0)
    list(core.run_implement(project, "alpha", "instr"))
    cmd = captured["cmd"]
    assert "--model" in cmd and "claude-sonnet-4-6" in cmd
    assert "Read,Edit" in cmd
    assert captured["kwargs"]["cwd"] == project.path


def test_run_implement_rejects_non_runnable(project):
    write_plan(project, "alpha")
    tracker.set_status(project, "alpha", "running", trigger="headless")
    with pytest.raises(ValueError, match="not runnable"):
        list(core.run_implement(project, "alpha", "instr"))


def test_run_implement_rejects_when_locked(project, fake_popen_factory):
    write_plan(project, "alpha")
    fake_popen_factory(OK_EVENTS)
    core.project_lock(project.path).acquire(blocking=False)  # hold it
    with pytest.raises(RuntimeError, match="already active"):
        list(core.run_implement(project, "alpha", "instr"))
