---
name: harness
description: Create, audit, and improve project-local agent harnesses for software, research, documents, and operational workflows, with restartable state and evidence-based verification. Use when asked to build or change AGENTS.md, project rules, workflow definitions, handoff, or harness governance. Ordinary requests to run an existing workflow use that project's operating instructions, without invoking harness maintenance. Can add an opt-in task-card component (one card at a time, human acceptance gate) and opt-in Claude Code hooks (silent unless a rule breaks) only when explicitly requested. Does not reorganize unrelated project files.
---

# harness

Build a small project-local harness that lets agents deliver work, verify outcomes, and resume without chat history. The project can be a folder of research or documents; Git, source code, CI, and executable tests are optional.

Resolve this directory as `SKILL_ROOT`; use the project's documented runtime. A generic `python` below stands for that verified interpreter, not permission to change environments.

## Portability

- Python 3.9+ standard library on Windows, macOS or Linux. Verify the real interpreter (`python --version`, `python3 --version` or `py -3 --version`); a WindowsApps alias alone is not proof.
- The skill scripts and every generated script force UTF-8 stdout/stderr, so Chinese output survives a GBK/cp936 console or pipe. User-maintained UTF-8 files (config, ledger, state files, `package.json`) may carry a BOM; generated files are UTF-8 without BOM, LF.
- Generated commands use the `{{PYTHON}}` placeholder: `python` on Windows, `python3` elsewhere, or `apply_harness.py --python-command "py -3"` (any verified one-line command, recorded as `python_command` in `.harness/config.json`). The installer records commands, never runs them.
- Before installing a changed skill, run `python -m unittest discover -s "<SKILL_ROOT>/tests" -p "test_*.py"`. Keep backups of a replaced skill outside scanned skill directories; replacing the skill does not update harness files already installed in projects (see [migration-rules.md](references/migration-rules.md)).

## Route the request

- **Use (default in installed projects):** run the existing workflow, supply its inputs, change authorized run parameters, and deliver its output. No harness audit, rule promotion, plan/review ceremony, or maintenance self-check for an ordinary run. Record actual results at existing checkpoints.
- **Maintain:** a request to build, fix, or change the workflow, harness, rules, or acceptance mechanism authorizes only that requested change. Read the relevant maintenance guidance. Return to use on the next ordinary request; never persist a global developer-mode switch.
- Classify the requested action, not the person's identity or whether files/code are involved. A report correction is use; changing the report-generation procedure is maintenance. "Can this workflow be better?" is discussion, not authorization to modify it. If a run encounters a defect, finish unaffected authorized work and report the defect; repair the workflow only when authorized. An explicit "fix the workflow and run it" covers both.

Mode is task routing, not authentication or access control. Keep existing permissions. `minimal` / `governed` is a separate governance choice, defaulting to `minimal` in every domain.

## State contract

Read-only questions verify relevant sources without full checks or state/ledger writes unless new durable facts, a blocker, explicit re-verification, or an existing business requirement warrants them. State-only closeout edits do not invalidate a passed business check; rerun for relevant changed inputs, failures or new evidence. Before claiming completion, re-run on the final state every check whose inputs this change touched; an earlier pass does not stand in for it.

