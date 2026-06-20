# Decision Log

### Entry 1

**Type:** Decision
**Mode:** Autonomous
**Timestamp:** 2026-06-20T00:00:00Z
**Task:** Implement docket from the SKELETON → ITER_01..03 plan to MVP.

**Context:** ITER_03 §04 specifies an atomic sidecar write via `os.replace` over the target.
On Windows a just-written target file is transiently locked by Defender/indexer, so an
immediate overwrite deterministically failed with `PermissionError (WinError 5)` in a
round-trip test (mark → reopen on the same plan). Plain `os.replace` to overwrite otherwise
works.
**Decision:** Kept the spec's atomic `os.replace` and added a bounded retry (10× @ 50ms) on
`PermissionError` in `tracker._atomic_write`. This preserves the crash-safety guarantee while
tolerating the platform's transient lock. Not a new dependency; ~6 lines.
**Impact / Risk:** Worst case a status write blocks up to ~0.5s before raising. Negligible for
a local single-user tool. No effect on POSIX where the lock doesn't occur.
**Outcome:** Round-trip test (mark/reopen/headless lifecycle/reset_stale_runs) passes.

### Entry 2

**Type:** Decision
**Mode:** Autonomous
**Timestamp:** 2026-06-20T00:00:00Z
**Task:** Batch-implement instruction UX in both frontends (ITER_03 §05).

**Context:** The plan describes a per-plan, individually-editable instruction *panel* for batch
submit (browser) and an instruction prompt (TUI). A full inline multi-textarea panel is
significant UI code not core to the MVP behavior (per-plan distinct instructions).
**Decision:** Satisfied the functional requirement — distinct instruction per plan — with the
minimum UI: the browser collects each selected plan's instruction via sequential
`window.prompt` calls (each pre-filled with the resolved template), and the TUI uses a single
`InstructionModal` for single-implement plus per-plan default resolution for batch. Different
instructions per plan are still possible; the dedicated multi-row panel is deferred.
**Impact / Risk:** Less polished batch UX than the plan's panel; behavior (per-plan
instructions, per-project sequential, concurrent across projects, stop-on-failure) is fully
intact. Easy to upgrade to a panel later without touching core.
**Outcome:** Functional; not yet runtime-tested for a live headless run (requires the `claude`
CLI + `textual` installed).
