# Existing-Project Migration Rules

## Evidence Order

Inspect in this order:

1. Repository-local `AGENTS.md`, nested `AGENTS.md`, `CLAUDE.md`, and equivalent instruction files.
2. Project briefs, existing workflow entries, source materials, and actual acceptance methods; README/manifests/CI/tests where present.
3. Current state files, plans, decision records, and handoffs.
4. Git branch, status, recent commits, and ignored runtime directories.

Treat current repository evidence as authoritative over generic templates.

## File Conflict Policy

- Missing path: safe candidate for installation.
- Existing file: skip automatically and produce a manual-merge recommendation. The apply preview lists it under `manual_merge` (what is missing, plus a rendered `AGENTS.md` section); see Merging Into An Existing AGENTS.md.
- Expected file path occupied by a directory: block installation for that path.
- Dirty Git worktree: preview freely; apply only after explicit `--allow-dirty` authorization and overlap inspection.
- Existing `CLAUDE.md`: preserve it; never overwrite it. When it does not mention `AGENTS.md`, the apply preview lists it under `manual_merge` with the one-line `@AGENTS.md` pointer to append (Claude Code auto-loads `CLAUDE.md`, not `AGENTS.md`).

## State Responsibilities

- `AGENTS.md` gives the map, triage, state discipline, the non-negotiable rules (baseline confirmation before writes, scope-assumption recording), and a standalone Definition of Done, not a full manual.
- `INSTRUCTIONS.md` holds stable project facts, constraints, and the Learned Constraints distilled from experience.
- `PROGRESS.md` is the project board: only facts that are already true, with evidence — Facts, In Progress (how far, not what next), Blocked (evidence + release condition), Backlog, Open Unknowns, Verified Baseline. Session intent never lives here.
- `HANDOFF.md` is the transfer packet: fixed fields answering "what does the next session do first", anchored to `PROGRESS.md` via `progress_ref`. Rewritten whole on every handoff, read once at startup, expired the moment work starts.
- `.harness/history/log.jsonl` is the append-only event ledger, written and read only through `scripts/harness_log.py`. Execution reads it solely on the four triggers named in `AGENTS.md`; startup never loads it.
- The split axis is facts versus intent: what is already true belongs in `PROGRESS.md`; what to do next belongs in `HANDOFF.md`; what happened belongs in the ledger.
- Conflict precedence: current authoritative source/artifact checks (Git/tests where applicable) > `PROGRESS.md` > `HANDOFF.md` > chat memory. For read-only questions, answer from authoritative evidence and mention a relevant discrepancy without repairing state. Correct lower-priority state only when this task needs to update it or relies on it for a write.
- Machine runtime state belongs in a dedicated state file or data store, not in `HANDOFF.md`.
- `docs/prd/`, an `Accepted` entry in `docs/decisions/`, and `docs/specs/` (governed profile only) are the intent layers: why the work matters, and what behavior must hold. None of them constitutes implementation authority — that comes only from an active plan or a direct user request — and none is state authority, so none overrides git, tests, or `PROGRESS.md` on what is currently true.

## Merging Into An Existing AGENTS.md

A project with its own `AGENTS.md` (for example a reading contract) keeps that file. The installer skips it, so the new `INSTRUCTIONS.md`, `PROGRESS.md` and `HANDOFF.md` are unreachable until `AGENTS.md` routes to them; `validate_harness.py` and the project's `scripts/check-project-harness.py` both fail in that state.

- Run the apply preview. `manual_merge` names the missing capabilities and renders the section from `assets/fragments/agents-merge-section.md` with the project's interpreter and Git state.
- During authorized maintenance append that section to `AGENTS.md` as its own heading. Keep the project's existing rules above it; do not reword them to match the template.
- If a checksum manifest (`MANIFEST.sha256`, `SHA256SUMS`, ...) is listed, update the merged file's entry in the same step and decide whether the new harness files belong in the distributed set.
- Re-run the preview (no `manual_merge` left), `validate_harness.py` and the project check, then record the merge as a `milestone` ledger entry.

## Migrating an Older Harness

- A harness installed by a previous skill version fails the new validation on the ledger components. Install the missing files incrementally (`apply_harness.py` only adds missing paths), then converge `PROGRESS.md` and `HANDOFF.md` to the new section/field shape by hand, preserving every project fact.
- Keep an existing `docs/progress-archive/` readable as-is; do not convert old prose archives into ledger entries retroactively. New events go to the ledger from the migration point onward.
- Never delete or rewrite historical evidence during migration; the migration itself should be recorded as a `milestone` ledger entry.

