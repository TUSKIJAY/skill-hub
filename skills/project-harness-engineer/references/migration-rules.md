# Existing-Project Migration Rules

## Evidence Order

Inspect in this order:

1. Repository-local `AGENTS.md`, nested `AGENTS.md`, `CLAUDE.md`, and equivalent instruction files.
2. `README`, project manifests, CI configuration, and existing test commands.
3. Current state files, plans, decision records, and handoffs.
4. Git branch, status, recent commits, and ignored runtime directories.

Treat current repository evidence as authoritative over generic templates.

## File Conflict Policy

- Missing path: safe candidate for installation.
- Existing file: skip automatically and produce a manual-merge recommendation.
- Expected file path occupied by a directory: block installation for that path.
- Dirty Git worktree: preview freely; apply only after explicit `--allow-dirty` authorization and overlap inspection.
- Existing `CLAUDE.md`: preserve it. Recommend a pointer to `AGENTS.md` only when the user wants a single authoritative entry; never overwrite it automatically.

## State Responsibilities

- `AGENTS.md` gives the map, triage, state discipline, and non-negotiable rules, not a full manual.
- `INSTRUCTIONS.md` holds stable project facts, constraints, and the Learned Constraints distilled from experience.
- `PROGRESS.md` is the project board: only facts that are already true, with evidence — Facts, In Progress (how far, not what next), Blocked (evidence + release condition), Backlog, Open Unknowns, Verified Baseline. Session intent never lives here.
- `HANDOFF.md` is the transfer packet: fixed fields answering "what does the next session do first", anchored to `PROGRESS.md` via `progress_ref`. Rewritten whole on every handoff, read once at startup, expired the moment work starts.
- `.harness/history/log.jsonl` is the append-only event ledger, written and read only through `scripts/harness_log.py`. Execution reads it solely on the four triggers named in `AGENTS.md`; startup never loads it.
- The split axis is facts versus intent: what is already true belongs in `PROGRESS.md`; what to do next belongs in `HANDOFF.md`; what happened belongs in the ledger.
- Conflict precedence: git/tests > `PROGRESS.md` > `HANDOFF.md` > chat memory. Fix the lower-priority file first, then continue.
- Machine runtime state belongs in a dedicated state file or data store, not in `HANDOFF.md`.
- `docs/prd/`, an `Accepted` entry in `docs/decisions/`, and `docs/specs/` (governed profile only) are the intent layers: why the work matters, and what behavior must hold. None of them constitutes implementation authority — that comes only from an active plan or a direct user request — and none is state authority, so none overrides git, tests, or `PROGRESS.md` on what is currently true.

## Migrating an Older Harness

- A harness installed by a previous skill version fails the new validation on the ledger components. Install the missing files incrementally (`apply_harness.py` only adds missing paths), then converge `PROGRESS.md` and `HANDOFF.md` to the new section/field shape by hand, preserving every project fact.
- Keep an existing `docs/progress-archive/` readable as-is; do not convert old prose archives into ledger entries retroactively. New events go to the ledger from the migration point onward.
- Never delete or rewrite historical evidence during migration; the migration itself should be recorded as a `milestone` ledger entry.

## Adding An Optional Docs Layer To An Installed Harness

An installed harness gains a later-added docs layer (for example `docs/prd/` or `docs/specs/`) incrementally, not by reinstalling:

- `apply_harness.py` only adds missing paths. Re-run it against the installed harness and it creates the new directory, index, and template while skipping every file that already exists. It never rewrites an installed file, so newer template wording does not reach files the project already has — those stay the project's own.
- Three items stay manual: add the layer's rows to the project's `docs/README.md` (authority layer, entry point, placement rule) by hand; re-word the affected lines of the project's `AGENTS.md` so the retrieval and write triggers point at the new layer instead of the old destination; then re-run `validate_harness.py` and the project's `scripts/check-project-harness.py`.
- Record the migration itself as a `milestone` ledger entry via `scripts/harness_log.py append`, with `--refs` naming the paths that changed.

## Authority Rules

- A clearly scoped user request is itself the approval for direct-execute and lightweight work; do not route small tasks through the plan lifecycle or ask again.
- A draft plan is not approval.
- A single explicit user reply may grant review confirmation and activation together; do not add extra confirmation rounds beyond what the user's reply already covers.
- An optimization record is not a plan.
- A completed phase does not authorize the next phase when a gate is required; phases may be merged only when the plan declares it, never silently.
- Historical evidence does not override current state.

## Proceed-Versus-Pause Rule

When scope is ambiguous, take the conservative, reversible interpretation, record the assumption in the state files, and keep working. Pause and ask only for destructive or irreversible actions, genuine scope expansion beyond the request, or conflicts inside the files the task must change. "Record a blocker and stop" is the last resort, not the default.

## Completion Rules

Before claiming the retrofit complete:

1. Run structural validation.
2. Run relevant native project checks.
3. Inspect the diff and ensure no unrelated path changed.
4. Replace generic generated statements with target-backed facts.
5. Refresh current progress and handoff.
6. Follow the repository's commit requirements.
