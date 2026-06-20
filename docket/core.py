"""docket core: registry, plan discovery/read, manual command, headless runner, batch."""
from __future__ import annotations

import json
import os
import re
import subprocess
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from queue import Empty, Queue

from docket import frontmatter, tracker

DEFAULT_ALLOWED_TOOLS = ["Read", "Edit", "Write",
                         "Bash(pytest:*)", "Bash(npm test:*)", "Bash(npm run test:*)"]

# {path} is filled with the plan's repo-relative path: .agents_workspace/planning/<slug>.md
DEFAULT_INSTRUCTION_TEMPLATE = (
    "Read the plan at {path} and implement it fully. The plan may reference sibling "
    "files (e.g. a SKELETON or earlier iterations) — read those as needed. Make the "
    "code changes the plan describes."
)

PLANNING_DIR = ".agents_workspace/planning"
IMPL_DIR = ".agents_workspace/implementation"

# Set by load_registry; the optional top-level "instruction_template" from projects.json.
REGISTRY_INSTRUCTION_TEMPLATE: str | None = None

_SEGMENT = re.compile(r"^[A-Za-z0-9._-]+$")


@dataclass
class Project:
    name: str
    path: str
    allowed_tools: list[str] = field(default_factory=lambda: list(DEFAULT_ALLOWED_TOOLS))
    model: str | None = None
    max_turns: int = 30


@dataclass
class Plan:
    project: str
    slug: str            # relative path under planning/, sans .md; may contain "/"
    title: str
    status: str          # ready|running|implemented — sourced from the sidecar, NOT the plan
    body: str = ""       # "" for list summaries; full markdown from read_plan
    history: list = field(default_factory=list)


def safe_slug(slug: str) -> str:
    """Validate a plan slug used as both a relative path and a URL/query value.

    Accept one or more `/`-separated segments each matching ^[A-Za-z0-9._-]+$;
    reject `.`/`..` segments, leading/trailing `/`, empty slugs, and absolute paths.
    Makes it impossible to escape planning/. Returns the slug unchanged on success.
    """
    if not slug or slug.startswith("/") or slug.endswith("/"):
        raise ValueError(f"invalid slug: {slug!r}")
    segments = slug.split("/")
    for seg in segments:
        if seg in ("", ".", "..") or not _SEGMENT.match(seg):
            raise ValueError(f"invalid slug segment {seg!r} in {slug!r}")
    return slug


def _registry_search_paths(path: str | None) -> list[Path]:
    """First match wins: --registry → $DOCKET_REGISTRY → ./projects.json → ~/.config."""
    candidates: list[str] = []
    if path:
        candidates.append(path)
    if os.environ.get("DOCKET_REGISTRY"):
        candidates.append(os.environ["DOCKET_REGISTRY"])
    candidates.append("./projects.json")
    candidates.append("~/.config/docket/projects.json")
    return [Path(os.path.expanduser(c)) for c in candidates]


def registry_search_paths(path: str | None = None) -> list[str]:
    """The resolved search paths, for the frontends' empty-state display."""
    return [str(p) for p in _registry_search_paths(path)]


def load_registry(path: str | None = None) -> list[Project]:
    """Resolve and load projects.json. No registry found -> [] (empty state, not error)."""
    global REGISTRY_INSTRUCTION_TEMPLATE
    found = next((p for p in _registry_search_paths(path) if p.is_file()), None)
    if found is None:
        return []

    with open(found, encoding="utf-8") as fh:
        data = json.load(fh)

    if not isinstance(data, dict) or not isinstance(data.get("projects"), list):
        raise ValueError(f"{found}: expected top-level shape {{\"projects\": [...]}}")

    REGISTRY_INSTRUCTION_TEMPLATE = data.get("instruction_template") or None

    projects: list[Project] = []
    seen: set[str] = set()
    for entry in data["projects"]:
        name = entry.get("name")
        if not name:
            raise ValueError(f"{found}: a project entry is missing 'name'")
        if name in seen:
            raise ValueError(f"{found}: duplicate project name {name!r}")
        seen.add(name)

        raw_path = entry.get("path")
        if not raw_path:
            raise ValueError(f"{found}: project {name!r} is missing 'path'")
        abspath = os.path.abspath(os.path.expanduser(raw_path))
        if not os.path.isdir(abspath):
            raise ValueError(f"{found}: project {name!r} path is not a directory: {abspath}")

        projects.append(Project(
            name=name,
            path=abspath,
            allowed_tools=entry.get("allowed_tools") or list(DEFAULT_ALLOWED_TOOLS),
            model=entry.get("model"),
            max_turns=entry.get("max_turns", 30),
        ))
    return projects


def _planning_root(project: Project) -> Path:
    return Path(project.path) / ".agents_workspace" / "planning"