## Adding An Optional Docs Layer To An Installed Harness

An installed harness gains a later-added docs layer (for example `docs/prd/` or `docs/specs/`) incrementally, not by reinstalling:

- `apply_harness.py` only adds missing paths. Re-run it against the installed harness and it creates the new directory, index, and template while skipping every file that already exists. It never rewrites an installed file, so newer template wording does not reach files the project already has — those stay the project's own.
- Three items stay manual: add the layer's rows to the project's `docs/README.md` (authority layer, entry point, placement rule) by hand; re-word the affected lines of the project's `AGENTS.md` so the retrieval and write triggers point at the new layer instead of the old destination; then re-run `validate_harness.py` and the project's `scripts/check-project-harness.py`.
- Record the migration itself as a `milestone` ledger entry via `scripts/harness_log.py append`, with `--refs` naming the paths that changed.

## Merging The Restored Hard Rules Into An Installed Harness

The installer never rewrites an installed `AGENTS.md` or `INSTRUCTIONS.md`, so a project installed before these rules existed gets them only by a narrow manual merge that keeps its facts and permissions:

- Startup Contract: before writing or modifying, confirm the baseline (native build/test commands, or the declared `acceptance_checks` for non-software projects). A baseline that already fails is recorded with its impact and is not reported as a regression. Read-only queries skip this.
- Hard Rules: on scope ambiguity take the conservative, reversible reading and record the assumption in the state files; pause the request only for destructive or irreversible actions or clear expansion beyond the request.
- A standalone `## Definition of Done` with its five conditions, and, in the Verification text of both files, the sentence that checks whose inputs the change touched are re-run on the final state before completion is claimed.

Dropping or softening any of these during a merge weakens the harness.

## Adding The Context Budget To An Installed Harness

The installer only adds missing paths, so re-running it on an installed harness adds just `scripts/harness_read.py`; the rules, numbers and checks reach existing files only by a narrow manual merge. The apply preview names each item under `manual_merge` and prints the paste-ready text, rendered with the project's interpreter and its existing `context_budget` numbers. Preview stays write-free.

- `INSTRUCTIONS.md`: paste the `## Context Budget` section (source `assets/fragments/context-budget-section.md`) after AI Behavior Rules. The checks look for that heading (or `## 上下文预算`); a mention elsewhere does not count. Where the project already has stricter numbers or a stricter reading rule, keep the project's and write the same numbers into the config.
- `AGENTS.md`: append the step-4 sentence ("读取和输出按 `INSTRUCTIONS.md` 的 Context Budget 执行……") to the startup step that says what to read. A project that merged the harness section instead takes the matching bullet from `assets/fragments/agents-merge-section.md`.
- `.harness/config.json`: add the `context_budget` block; re-run `apply_harness.py` (same profile, preview first) to install `scripts/harness_read.py`. The scratch directory is not created and `.gitignore` is not edited; the preview reminds when `.gitignore` does not cover it (`.harness/history/log.jsonl` must stay tracked, so never ignore all of `.harness/`).
- `scripts/check-project-harness.py`: merge the parts the preview lists — the Context Budget lint that compares every number the section states with the config (`lint_context_budget`), the `scratch_dir` path rule (`scratch_dir_problem`), and `scripts/harness_read.py` in the required files. Without them the project's own check passes a section that disagrees with the config.
- `scripts/check-startup-doc-budget.py`: a project that never changed it takes the new template whole. A changed script (for example one that already has the D0035 shape limits) merges by hand the parts the preview lists — four-file total, `startup_budget` thresholds, action lines, shape limits — and keeps the project's own numbers.
- Do not touch the project's existing permissions or external-write boundaries.
- Re-run `validate_harness.py` (the missing section and reader are unscored warnings in this version), the project's `scripts/check-project-harness.py` and the budget script, then record the merge as a `milestone` ledger entry.

## Adding Task Cards To An Installed Harness

Task cards are an explicit opt-in (`--task-cards`), never part of a default install or migration. For an installed harness:

- Re-run `apply_harness.py --target <project> --profile <installed profile> --task-cards [--task-cards-dir <dir>]` (preview first). It creates only the missing `<dir>/index.md` and `<dir>/task-card-template.md` and skips every existing file; the result lists the remaining hand merges under `task_cards.manual_merge`.
- Merge by hand: add `"task_cards": {"dir": "<dir>", "max_active": 1}` to `.harness/config.json`; add the `## Task Cards` section (source `assets/task-cards/agents-section.md`, with the directory token replaced) to `AGENTS.md`; and merge the task-card lint into the project's existing script (its source is `assets/fragments/task-card-lint.py.frag`, rendered into `assets/minimal/scripts/check-project-harness.py.tmpl`; use the single-file `scripts/check-project-harness.py` generated by an apply preview as the merge reference). The installer skips that existing script, so without this merge cards are never linted.
- Run `validate_harness.py` (it checks the index and template only because `task_cards` is now configured) and the project's `scripts/check-project-harness.py`, then record the migration as a `milestone` ledger entry.
- The lint checks consistency, not truth. The optional hooks component (next section) stops the agent's own edits from recording `human` results; anything stronger is the target project's own permission work.