- `AGENTS.md` routes work; `INSTRUCTIONS.md` holds stable rules, the use contract, acceptance methods, and supported Learned Constraints.
- `PROGRESS.md` contains current facts with evidence, never proposed steps. `HANDOFF.md` is a whole-rewritten transfer packet (`progress_ref`, `just_finished`, `current_task`, `first_action`, `do_not`, `open_questions`, `verify`), read once and expired when work starts. It never overrides the current user request. Keep `just_finished` to one locating sentence and `progress_ref` to a section/evidence pointer; never copy the completed list, baseline results, backlog or history into handoff. Resume-critical questions/checks may be referenced, not retold.
- Writing rules for human-facing text (readable IDs, Chinese sentence style, the plan walkthrough) come from the separate `readable-docs` skill (its `install` mode), not from this skill; a harness install may point the user there.
- Current authoritative source/artifact checks (Git/tests where applicable) > `PROGRESS.md` > `HANDOFF.md` > chat recollection for factual state. For read-only questions, resolve from authoritative sources without repairing a stale bookmark; query history only if those sources cannot resolve the relevant conflict. This does not override user intent or permissions.
- History stays off-prompt in `.harness/history/log.jsonl`, through `scripts/harness_log.py` only (`show --seq <N>`, or `--id` when entries carry ids, prints one entry). Retrieve on the four declared triggers, never wholesale at startup.
- External writes (anything that changes an external system: submit, send, publish, order, call a write API) are two-phase in the ledger: `append --type intent` with the operation id or idempotency key as evidence before the action, then a `milestone` or `incident` appended with `--closes <seq>` after it. `scripts/harness_log.py pending` lists the intents still open (exit 1 while any remain); it runs before writes and on takeover, and an open intent is verified against the external system or artifact before anything is redone. `INSTRUCTIONS.md` Use Contract names the project's external writes and how to verify each.
- Pre-resume gate: on takeover or resume, an expensive, irreversible or `do_not`-named action is shown to the user with its cost and waits for confirmation; `do_not` is lifted only by the user, never because the previous process is gone or time has passed. `HANDOFF.md` writes such gates unconditionally and without time qualifiers, `first_action` is never such an action, and `PROGRESS.md` In Progress names the job and log location of a long-running task so a takeover can check whether it still runs. The hooks component's `gated_actions` is the enforced form.
- `INSTRUCTIONS.md` carries a Context Budget for the working layer: outline a file before reading it (`scripts/harness_read.py`) and read only line ranges past the budget; redirect output of uncertain length to the scratch directory and read its head; count before fetching detail; subagents return conclusions with locations, not source text. The numbers live in `.harness/config.json` `context_budget`; `scripts/check-startup-doc-budget.py` gates each startup file, the four files' total and the shape of `PROGRESS.md`.
- Rule promotion is maintenance, not routine closeout. Use observed behavior, a narrow applicability condition, evidence, and a retirement condition; unsupported or confounded ideas may stay unpromoted. Explicit user constraints and verified facts retain their own authority. Repeated step sequences are promoted the same way (procedure promotion in the maintenance guide): deterministic ones become a project script declared in the Use Contract, judgment-laden ones a Learned Constraint pointing at a procedure document; never during use.

## Workflow for harness creation or maintenance