def list_plans(project: Project) -> list[Plan]:
    """Recursively discover planning/**/*.md -> Plan summaries (body=""), sorted."""
    root = _planning_root(project)
    if not root.is_dir():
        return []

    plans: list[Plan] = []
    for md in root.rglob("*.md"):
        if not md.is_file():
            continue
        slug = md.relative_to(root).with_suffix("").as_posix()
        meta, _ = frontmatter.parse(md.read_text(encoding="utf-8"))
        status = tracker.read_record(project, slug)["status"]
        plans.append(Plan(
            project=project.name,
            slug=slug,
            title=meta.get("title") or slug,
            status=status,
        ))
    plans.sort(key=lambda p: (p.status, p.slug))
    return plans


def read_plan(project: Project, slug: str) -> Plan:
    """Full plan body + status + history. Missing file -> FileNotFoundError."""
    slug = safe_slug(slug)
    md = _planning_root(project) / f"{slug}.md"
    if not md.is_file():
        raise FileNotFoundError(f"plan not found: {project.name}/{slug}")
    text = md.read_text(encoding="utf-8")
    meta, _ = frontmatter.parse(text)
    rec = tracker.read_record(project, slug)
    return Plan(
        project=project.name,
        slug=slug,
        title=meta.get("title") or slug,
        status=rec["status"],
        body=text,
        history=rec["history"],
    )


def manual_command(project: Project, slug: str) -> str:
    """Copy-pasteable command for running the plan yourself (feeds the plan body)."""
    slug = safe_slug(slug)
    plan_rel = f"{PLANNING_DIR}/{slug}.md"
    return (
        f"cd {project.path} && claude -p < {plan_rel}\n"
        f"# or: cd {project.path} && claude   (then paste / @-mention the plan file)"
    )


# --- Headless run (ITER_03) ---------------------------------------------------

_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def project_lock(path: str) -> threading.Lock:
    """Per-project lock so two headless runs on the same repo can't collide."""
    with _locks_guard:
        return _locks.setdefault(path, threading.Lock())


def resolve_instruction(slug: str, override: str | None) -> str:
    """Build the stdin instruction that names the plan file. {path} is substituted."""
    slug = safe_slug(slug)
    path = f"{PLANNING_DIR}/{slug}.md"
    template = override or REGISTRY_INSTRUCTION_TEMPLATE or DEFAULT_INSTRUCTION_TEMPLATE
    if "{path}" in template:
        return template.format(path=path)
    return template


def format_event(raw: str) -> str | None:
    """Parse one NDJSON stream-json event into a short display line, or None to skip."""
    raw = raw.rstrip("\n")
    if not raw.strip():
        return None
    try:
        ev = json.loads(raw)
    except json.JSONDecodeError:
        return raw  # defensive: pass non-JSON through verbatim

    etype = ev.get("type")
    if etype == "system":
        return None  # init event — skip
    if etype == "assistant":
        parts = []
        for block in ev.get("message", {}).get("content", []):
            btype = block.get("type")
            if btype == "text":
                text = block.get("text", "").strip()
                if text:
                    parts.append(text)
            elif btype == "tool_use":
                name = block.get("name", "tool")
                digest = _tool_digest(block.get("input", {}))
                parts.append(f"▸ {name}{(' ' + digest) if digest else ''}")
        return "\n".join(parts) if parts else None
    if etype == "result":
        if ev.get("is_error") or ev.get("subtype") not in (None, "success"):
            return f"[error] {ev.get('subtype', 'error')}"
        return "[done]"
    return None


def _tool_digest(inp: dict) -> str:
    """One-line arg digest for a tool_use event (e.g. the edited path or command)."""
    for key in ("file_path", "path", "pattern", "command", "url"):
        val = inp.get(key)
        if isinstance(val, str):
            return val.splitlines()[0][:80] if val else ""
    return ""


def run_implement(project: Project, slug: str, instruction: str, *,
                  on_spawn=None, run_id: str | None = None):
    """Generator: spawn `claude -p`, pipe the INSTRUCTION (names the plan file) on stdin,
    yield human-readable display lines. The plan body is never piped. on_spawn(proc) hands
    the Popen handle to the caller for stop()."""
    slug = safe_slug(slug)
    rec = tracker.read_record(project, slug)
    if rec["status"] not in ("ready", "implemented"):
        raise ValueError(f"{project.name}/{slug} is '{rec['status']}', not runnable")

    lock = project_lock(project.path)
    if not lock.acquire(blocking=False):
        raise RuntimeError("a run is already active for this project")
    try:
        tracker.set_status(project, slug, "running", trigger="headless", run_id=run_id)
        allow = ",".join(project.allowed_tools)
        cmd = ["claude", "-p",
               "--output-format", "stream-json", "--verbose",
               "--permission-mode", "acceptEdits",
               "--max-turns", str(project.max_turns),
               "--allowedTools", allow]
        if project.model:
            cmd += ["--model", project.model]

        proc = subprocess.Popen(
            cmd, cwd=project.path,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1,
        )
        if on_spawn:
            on_spawn(proc)
        proc.stdin.write(instruction)
        proc.stdin.close()
        try:
            for raw in proc.stdout:
                line = format_event(raw)
                if line is not None:
                    yield line
            proc.wait()
        finally:
            proc.stdout.close()

        ok = proc.returncode == 0
        tracker.set_status(project, slug, "implemented" if ok else "ready",
                           trigger="headless", run_id=run_id, rc=proc.returncode)
        yield f"[docket] run {'completed' if ok else f'ended (rc={proc.returncode})'}"
    finally:
        lock.release()


