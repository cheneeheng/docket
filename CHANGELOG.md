# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-06-20

First stable release. docket is a local, single-user command-center over many Claude Code
repos: it reads plan markdown from each repo's `.agents_workspace/planning/`, tracks each
plan's lifecycle in a docket-owned JSON sidecar, and implements plans manually or headless
via `claude -p`.

### Added

- **Plan discovery and lifecycle tracking** — reads plans from each registered repo's
  `.agents_workspace/planning/`; a docket-owned sidecar under
  `.agents_workspace/implementation/<slug>.json` tracks a closed-set lifecycle
  (`ready | running | implemented`) with a fixed transition table and recorded history.
- **Headless implementation** — runs plans via `claude -p`, piping a short instruction that
  names the plan file (never the plan body), with per-project `threading.Lock` serializing
  same-repo runs and concurrent runs across projects.
- **Textual TUI** (`docket tui`) — terminal interface that streams one run at a time.
- **Localhost browser UI** (`docket serve`) — stdlib `ThreadingHTTPServer` with a
  hand-written JSON API and SSE stream; no framework, no build step. Binds `127.0.0.1` only.
- **Batch orchestration** — server-side `RunManager` for running multiple plans, with
  startup recovery (`reset_stale_runs`) for runs interrupted by a crash.
- **Registry configuration** — `projects.json` registry with resolution order
  `--registry PATH` → `$DOCKET_REGISTRY` → `./projects.json` → `~/.config/docket/projects.json`;
  per-project `model`, `max_turns`, and `instruction_template` overrides.
- **Path-traversal guard** — every external slug passes through `core.safe_slug`, keeping
  access inside `planning/` / `implementation/`.
- **Atomic sidecar writes** — temp file + `os.replace`, with a bounded Windows retry on
  transient `PermissionError`.
- **Documentation** — `ARCHITECTURE.md` (diagrams + key decisions), `CLAUDE.md`, and a
  user/operator guide under `docs/guide`.
- **Test suite** — `tests/` (`unit/` + `api/`) at 100% line+branch coverage, gated in
  `pyproject.toml`.

### Security

- Both frontends bind to `127.0.0.1` only; localhost-only binding is the entire auth model
  for this single-user MVP. docket never handles API keys (the headless runner shells out to
  an already-authenticated `claude` CLI).

[1.0.0]: https://github.com/cheneeheng/docket/releases/tag/v1.0.0