1. Read existing instruction chains, actual source materials, workflow entrypoints and acceptance evidence. Inspect `git status --short --branch` in Git projects before maintenance writes; preserve user changes. Confirm the baseline too (see Boundaries).
2. Default to `minimal`. Use `governed` for established review-gated, safety-sensitive, or explicitly formal work. Read [profiles.md](references/profiles.md) when choosing/extending profiles and [migration-rules.md](references/migration-rules.md) before changing an installed harness.
3. Identify the use contract: entrypoint, inputs/adjustable parameters, outputs, acceptance evidence, and side-effect boundary. Reuse existing paths. Read [project-types.md](references/project-types.md) when domain adaptation is needed; do not invent `src/`, tests, CI, or a new directory layout.
4. Audit and preview; these do not write:

   ```sh
   python "<SKILL_ROOT>/scripts/audit_harness.py" --target <project> --profile minimal
   python "<SKILL_ROOT>/scripts/apply_harness.py" --target <project> --profile minimal --project-name <name> --objective <objective>
   ```

   Optional `--project-type <description>`, `--workflow-entry <existing-entry>`, `--scratch-dir <dir>` (where output of uncertain length goes; default `.harness/tmp`), repeatable `--verification-command <command>` and `--acceptance-check <observable-check>` capture domain evidence. Manual checks are first-class; a missing executable test is not a defect in a non-software project. These arguments declare checks; they do not execute them or claim success. Add `--task-cards` (with optional `--task-cards-dir`) or `--hooks` only on request; see [Optional component: task cards](#optional-component-task-cards) and [Optional component: hooks](#optional-component-hooks).
5. Show findings and intended files. A clear request to create or retrofit already authorizes that scope; otherwise obtain approval before writing. Apply with the same options plus `--apply`. Never overwrite existing files. Dirty Git apply still requires an overlap review and explicit authorization for `--allow-dirty`.
6. Replace placeholders from project evidence; inspect the generated files. Existing files require a narrow manual merge, not reinstallation: the preview's `manual_merge` names what each skipped root file lacks and, for an existing `AGENTS.md`, prints a paste-ready section (`assets/fragments/agents-merge-section.md`, rendered for Git or non-Git). Without that merge the new state files are unreachable and validation fails. Update any checksum manifest it names in the same step. Ordinary users should receive their result, not instructions on maintaining the harness.
7. For substantive rule/workflow changes, use [behavioral-validation.md](references/behavioral-validation.md): state the hypothesis, inspect old/new behavior in representative isolated cases (the cold-takeover and interrupted-takeover cases included), and retain failures. This is a maintenance check, not a gate on everyday tasks. Read the generated [maintenance guide template](assets/minimal/docs/harness-maintenance.md.tmpl) for lesson promotion.
8. Run structural validation and the actual domain acceptance checks. Report the two separately. Outside Git the validator asks for a recoverable version instead of `git status` and a commit policy; an install with no declared acceptance fails until it is calibrated:

   ```sh
   python "<SKILL_ROOT>/scripts/validate_harness.py" --target <project> --profile auto --min-score 90
   python <project>/scripts/check-project-harness.py --root <project> --profile auto
   python <project>/scripts/check-startup-doc-budget.py --root <project>
   ```

9. Update factual progress and handoff, append a maintenance milestone, and follow the project's existing commit policy if it uses Git (otherwise record a recoverable version). Report observed evidence and remaining limits; structural scores never prove agent behavior or task correctness.

## Optional component: task cards

Off by default; the installer never adds a feature tracker on its own. Use it when the user asks for requirement-to-small-cards work, one card at a time, with a person verifying on the real target (agent implements, human accepts):

```sh
python "<SKILL_ROOT>/scripts/apply_harness.py" --target <project> --profile minimal --task-cards [--task-cards-dir docs/tasks] [--apply]
```

- Installs only missing files: `<dir>/index.md` (card list; at most one card in progress) and `<dir>/task-card-template.md` (the template authorizes nothing). Writes `task_cards` into `.harness/config.json` and renders a `## Task Cards` section in `AGENTS.md`; without the flag neither appears.
- Card states: draft, approved, in progress, pending acceptance, done, failed, blocked (Chinese values in the template). Each acceptance item is `script` or `human`; the agent may mark `script` items executed with evidence, only a person may mark a `human` item passed or failed. A card with a human item awaiting acceptance stays "待验收", and is done only when every item passed.
- The target project's `scripts/check-project-harness.py` lints card states, the in-progress limit, and required recorder/evidence fields. This checks consistency only and cannot prove a recorded result is genuine; the optional hooks below stop the agent's own edits from recording one, and anything stronger rests on the target project's permissions.
- Already-installed harness: re-run apply with `--task-cards`; see [migration-rules.md](references/migration-rules.md) for the manual merges.
- `validate_harness.py` checks the index and template only when `task_cards` is configured.

## Optional component: hooks

Off by default. Use it when the user wants the harness rules enforced in Claude Code rather than only written down. A hook that passes prints nothing and costs no tokens; a broken rule blocks the tool call or the end of the turn with at most three stderr lines saying why and what to do instead:

```sh
python "<SKILL_ROOT>/scripts/apply_harness.py" --target <project> --profile minimal --hooks [--task-cards] [--apply]
```

- Installs only missing files: `scripts/harness_hook.py` (one standard-library file) and `.claude/settings.json`. An existing `.claude/settings.json` is never touched; the preview's `manual_merge` prints the `hooks` block to paste. Writes `"hooks": {"enabled": true}` into `.harness/config.json` (`false` turns every rule off). Handlers are exec form (`python` + `${CLAUDE_PROJECT_DIR}/scripts/harness_hook.py`, no shell), so they run alike under Git Bash, PowerShell or cmd and from any working directory.
- Matchers stay narrow: `Edit|Write|MultiEdit`, `Bash|PowerShell` and `Stop`; nothing else starts Python. Rules: no direct write to `.harness/history/log.jsonl` (file tools, or a redirect, `tee`, `sed -i`, `cp`/`mv`/`rm`, `Set-Content`/`Add-Content`/`Out-File`, an inline `open(..., "a")`); with task cards configured, no agent-recorded 已通过/未通过 or 记录人 on a `human` acceptance item (an item that was `human` stays `human` for this check); at Stop, `check-project-harness.py`, `check-startup-doc-budget.py --strict` and `harness_log.py pending` must pass, once per stop (`stop_hook_active`). All three pass on an untouched install, so enable hooks on an existing project only after they pass there, or read-only sessions get blocked too.
- Optional, inactive unless declared: `"hooks": {"enabled": true, "external_writes": ["<command fragment>", ...]}` makes a matching `Bash`/`PowerShell` command wait for an open `intent` as the ledger's last entry. Also optional: a `PostToolUse` `Bash|PowerShell` entry with the same handler re-runs the task-card lint after a command that names the card directory (detection after the fact, not a block).
- Also optional: `"gated_actions": ["<command fragment>", ...]` in the same block makes a matching `Bash`/`PowerShell` command ask the user first (`permissionDecision: ask` with the reason); a headless run or a mode that cannot prompt denies it, which is the intended fail-safe. List the project's expensive or irreversible commands there: it is the enforced form of the pre-resume gate.
- Other CLIs have no such hooks: with `--hooks` in a Git project the preview prints a short `.git/hooks/pre-commit` (`harness_hook.py --git-pre-commit`: the project check, the strict budget check and an append-only ledger diff) for the user to install; the installer never writes into `.git`.
- Limits: hooks see only the agent's own tool calls and cannot prove that a person wrote a result. A script file or an obfuscated shell command can still change a card or the ledger unseen, and an agent can edit the hook settings themselves. Stronger guarantees need file-system permissions or the business system, outside this skill.
- Already-installed harness: re-run apply with `--hooks`; see [migration-rules.md](references/migration-rules.md). `validate_harness.py` checks the script and its settings entry only when `hooks` is configured.

## Boundaries

- Baseline first: before writing or modifying, confirm the project's baseline (native build/test commands, or the declared `acceptance_checks` for non-software work). A baseline that already fails is recorded with its impact and never reported as a regression of this change. Read-only queries skip this.
- Scope ambiguity: choose the conservative, reversible reading, record the assumption in the state files, and keep working. Pause the request only for destructive or irreversible actions or clear expansion beyond the request.
- Definition of Done (the generated `AGENTS.md` carries it as its own section): the deliverable exists; relevant verification actually ran with recorded evidence (a structural score does not count, and a human-acceptance item stays "待验收" until a person records the result); `PROGRESS.md`, `HANDOFF.md` and the ledger are current; no unrelated changes; and a recoverable boundary exists (project commit policy in Git projects, a recorded version otherwise).
- Preserve the direct-execute path. Maintenance also permits small clearly authorized edits without new plans, review rounds, or confirmations. Never introduce broader gates from a single failure or reviewer preference. Any justified stronger gate has scope and an exit condition.
- Keep one instruction authority, normally `AGENTS.md`. Claude Code auto-loads `CLAUDE.md`, not `AGENTS.md`, so the installer adds a one-line `CLAUDE.md` whose only content is the `@AGENTS.md` pointer when that file is missing, and the preview prints the line for an existing `CLAUDE.md` that lacks it; a CLI with another entry file (`GEMINI.md`) gets the same one line by hand. Do not duplicate policy in those files. Long evidence and domain procedures stay behind existing indexes. No mandatory new ledger fields or per-run improvement records.
- Optimization intake, PRDs/specs, and proposed plans do not themselves authorize implementation. User goals/non-goals remain user-owned; do not ratify or rewrite them silently.
- Plan walkthrough gate (governed lifecycle): when the review verdict is approve and the next step is activation, the agent asks the user whether to hear a walkthrough first, with the plan's summary and its pending decisions in the question. If the user says yes, the agent walks them through chunk by chunk under the `readable-docs` plan-walkthrough rules (a version revised after agent-to-agent review covers what changed and which findings were taken or declined). The user may skip it and approve directly, or only answer the pending decisions. Until the user answers, review verdicts and agent consensus are not decisions, and the revised plan is neither committed nor activated; no answer is not a skip. A user who asks for a walkthrough of any plan gets one at any time. The question and the walkthrough are the review before approval, not an extra round after it: one reply may still grant review confirmation and activation together.
- Keep domain constraints local. Only promote a project lesson to this generic skill when its mechanism applies elsewhere and cross-domain checks support it. Do not copy credentials, private records, or domain-specific policies into the skill.
- Never move, rename, delete, or archive unrelated project files. Preserve existing environments. A use/maintain route does not grant additional tool permissions or external-write authority.

## Resources

- `scripts/audit_harness.py`: read-only inventory.
- `scripts/apply_harness.py`: deterministic preview and missing-file installation; `--python-command` sets the interpreter written into generated commands.
- `scripts/validate_harness.py`: structural scoring only.
- `scripts/harness_portability.py`: UTF-8 output, BOM-tolerant reads and the interpreter default shared by the scripts above.
- `scripts/harness_common.py`: target and path safety plus the audit report; re-exports the names of the two modules below.
- `scripts/harness_templates.py`: template locations, placeholder replacements and rendering (including the `assets/fragments/` tokens).
- `scripts/harness_project.py`: repository state and verification-command detection for a target project.
- `scripts/harness_merge.py`: read-only hand-merge hints for skipped root files, used by the apply preview.
- `scripts/harness_checks.py`: check primitives and the five base validation categories used by `validate_harness.py`.
- `scripts/harness_checks_optional.py`: the optional governance, task-card and hooks validation categories.
- `assets/minimal/` and `assets/governed/`: generated output, load only relevant templates.
- `assets/fragments/`: template fragments rendered into generated files (the task-card lint source, `context-budget-section.md`) or into the apply preview's merge hints (`agents-merge-section.md`, the same Context Budget section); never installed on their own.
- `assets/task-cards/`: opt-in task-card index/template and the `AGENTS.md` section fragment; used only with `--task-cards`.
- `assets/hooks/`: opt-in hook script, `.claude/settings.json` template and the printed-only Git pre-commit sample; used only with `--hooks`.
- `tests/`: skill-development regressions (unittest; shared helpers in `tests/harness_test_support.py`), passing under the platform's default encoding; never installed into target projects.