## Adding Hooks To An Installed Harness

Hooks are an explicit opt-in (`--hooks`), never part of a default install or migration. First run `scripts/check-project-harness.py`, `scripts/check-startup-doc-budget.py --strict` and `scripts/harness_log.py pending` on the project: the Stop hook blocks while any of them fails, read-only sessions included, so fix or record those failures before enabling it. Then re-run `apply_harness.py --target <project> --profile <installed profile> --hooks` (preview first): it creates `scripts/harness_hook.py`, and `.claude/settings.json` only when the project has none; for an existing one, paste the `hooks` block printed under `manual_merge` into it by hand. Add `"hooks": {"enabled": true}` to `.harness/config.json` (listed under `hooks.manual_merge`); list the project's expensive or irreversible commands under `hooks.gated_actions` so the hook asks the user before one runs. An older `scripts/harness_log.py` without `pending` is skipped by that Stop check (usage error, not open intents); merge the two-phase ledger (section above) to get it. Run `validate_harness.py`, then record the change as a `milestone` ledger entry.

## Portability And Ledger `show` In An Installed Harness

The installer only adds missing paths, so an installed project receives these changes as follows:

- Readable IDs and other writing rules for human-facing text moved to the separate `readable-docs` skill; re-running `apply_harness.py` no longer adds `scripts/check-id-readability.py`. A project that already has that script keeps using it as before; after the project adopts readable-docs, its `check.py` can replace the script, and whether to delete the script is the project's decision.
- Everything else is a narrow manual merge into the project's existing files. Never overwrite them with a whole rendered template: that discards project facts and local extensions.
  - `scripts/harness_log.py`: the `show --seq <N>` / `--id <X>` subcommand (exit 1 when nothing matches; duplicates are all printed), `query` showing and searching an entry's `id` when present, `ensure_utf8_stdio()`, and `utf-8-sig` reads.
  - `scripts/check-project-harness.py` and `scripts/check-startup-doc-budget.py`: `ensure_utf8_stdio()`; for the former also `utf-8-sig` reads of the config, state files and cards.
  - `AGENTS.md`: the `show --seq <N>` lookup in State Discipline's ledger bullet, and "影响范围无法预估" among the governed-lifecycle triggers in Task Triage. Write the project's verified interpreter command where the template says `{{PYTHON}}`.
  - `INSTRUCTIONS.md`: "项目存在更严格的本地规则时，以更严格规则为准。" in AI Behavior Rules.
  - `.harness/config.json`: `python_command` is optional; add it only if the project records its interpreter there.
- Run the project's verification commands afterwards and record the merge as a `milestone` ledger entry.

## Adding Two-Phase External Writes And The Entry Pointer To An Installed Harness

The installer only adds missing paths: re-running it adds `CLAUDE.md` when the project has none. Everything else is a narrow manual merge; the apply preview names each item under `manual_merge`, and `validate_harness.py` reports the gaps as unscored warnings.

