"""Unit tests for CLI dispatch."""

import docket.__main__ as main_mod


def test_no_command_prints_help(capsys):
    rc = main_mod.main([])
    assert rc == 1
    assert "usage" in capsys.readouterr().out.lower()


def test_tui_dispatch(monkeypatch):
    called = {}

    def fake_tui(registry=None):
        called["registry"] = registry
        return 0

    monkeypatch.setattr("docket.tui.run_tui", fake_tui)
    assert main_mod.main(["--registry", "/r.json", "tui"]) == 0
    assert called["registry"] == "/r.json"


def test_serve_dispatch(monkeypatch):
    called = {}

    def fake_serve(port, registry):
        called["port"] = port
        called["registry"] = registry
        return 0

    monkeypatch.setattr("docket.server.run_server", fake_serve)
    assert main_mod.main(["serve", "--port", "9000"]) == 0
    assert called["port"] == 9000