# --- Batch orchestration (ITER_03, server side) -------------------------------

@dataclass
class Run:
    run_id: str
    project: str
    slug: str
    instruction: str
    state: str = "queued"  # queued|running|done|failed|stopped|skipped
    proc: object | None = None
    queue: Queue = field(default_factory=Queue)


_SENTINEL = object()


class RunManager:
    """Server-side run + batch orchestrator: group by project, sequential per project,
    concurrent across projects, stop-on-failure within a project."""

    def __init__(self, projects: list[Project]):
        self._projects = {p.name: p for p in projects}
        self._runs: dict[str, Run] = {}
        self._guard = threading.Lock()

    def set_projects(self, projects: list[Project]) -> None:
        self._projects = {p.name: p for p in projects}

    def submit(self, items: list[dict]) -> list[Run]:
        """Validate every item, create a Run for each up front, group by project, and
        spawn one daemon thread per project. Returns all runs (state queued/running)."""
        validated: list[tuple[Project, str, str]] = []
        for item in items:
            project = self._projects.get(item.get("project"))
            if project is None:
                raise ValueError(f"unknown project: {item.get('project')!r}")
            slug = safe_slug(item.get("slug", ""))
            rec = tracker.read_record(project, slug)
            if rec["status"] not in ("ready", "implemented"):
                raise ValueError(f"{project.name}/{slug} is '{rec['status']}', not runnable")
            instruction = resolve_instruction(slug, item.get("instruction"))
            validated.append((project, slug, instruction))

        runs: list[Run] = []
        by_project: dict[str, list[Run]] = {}
        for project, slug, instruction in validated:
            run = Run(run_id=uuid.uuid4().hex, project=project.name,
                      slug=slug, instruction=instruction)
            runs.append(run)
            by_project.setdefault(project.name, []).append(run)

        with self._guard:
            for run in runs:
                self._runs[run.run_id] = run

        for project_name, project_runs in by_project.items():
            t = threading.Thread(
                target=self._run_project_batch,
                args=(self._projects[project_name], project_runs),
                daemon=True,
            )
            t.start()
        return runs

    def _run_project_batch(self, project: Project, runs: list[Run]) -> None:
        failed = False
        for run in runs:
            if failed:
                run.state = "skipped"
                run.queue.put(_SENTINEL)
                continue
            run.state = "running"
            try:
                gen = run_implement(
                    project, run.slug, run.instruction,
                    on_spawn=lambda p, r=run: setattr(r, "proc", p),
                    run_id=run.run_id,
                )
                for line in gen:
                    run.queue.put(line)
                if run.state != "stopped":
                    run.state = "done" if (run.proc is None or run.proc.returncode == 0) \
                        else "failed"
            except (ValueError, RuntimeError) as exc:
                run.queue.put(f"[docket] {exc}")
                run.state = "failed"
            run.queue.put(_SENTINEL)
            if run.state in ("failed", "stopped"):
                failed = True

    def stream(self, run_id: str, keepalive: float = 15.0):
        """Look up the run and return the SSE generator. Raises KeyError eagerly for an
        unknown run_id (so the handler can answer 404 before sending stream headers — a
        generator function would defer that raise until first iteration)."""
        run = self._runs.get(run_id)
        if run is None:
            raise KeyError(run_id)
        return self._stream(run, keepalive)

    def _stream(self, run: Run, keepalive: float):
        """Drain one run's queue: yields ('data', line), ('keepalive', None) while idle,
        and finally ('end', state). A queued run just emits keep-alives until its turn in
        its project batch arrives."""
        while True:
            try:
                item = run.queue.get(timeout=keepalive)
            except Empty:
                yield ("keepalive", None)
                continue
            if item is _SENTINEL:
                break
            yield ("data", item)
        yield ("end", run.state)

    def stop(self, run_id: str) -> None:
        run = self._runs.get(run_id)
        if run is None:
            raise KeyError(run_id)
        if run.state not in ("queued", "running"):
            raise ValueError(f"run {run_id} is '{run.state}', not stoppable")
        run.state = "stopped"
        proc = run.proc
        if proc is not None:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