- `scripts/harness_log.py`: a project that never changed it takes the new template whole; otherwise merge the `intent` entry type, `--closes <seq>` on `append` (adds `seq:<N>` to refs and refuses a seq that is not an intent) and the `pending` subcommand (`cmd_pending`; exit 1 while an intent is open). Existing entries and ids stay as they are.
- `AGENTS.md`: the State Discipline bullet that starts "外部写入两段记账" (the preview prints it rendered with the project's interpreter), `intent` among the ledger types, the `pending` run in the startup step before writes, and "本次的 intent 条目均已闭合" in the Definition of Done.
- `AGENTS.md` Hard Rules: the bullet that starts "恢复前闸门" (the preview prints it when missing); `HANDOFF.md`: `do_not` written as an unconditional gate without time qualifiers and `first_action` never an expensive action; `PROGRESS.md` In Progress: the job id and log location of a long-running task.
- `INSTRUCTIONS.md` Use Contract: the line that lists the project's external writes with their operation ids / idempotency keys and how to verify each afterwards, or "无外部写入".
- `HANDOFF.md`: when `pending` lists an open intent, `verify` names how to check whether it happened.
- `CLAUDE.md`: append the one-line pointer when the file exists without one; never copy rules into it. A CLI with another entry file (`GEMINI.md`) gets the same one line by hand.
- `scripts/check-project-harness.py`: merge `lint_entry_pointer` (a `CLAUDE.md` that exists must mention `AGENTS.md`).
- Re-run the preview, `validate_harness.py` and the project check, then record the merge as a `milestone` ledger entry.

## Adding The Plan Walkthrough Gate To An Installed Harness

The installer only adds missing paths, so a governed project installed before this gate existed gets it by a narrow manual merge. Re-run the apply preview with the installed profile: when `docs/exec-plans/roadmap.md` lacks the gate, `manual_merge` lists it with the paste-ready lifecycle step, and `validate_harness.py` reports the gap as an unscored warning.

- `docs/exec-plans/roadmap.md`: paste the step after the review-budget step and before "经用户批准后，计划移动到 `active/`"; renumber the later steps.
- `docs/README.md` Placement Rules, `docs/exec-plans/reviews/index.md`, `docs/exec-plans/reviews/review-template.md` and `docs/optimization/SOP.md`: the matching sentences from the templates. `docs/exec-plans/plan-template.md`: the "Walkthrough offer" line in the Review And Activation Gate section. Existing plans are not rewritten.
- The project's `readable-docs` rule card supplies the "how" (its `upgrade` mode brings the new card item); this skill only sets when the offer is mandatory.
- Keep the project's existing review budget and approval wording; re-run `validate_harness.py` and record the merge as a `milestone` ledger entry.

## Authority Rules

- A clearly scoped user request is itself the approval for direct-execute and lightweight work; do not route small tasks through the plan lifecycle or ask again.
- A draft plan is not approval.
- A single explicit user reply may grant review confirmation and activation together; do not add extra confirmation rounds beyond what the user's reply already covers.
- Agreement between agents is not a decision. After an approve verdict the agent offers the user a walkthrough (readable-docs plan-walkthrough rules) before activation; the user may hear it or skip it, and the revised plan is neither committed nor activated until the user answers. A user may ask for a walkthrough of any plan at any time.
- An optimization record is not a plan.
- A completed phase does not authorize the next phase when a gate is required; phases may be merged only when the plan declares it, never silently.
- Historical evidence does not override current state.

## Proceed-Versus-Pause Rule

When scope is ambiguous, take the conservative, reversible interpretation, record the assumption in the state files, and keep working. Pause the request only for destructive or irreversible actions or for scope that clearly exceeds the request (including a conflict inside the files the task must change that no conservative reading resolves). "Record a blocker and stop" is the last resort, not the default. The generated `AGENTS.md` carries the same rule under Hard Rules.

## Candidate migration

旧 roadmap 不必重复生命周期英文关键词：检查现有 proposed/active/completed/reviews 索引是否真实存在。旧 SOP 若是日常操作入口，保留其职责；优化记录不授予执行权的规则可放在 AGENTS 明确链接的 maintenance guide。不可仅因新模板有同名路径就覆盖旧 SOP。缺失的 docs 导航（prd/specs/decisions/archive）逐项补链接；INSTRUCTIONS 增加 Learned Constraints 入口但不虚构经验。只读验收条件与 handoff 引用规则需手工合并到现有 Use Contract，不能假设新增模板已更新旧文件。

The use/maintain routing and acceptance metadata are additive. Old installations remain readable; no automatic rewrite is performed. Add missing maintenance guidance, manually merge the request routing and use contract, and retain project-specific intent/permissions. New optional config fields do not turn an old config into a migration failure.

## Completion Rules

Before the first write, confirm the baseline (native checks, or the declared `acceptance_checks` for non-software projects). A baseline that already fails is recorded with its impact and is not reported as a regression of the retrofit.

Before claiming the retrofit complete:

1. Run structural validation.
2. Run relevant domain acceptance: native checks where present, otherwise observable source/artifact or human checks. Re-run on the final state every check whose inputs the retrofit changed; an earlier pass does not count. Human acceptance that no person has recorded stays "待验收" (pending), never done.
3. Inspect the diff and ensure no unrelated path changed.
4. Replace generic generated statements with target-backed facts.
5. Refresh current progress and handoff.
6. Follow the repository's commit requirements; in a non-Git project, record a recoverable version.

Profile changes require an explicit target profile: during authorized migration align `.harness/config.json` by hand before apply, then validate with `--profile <intended-profile>` rather than auto. Preview reports mismatches; apply refuses them before writing. Auto follows the declared profile, not directory presence alone.
