# Harness Profiles

## Profile Selection

| Profile | Use when | Installed model |
| --- | --- | --- |
| `minimal` | Small project, one owner, short task horizon, no formal plan review | Startup contract, project charter, progress, handoff, local structural check |
| `governed` | Multi-session work, several plans, reviewers, safety boundaries, durable evidence, or an IB-style coding harness | Everything in `minimal` plus docs authority map, proposed/active/completed plans, reviews, decisions, optimization intake, progress archive, and startup-document budgets |

Default to `minimal`. Choose `governed` only when the evidence clearly shows multi-session review-gated work, safety-sensitive scope, or the user explicitly asks for it (for example the `ib-agent-trading-sys` governance model). A too-heavy profile is a real failure mode: it routes every small task through plan/review ceremony and stalls coding work.

## Minimal Profile

The minimal profile installs only missing files:

- `AGENTS.md` — compact entry map, task triage, state discipline (conflict precedence, ledger triggers, distillation), and hard rules.
- `INSTRUCTIONS.md` — project objective, structure, verification, learned constraints, and project-specific constraints.
- `PROGRESS.md` — project board: latest facts and evidence only (Facts / In Progress / Blocked / Backlog / Open Unknowns / Verified Baseline); session intent lives in `HANDOFF.md`, history in the ledger.
- `HANDOFF.md` — transfer packet with fixed fields (`progress_ref`, `just_finished`, `current_task`, `first_action`, `do_not`, `open_questions`, `verify`); rewritten whole on every handoff, expired once work starts.
- `.harness/history/log.jsonl` — append-only event ledger, created on first append; readable and writable only through `scripts/harness_log.py`.
- `.harness/config.json` — machine-readable profile and inferred commands.
- `scripts/harness_log.py` — sole ledger entry point: `append` at checkpoints/verification/handoff/decision events, `query`/`tail` for on-demand retrieval and memory distillation. A decision event is the one-line "at time T we chose X"; in the governed profile a trade-off that constrains later phases or later plans is additionally registered in `docs/decisions/index.md`, with the ledger entry back-linking to it through `--refs`.
- `scripts/check-project-harness.py` — dependency-free structure check plus state-file lint (HANDOFF fields, PROGRESS sections, ledger pointer).
- `scripts/check-startup-doc-budget.py` — startup-doc size gate; `archive_required=true` triggers migrating the oldest completed entries into the ledger via `harness_log.py append`.

The state model closes a loop: rules → session execution (checkpoints update `PROGRESS.md` and append to the ledger) → verification evidence → handoff → distillation (durable lessons promoted from the ledger into `INSTRUCTIONS.md` Learned Constraints). Conflict precedence is git/tests > `PROGRESS.md` > `HANDOFF.md` > chat memory.

Do not add a feature tracker merely to satisfy a template. Add machine-readable feature state only when the target project already uses it or the user asks for it.

## Governed Profile

The governed profile adds:

- `docs/README.md` — authority and placement map.
- `docs/exec-plans/roadmap.md` — lifecycle contract and plan index.
- `docs/exec-plans/{proposed,active,completed,reviews}/index.md` — explicit state surfaces.
- Plan and review templates that carry no execution authority.
- `docs/decisions/` — the authority on which trade-offs bind later work: only `Accepted` entries bind, and `index.md` is that authority whether the decision's prose sits in a plan's `## Decisions` section or in a standalone file here. Registering a constraining trade-off is mandatory; a standalone file is written only when the trade-off spans several plans, arose outside a plan, or overturns an earlier `Accepted` decision.
- `docs/prd/` — record-only product-requirement layer: why the work matters and what success means. Intent authority only — an `Accepted` PRD may serve as a proposed plan's source evidence and never authorizes implementation; its goals and non-goals belong to the user, who edits them.
- `docs/specs/` — record-only behavior-contract layer: what the system must do, as `proposed`/`settled` entries. Intent authority, not state authority — a `settled` entry requires a verification pointer (a named test or runnable command), and implementation choices stay out of it.
- `docs/optimization/` — record-only improvement intake.
- `docs/progress-archive/` — long-form prose evidence only (postmortems, review records); event-level history stays in the ledger, whose entries point here via `--refs`.

`docs/prd/` and `docs/specs/` install unconditionally with the profile — directory, index, and template — exactly as `docs/optimization/` does; content is gated by wording, not by a config field. The enablement signal is a non-template row in `docs/prd/index.md` or `docs/specs/index.md`: until one appears, no PRD is drafted and the phase-boundary spec sync in `docs/exec-plans/roadmap.md` is a no-op. An empty layer is the expected steady state for a project that does not need it and never counts as a validation gap.

The lifecycle is tiered. Task triage in `AGENTS.md` decides which tier applies:

- **Direct execute (default)** — small, low-risk, clearly requested work. The user's request is the approval; no plan or review files are created.
- **Lightweight plan** — medium work planned inline in `PROGRESS.md`; execution starts immediately.
- **Governed lifecycle** — only for multi-session, irreversible, safety-sensitive, or explicitly requested formal work:

  `optimization intake -> proposed plan -> review + approval (grantable in one user reply) -> active plan -> phased implementation and verification -> completed plan`

Review confirmation and activation may be granted together in a single explicit user reply; never add extra confirmation rounds for ceremony. Routing small tasks into the governed lifecycle is as much a defect as skipping the lifecycle for large ones.

## Domain Overlays

Keep project-specific overlays local to the target repository. Examples include broker reconciliation, release approvals, regulated-data handling, hardware test gates, or document-signoff rules.

An overlay may strengthen the generic profile. It must not silently weaken the generic rules for scope preservation, evidence, handoff, or authority separation.

An overlay that strengthens a gate must state its trigger, its exit condition, and who may lift it. A gate with no exit condition is a defect, not a stricter standard.
