# Harness Profiles

## Profile Selection

| Profile | Use when | Installed model |
| --- | --- | --- |
| `minimal` | Small project, one owner, short task horizon, no formal plan review | Startup contract, project charter, progress, handoff, local structural check |
| `governed` | Multi-session work, several plans, reviewers, safety boundaries, durable evidence, or an IB-style coding harness | Everything in `minimal` (including the startup-document budget check) plus docs authority map, proposed/active/completed plans, reviews, decisions, optimization intake, and progress archive |

Default to `minimal`. Choose `governed` only when the evidence clearly shows multi-session review-gated work, safety-sensitive scope, or the user explicitly asks for it (for example the `ib-agent-trading-sys` governance model). A too-heavy profile is a real failure mode: it routes every small task through plan/review ceremony and stalls ordinary project work.

## Minimal Profile

The minimal profile installs only missing files:

- `AGENTS.md` — compact entry map, task triage, state discipline (conflict precedence, ledger triggers, distillation), hard rules (baseline confirmation before writes, scope-assumption recording), and a standalone `## Definition of Done`.
- `CLAUDE.md` — one line, the `@AGENTS.md` pointer: Claude Code auto-loads `CLAUDE.md`, not `AGENTS.md`, so this makes it read the same entry; it never holds rules of its own.
- `INSTRUCTIONS.md` — project objective, structure, the Context Budget (outline before reading, line ranges past the budget, uncertain output to the scratch directory, count before detail, subagents return conclusions with locations), verification, learned constraints, and project-specific constraints.
- `PROGRESS.md` — project board: latest facts and evidence only (Facts / In Progress / Blocked / Backlog / Open Unknowns / Verified Baseline); session intent lives in `HANDOFF.md`, history in the ledger.
- `HANDOFF.md` — transfer packet with fixed fields (`progress_ref`, `just_finished`, `current_task`, `first_action`, `do_not`, `open_questions`, `verify`); rewritten whole on every handoff, expired once work starts.
- `.harness/history/log.jsonl` — append-only event ledger, created on first append; readable and writable only through `scripts/harness_log.py`.
- `.harness/config.json` — machine-readable profile and inferred commands, the `context_budget` numbers and `scratch_dir` (default `.harness/tmp`, set with `--scratch-dir`; never created or git-ignored by the installer), plus the `task_cards` and `hooks` blocks when those components are enabled. An optional `startup_budget` object (`files`, `total`, `shape`) overrides the budget script's thresholds field by field.
- `scripts/harness_log.py` — sole ledger entry point: `append` at checkpoints/verification/handoff/decision events, `query`/`tail` for on-demand retrieval and memory distillation. External writes are two-phase: `append --type intent` before the action (evidence = operation id / idempotency key), a `milestone` or `incident` appended with `--closes <seq>` after it; `pending` lists the intents still open and exits 1 while any remain. A decision event is the one-line "at time T we chose X"; in the governed profile a trade-off that constrains later phases or later plans is additionally registered in `docs/decisions/index.md`, with the ledger entry back-linking to it through `--refs`.
- `scripts/check-project-harness.py` — dependency-free structure check plus state-file lint (HANDOFF fields, PROGRESS sections, ledger pointer), a check that every number the INSTRUCTIONS.md Context Budget states equals the config (a mismatch fails and names the line) and that `scratch_dir` is a relative path inside the project, and, only when `task_cards` is configured, task-card lint.
- `scripts/harness_read.py` — budgeted reads: `outline` (total lines/bytes, a verdict, Markdown headings), `lines <start> <end>`, `head [N]`. Text only (binary refused with exit 2), UTF-8 with BOM tolerated, output capped by lines and bytes, long lines cut, and a "下一段从第 X 行开始" line when it stops early.
- `scripts/check-startup-doc-budget.py` — startup-doc gate: per-file size (`archive_required=true` triggers migrating the oldest completed entries into the ledger via `harness_log.py append`), the four files' total (warning 40,960 bytes, hard 57,344), and `PROGRESS.md` shape (`progress_shape`: at most 5 Completed entries and 12 Verified Baseline rows; Facts/In Progress items up to 900 bytes, baseline rows up to 400). A file over its hard byte limit is reported without being read; a hard line set below its warning line lowers the warning line, with a config warning. Prints an action line per crossed limit that names the biggest section (the ledger is suggested only for Completed entries); exit 1 on a hard limit, and with `--strict` exit 2 on any warning or shape limit, for commit gates.

The state model closes a loop: rules → session execution (checkpoints update `PROGRESS.md` and append to the ledger) → verification evidence → handoff → distillation (evidence-supported lessons promoted during authorized maintenance from the ledger into `INSTRUCTIONS.md` Learned Constraints). Conflict precedence is current authoritative source/artifact checks (Git/tests where applicable) > `PROGRESS.md` > `HANDOFF.md` > chat memory.

Default: no feature tracker. When the user asks for one-card-at-a-time work or a human acceptance gate, enable it explicitly with `apply_harness.py --task-cards` (see Task Cards below); never add it merely to satisfy a template. Other machine-readable feature state is added only when the target project already uses it or the user asks for it.

## Governed Profile

The governed profile adds:

- `docs/README.md` — authority and placement map.
- `docs/exec-plans/roadmap.md` — lifecycle contract and plan index.
- `docs/exec-plans/{proposed,active,completed,reviews}/index.md` — explicit state surfaces.
- Plan and review templates that carry no execution authority.
- `docs/decisions/` — the authority on which trade-offs bind later work: only `Accepted` entries bind, and `index.md` is that authority whether the decision's prose sits in a plan's `## Decisions` section or in a standalone file here. Registering a constraining trade-off is mandatory; a standalone file is written only when the trade-off spans several plans, arose outside a plan, or overturns an earlier `Accepted` decision.
- `docs/prd/` — record-only product-requirement layer: why the work matters and what success means. Intent authority only — an `Accepted` PRD may serve as a proposed plan's source evidence and never authorizes implementation; its goals and non-goals belong to the user, who edits them.
- `docs/specs/` — record-only behavior-contract layer: what the system must do, as `proposed`/`settled` entries. Intent authority, not state authority — a `settled` entry requires a verification pointer (a named test, runnable command, or reproducible manual procedure with source/artifact evidence), and implementation choices stay out of it.
- `docs/optimization/` — record-only improvement intake.
- `docs/progress-archive/` — long-form prose evidence only (postmortems, review records); event-level history stays in the ledger, whose entries point here via `--refs`.

`docs/prd/` and `docs/specs/` install unconditionally with the profile — directory, index, and template — exactly as `docs/optimization/` does; content is gated by wording, not by a config field. The enablement signal is a non-template row in `docs/prd/index.md` or `docs/specs/index.md`: until one appears, no PRD is drafted and the phase-boundary spec sync in `docs/exec-plans/roadmap.md` is a no-op. An empty layer is the expected steady state for a project that does not need it and never counts as a validation gap.

The lifecycle is tiered. Task triage in `AGENTS.md` decides which tier applies:

- **Direct execute (default)** — small, low-risk, clearly requested work. The user's request is the approval; no plan or review files are created.
- **Lightweight plan** — medium work planned inline in chat; execution starts immediately. Durable next-step intent belongs in `HANDOFF.md`, never facts-only `PROGRESS.md`.
- **Governed lifecycle** — only for multi-session, irreversible, safety-sensitive, or explicitly requested formal work:

  `optimization intake -> proposed plan -> agent review -> walkthrough offer (hear it or skip it) -> approval (grantable in one user reply) -> active plan -> phased implementation and verification -> completed plan`

Review confirmation and activation may be granted together in a single explicit user reply, given after the walkthrough offer; never add extra confirmation rounds for ceremony. Routing small tasks into the governed lifecycle is as much a defect as skipping the lifecycle for large ones.

## Task Cards (opt-in component)

Independent of the profile (works with `minimal` and `governed`) and off by default. It exists for "requirement -> small features -> one card at a time; the agent writes the change, a person verifies on the real target", and is enabled only by `apply_harness.py --task-cards [--task-cards-dir <dir>]` (default `docs/tasks`).

- Files, installed only when missing and never overwritten: `<dir>/index.md` (ID | title | status | covered requirements | last updated; at most one card in progress) and `<dir>/task-card-template.md` (a template that authorizes nothing).
- `.harness/config.json` gains `"task_cards": {"dir": "<dir>", "max_active": 1}`; `AGENTS.md` renders a `## Task Cards` section, which is absent when the component is not enabled.
- A card `TASK-<NNN>-<slug>.md` carries `status` (草稿, 已批准, 实施中, 待验收, 已完成, 未通过, 阻塞), `requirements`, `acceptance_owner`, and sections for goal, scope, declared files, constraints and risks, implementation contract, an acceptance table (ID | method `script`/`human` | steps or command | expected | evidence location | status | recorder | time), attempt log and conclusion. Acceptance item states: 待执行, 已执行, 待人工验收, 已通过, 未通过.
- Authority split: the agent may mark `script` items executed and fill the evidence location; only a person marks a `human` item passed or failed and names themselves as recorder. A card is done only when every item passed; while a human item awaits acceptance the card stays 待验收.
- The target project's `scripts/check-project-harness.py` lints cards only when `task_cards` is configured and the directory exists: vocabulary, the in-progress limit, required recorder/evidence fields, and done-implies-all-passed. That is a consistency check, not proof that a recorded result is true; the optional hooks component (below) stops the agent's own edits from recording a `human` result, and anything stronger rests on the target project's permissions.

## Hooks (opt-in component)

Independent of the profile and off by default; enabled only by `apply_harness.py --hooks`. With `hooks.gated_actions` declared in the config, a matching shell command asks the user before it runs: the enforced form of the pre-resume gate. It installs `scripts/harness_hook.py` and, when missing, `.claude/settings.json` (exec-form handlers on `Edit|Write|MultiEdit`, `Bash|PowerShell` and `Stop`), and adds `"hooks": {"enabled": true}` to the config. A passing hook is silent; a broken rule (direct ledger write, an agent-recorded `human` acceptance result, a failing project/budget/`pending` check at Stop, or an undeclared external write when `hooks.external_writes` is set) blocks with at most three stderr lines. It binds only Claude Code's own tool calls; other CLIs get a printed Git pre-commit sample, never installed.

## Use and maintenance

Use is the per-request default; only explicit workflow/rule changes enter maintenance. The generated `docs/harness-maintenance.md` is read on that route, not at normal startup. Domain acceptance can be commands or observable manual checks. No new approval is implied by maintenance, and profile selection does not grant authority.

## Domain Overlays

Keep project-specific overlays local to the target repository. Examples include broker reconciliation, release approvals, regulated-data handling, hardware test gates, or document-signoff rules.

An overlay may strengthen the generic profile. It must not silently weaken the generic rules for scope preservation, evidence, handoff, or authority separation.

An overlay that strengthens a gate must state its trigger, its exit condition, and who may lift it. A gate with no exit condition is a defect, not a stricter standard.
