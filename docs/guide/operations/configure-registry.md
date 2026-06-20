# Configure the registry

The registry is a single JSON file, `projects.json`, that tells docket which repos exist and how
to run each one. It is the only file you edit to operate docket.

## Where docket looks for it

Resolution order, **first match wins**:

1. `--registry PATH` (passed to `docket tui` or `docket serve`)
2. `$DOCKET_REGISTRY` environment variable
3. `./projects.json` (current working directory)
4. `~/.config/docket/projects.json`

If none exists, docket does **not** error — both frontends show a "no projects" empty state, and
`docket serve` prints the exact paths it searched. To see those paths, start the server with no
registry present.

## File shape

```json
{
  "instruction_template": "Read the plan at {path} and implement it fully. The plan may reference sibling files (e.g. a SKELETON or earlier iterations) — read those as needed. Make the code changes the plan describes.",
  "projects": [
    { "name": "pyxyflow", "path": "~/code/pyxyflow" },
    { "name": "mcp-harness", "path": "~/code/mcp-harness", "model": "claude-sonnet-4-6", "max_turns": 40 }
  ]
}
```

This is JSON only — no YAML, no TOML.

## Top-level fields

| Field | Required | Purpose |
|-------|----------|---------|
| `projects` | Yes | List of project entries (below). May be empty. |
| `instruction_template` | No | Default headless instruction for every project. `{path}` is replaced with the plan's repo-relative path. If omitted, docket's built-in default is used. Overridable per run at submit time. |

## Per-project fields

| Field | Required | Default | Purpose |
|-------|----------|---------|---------|
| `name` | Yes | — | Unique display name. Duplicate names are rejected. |
| `path` | Yes | — | Path to the repo (absolute or `~`-expanded). **Must be an existing directory** or docket refuses to load. |
| `allowed_tools` | No | `Read, Edit, Write, Bash(pytest:*), Bash(npm test:*), Bash(npm run test:*)` | Tools the headless agent may use, passed to `--allowedTools`. Anything outside this list is denied, never prompted. |
| `model` | No | the CLI's configured model | Pins the model for headless runs (`--model`). |
| `max_turns` | No | `30` | Caps the agent loop per headless run (`--max-turns`). |

## Procedure: add a repo

1. Open your `projects.json`.
2. Add an entry to `projects` with a unique `name` and a valid `path`:

   ```json
   { "name": "my-repo", "path": "~/code/my-repo" }
   ```

3. Save the file.

**Verify:** restart the frontend (or just refresh the browser page — docket reloads the registry
on every request) and confirm the project appears with its plans. If you see no plans under it,
the repo has no files under `<path>/.agents_workspace/planning/`.

**If it fails:** docket raises a clear, named error and the browser shows it as an HTTP 500:

- `project '<name>' path is not a directory` — fix the `path`.
- `duplicate project name '<name>'` — names must be unique.
- `a project entry is missing 'name'` / `missing 'path'` — add the required field.
- `expected top-level shape {"projects": [...]}` — the file isn't a JSON object with a `projects`
  list.

## Notes for operators

- docket reads the registry on **every** request/startup, so edits take effect without a restart
  on the browser side. The TUI reads it once at launch.
- A plan's own `status:` frontmatter is ignored. Lifecycle status comes only from the sidecar — do
  not try to drive status through the plan file.
