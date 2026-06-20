"""Unit tests for core registry loading + search-path resolution."""

import json

import pytest

from docket import core


def test_no_registry_returns_empty(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)  # no ./projects.json here
    monkeypatch.setattr(
        core.os.path, "expanduser", lambda p: p.replace("~", str(tmp_path))
    )
    assert core.load_registry(None) == []


def test_search_paths_order(monkeypatch):
    monkeypatch.setenv("DOCKET_REGISTRY", "/env/reg.json")
    paths = core.registry_search_paths("/flag/reg.json")
    assert paths[0].endswith("reg.json") and "flag" in paths[0]
    assert any("env" in p for p in paths)
    assert any(p.endswith("projects.json") for p in paths)


def test_load_via_env_var(monkeypatch, registry_file):
    monkeypatch.setenv("DOCKET_REGISTRY", registry_file)
    projects = core.load_registry(None)
    assert len(projects) == 1
    assert projects[0].name == "repo"
    assert core.REGISTRY_INSTRUCTION_TEMPLATE == "Implement {path} now."


def test_load_full_entry_fields(tmp_path, project):
    reg = tmp_path / "r.json"
    reg.write_text(
        json.dumps(
            {
                "projects": [
                    {
                        "name": "x",
                        "path": project.path,
                        "allowed_tools": ["Read"],
                        "model": "claude-sonnet-4-6",
                        "max_turns": 40,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    p = core.load_registry(str(reg))[0]
    assert p.allowed_tools == ["Read"]
    assert p.model == "claude-sonnet-4-6"
    assert p.max_turns == 40
    assert core.REGISTRY_INSTRUCTION_TEMPLATE is None  # absent -> None


def test_bad_top_level_shape(tmp_path):
    reg = tmp_path / "r.json"
    reg.write_text(json.dumps(["not", "a", "dict"]), encoding="utf-8")
    with pytest.raises(ValueError, match="expected top-level shape"):
        core.load_registry(str(reg))


def test_missing_name(tmp_path, project):
    reg = tmp_path / "r.json"
    reg.write_text(json.dumps({"projects": [{"path": project.path}]}), encoding="utf-8")
    with pytest.raises(ValueError, match="missing 'name'"):
        core.load_registry(str(reg))


def test_duplicate_name(tmp_path, project):
    reg = tmp_path / "r.json"
    reg.write_text(
        json.dumps(
            {
                "projects": [
                    {"name": "dup", "path": project.path},
                    {"name": "dup", "path": project.path},
                ]
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="duplicate project name"):
        core.load_registry(str(reg))


def test_missing_path(tmp_path):
    reg = tmp_path / "r.json"
    reg.write_text(json.dumps({"projects": [{"name": "x"}]}), encoding="utf-8")
    with pytest.raises(ValueError, match="missing 'path'"):
        core.load_registry(str(reg))


def test_path_not_a_directory(tmp_path):
    reg = tmp_path / "r.json"
    reg.write_text(
        json.dumps(
            {
                "projects": [
                    {"name": "x", "path": str(tmp_path / "nope")},
                ]
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="not a directory"):
        core.load_registry(str(reg))
