---
name: project-harness-engineer
description: Audit, create, and incrementally retrofit repository-level coding-agent harnesses with startup instructions, durable progress and handoff state, verification commands, scope boundaries, and optional governed plan/review/decision/optimization lifecycles. Use when a user asks to add or improve harness engineering, AGENTS.md/INSTRUCTIONS.md/PROGRESS.md/HANDOFF.md, restartable agent workflows, exec-plan gates, or to make another project follow the same coding-governance model as an existing repository. Not for directory-structure design or general file tidying/reorganization ("整理项目"/"新建项目" scaffolding) — those belong to the project-scaffolder skill; this skill never moves or renames existing project files.
---

# Project Harness Engineer

Build a small, project-local control plane that lets coding agents start safely, stay in scope, verify work, and hand off without relying on chat history.

Resolve the directory containing this `SKILL.md` as `SKILL_ROOT` before invoking bundled scripts. Do not assume the target repository contains the Skill scripts.

## State Contract

The installed harness follows one closed-loop state model. Every generated or migrated file must respect these roles:

- `AGENTS.md` + `INSTRUCTIONS.md` are the stable rule layer; `INSTRUCTIONS.md` Learned Constraints absorbs distilled long-term lessons.
- `PROGRESS.md` holds only facts that are already true, with evidence. Session intent is never written there.
- `HANDOFF.md` is a fixed-field transfer packet (`progress_ref`, `just_finished`, `current_task`, `first_action`, `do_not`, `open_questions`, `verify`), rewritten whole, read once at startup, expired once work starts.
- `.harness/history/log.jsonl` is the off-prompt event ledger, accessed only through `scripts/harness_log.py` (`append` at checkpoints, `query` on the four retrieval triggers in `AGENTS.md`). Startup never loads it.
- Conflict precedence: git/tests > `PROGRESS.md` > `HANDOFF.md` > chat memory.
- The loop closes through distillation: durable lessons found in the ledger are promoted into `INSTRUCTIONS.md` Learned Constraints so later sessions start smarter.

## Workflow

1. Read the target repository's existing instruction chain and manifests before proposing changes.
2. Inspect `git status --short --branch` when the target is a Git repository. Preserve all unrelated and user-owned changes.
3. Choose a profile. Default to `minimal`:
   - Use `minimal` unless the evidence clearly demands more. It covers startup, state, verification, scope, and handoff, plus a task-triage fast path.
   - Use `governed` only for multi-session review-gated work, safety-sensitive scope, or when the user explicitly asks for IB-style coding governance (e.g. reproducing the `ib-agent-trading-sys` harness). Over-governing a small project stalls its coding loop.
4. Run the read-only audit first:

   ```powershell
   python "<SKILL_ROOT>/scripts/audit_harness.py" --target <repo> --profile <minimal|governed>
   ```

5. Present the audit findings, selected profile, inferred verification commands, and every proposed file. Obtain explicit approval before target-project writes unless the user's request already clearly authorizes the retrofit.
6. Preview installation. Preview is the default and writes nothing:

   ```powershell
   python "<SKILL_ROOT>/scripts/apply_harness.py" --target <repo> --profile <minimal|governed> --project-name <name> --objective <objective>
   ```

7. Apply only after approval:

   ```powershell
   python "<SKILL_ROOT>/scripts/apply_harness.py" --target <repo> --profile <minimal|governed> --project-name <name> --objective <objective> --apply
   ```

   Never overwrite an existing file. The installer skips existing files and reports manual-merge work. On a dirty Git worktree it fails closed unless the user explicitly authorizes `--allow-dirty` after the overlapping paths are inspected.
8. Replace generic generated facts with evidence from the target repository. Do not invent objectives, completed work, test commands, decisions, or active plans.
9. Validate the harness and then run the target project's native checks:

   ```powershell
   python "<SKILL_ROOT>/scripts/validate_harness.py" --target <repo> --profile auto --min-score 90
   python <repo>/scripts/check-project-harness.py --root <repo> --profile auto
   ```

10. Update the target `PROGRESS.md` and `HANDOFF.md`, append an install `milestone` via `python <repo>/scripts/harness_log.py append`, stage only intended paths, and follow the target repository's commit policy.

## Non-Negotiable Boundaries

- Keep the task-triage fast path intact. The installed harness must let small, clearly requested work execute directly — no plan files, no review round-trips, no extra confirmations. Never tighten the installed harness's gates beyond the templates on your own initiative. A project constraint backed by an explicit user requirement or a stated risk may go further, but it must record its scope and its exit condition; do not let a single fix or a reviewer's preference harden into a standing gate. This ceiling also applies inside the governed tier: a proposed plan carrying field-level contracts with no named verification command, or a review loop with no declared round cap, is over-governance even when task triage is correct. If the existing harness forces every task through plan/review ceremony, flag that as a defect to fix.
- Keep one authoritative instruction entry. Prefer `AGENTS.md`; do not create a second full policy copy in `CLAUDE.md`.
- Treat `HANDOFF.md` as the fixed-field transfer packet and `PROGRESS.md` as the facts-only status surface with ledger pointers; never blur the facts-versus-intent split.
- Keep event history in the ledger and detailed manuals, long-form evidence, and domain rules behind indexed docs rather than expanding startup files. Execution agents read the ledger only through `harness_log.py query` on the declared triggers.
- Do not reorganize, rename, delete, or archive unrelated project files as part of harness installation. Directory layout and file reorganization requests belong to the `project-scaffolder` skill.
- Do not promote an optimization record or proposed plan into execution authority automatically.
- Do not promote a PRD or a spec entry into execution authority automatically. A PRD is intent authority: `Accepted` lets it serve as a proposed plan's source evidence, never as permission to implement. Its goals and non-goals belong to the user — draft them, but do not rewrite or ratify them on your own.
- Do not copy broker, credential, trading, or other domain-specific rules into the generic harness. Add such rules only as a target-project overlay backed by that project's requirements.
- Do not claim the harness is effective solely because structural validation passes. Run representative project verification and record evidence.

## Resources

- Read [profiles.md](references/profiles.md) when choosing or extending a profile.
- Read [migration-rules.md](references/migration-rules.md) before modifying an existing harness or resolving file conflicts.
- Use `scripts/audit_harness.py` for read-only inventory and risk reporting.
- Use `scripts/apply_harness.py` for deterministic preview and missing-file installation.
- Use `scripts/validate_harness.py` for structural scoring and critical-gate validation.
- Treat `assets/minimal/` and `assets/governed/` as output templates; never load all templates into context unless they need modification.
