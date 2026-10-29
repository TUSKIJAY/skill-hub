#!/usr/bin/env python3
"""Check primitives and the five base check categories of the harness validator."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from harness_portability import read_json_file, read_text_or_empty


def present(root: Path, relative: str) -> bool:
    return (root / relative).is_file()


def contains_all(text: str, groups: list[tuple[str, ...]]) -> bool:
    lowered = text.lower()
    return all(any(term.lower() in lowered for term in group) for group in groups)


def check(label: str, passed: bool, path: str, *, critical: bool = False) -> dict[str, Any]:
    return {"label": label, "passed": bool(passed), "path": path, "critical": critical}


def acceptance_declared(root: Path) -> bool:
    """A declaration only: do not confuse structure with an executed verification."""
    try:
        config = read_json_file(root / ".harness/config.json")
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return False
    if not isinstance(config, dict):
        return False
    return any(
        isinstance(config.get(key), list)
        and any(isinstance(item, str) and item.strip() for item in config[key])
        for key in ("verification_commands", "acceptance_checks")
    )


def task_cards_state(root: Path) -> tuple[bool, str | None]:
    """(enabled, directory): enabled when config carries `task_cards`; directory is None when unsafe."""
    try:
        config = read_json_file(root / ".harness/config.json")
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return False, None
    spec = config.get("task_cards") if isinstance(config, dict) else None
    if spec is None:
        return False, None
    directory = spec.get("dir") if isinstance(spec, dict) else None
    if isinstance(directory, str) and directory.strip():
        resolved_root = root.resolve()
        base = (resolved_root / directory).resolve()
        if base == resolved_root or resolved_root in base.parents:
            return True, directory.strip().strip("/")
    return True, None


# Words that declare a recoverable version where Git commits are not available.
RECOVERABLE = ("可恢复", "recoverable", "备份", "backup")
# Words of the pointer to the Context Budget in AGENTS.md; the INSTRUCTIONS.md section itself is found by heading.
CONTEXT_BUDGET_TERMS = [("context budget", "上下文预算")]
CONTEXT_BUDGET_TITLES = ("context budget", "上下文预算")
# The command text of the two-phase external-write rule in AGENTS.md ("意图" alone also names handoff intent).
INTENT_TERMS = [("--type intent",)]
# The Hard Rules bullet that gates expensive, irreversible or do_not-named actions on resume.
GATE_TERMS = [("恢复前闸门",)]
# The roadmap Lifecycle step that offers the user a walkthrough after an approve verdict and before activation.
WALKTHROUGH_TERMS = [("人类讲解评审",)]


def has_context_budget_section(text: str) -> bool:
    """A `## ` heading whose title starts with Context Budget (or 上下文预算); a mention elsewhere does not count."""
    return any(line.startswith("## ") and line[3:].strip().lower().startswith(CONTEXT_BUDGET_TITLES)
               for line in text.splitlines())


def agents_requirements(is_git: bool) -> dict[str, dict[str, Any]]:
    """What AGENTS.md itself must cover, keyed for the checks below and for the merge hints.

    `scored` items feed the validator. The others are hard rules (baseline, scope assumptions, Definition
    of Done, use/maintain routing), the Context Budget pointer, and wording the validator reads across
    several files; the apply preview still asks an existing AGENTS.md to carry them, because the merged
    section is the only harness text such a project gets. Outside Git there is no `git status`; a
    recoverable version replaces the commit.
    """
    requirements = [
        ("routes", "Startup contract routes all four root state files",
         [("startup", "启动"), ("instructions.md",), ("progress.md",), ("handoff.md",)], True, True),
        ("precedence", "Conflict precedence chain is declared", [("优先级", "precedence")], False, True),
        ("ledger", "Ledger discipline is declared", [("harness_log",)], False, True),
        ("unrelated", "Unrelated user changes are protected",
         [("unrelated", "无关"), ("preserve", "保留", "不得覆盖")], True, True),
        ("triage", "Task triage fast path lets small work execute directly",
         [("triage", "分级"), ("direct", "直接执行", "fast path")], False, True),
    ]
    if is_git:
        requirements += [
            ("git_status", "Git status is part of startup", [("git status",)], False, True),
            ("completion", "Completion and commit policy is explicit",
             [("commit", "提交"), ("complete", "完成")], False, True),
        ]
    else:
        requirements.append(("completion", "Completion and recoverable-version policy is explicit (non-Git)",
                             [RECOVERABLE, ("complete", "完成")], False, True))
    requirements += [
        ("baseline", "Baseline is confirmed before writes", [("基线", "baseline")], False, False),
        ("assumptions", "Scope ambiguity is resolved conservatively and recorded", [("假设", "assumption")],
         False, False),
        ("done", "Definition of Done is stated", [("definition of done", "完成标准")], False, False),
        ("maintain", "Use/maintain routing is stated", [("维护", "maintain")], False, False),
        ("scope", "Scope boundary is explicit", [("scope", "范围", "边界")], False, False),
        ("evidence", "Completion requires evidence", [("evidence", "证据"), ("verify", "验证")], False, False),
        ("history", "History stays in the ledger behind an index", [("index", "索引"), ("history", "历史")],
         False, False),
        ("context", "Reads and output follow the INSTRUCTIONS.md Context Budget", CONTEXT_BUDGET_TERMS,
         False, False),
        ("intent", "External writes are logged as an intent before and closed after", INTENT_TERMS, False, False),
        ("gate", "Expensive, irreversible or do_not-named actions wait for the user on resume", GATE_TERMS,
         False, False),
    ]
    return {key: {"label": label, "groups": groups, "critical": critical, "scored": scored}
            for key, label, groups, critical, scored in requirements}


def context_budget_warnings(root: Path, instructions: str) -> list[str]:
    """Unscored for now: installs made before the Context Budget existed must not lose points."""
    warnings: list[str] = []
    if present(root, "INSTRUCTIONS.md") and not has_context_budget_section(instructions):
        warnings.append("INSTRUCTIONS.md 缺 Context Budget 节；从模板或合并提示补上")
    if not present(root, "scripts/harness_read.py"):
        warnings.append("scripts/harness_read.py 缺失；重跑 apply_harness.py 补装（只补缺失文件）")
    return warnings


def intent_warnings(root: Path, agents: str) -> list[str]:
    """Unscored for now: installs made before two-phase external writes existed must not lose points."""
    warnings: list[str] = []
    if present(root, "AGENTS.md") and not contains_all(agents, INTENT_TERMS):
        warnings.append("AGENTS.md 缺外部写入两段记账规则（--type intent / pending）；从合并提示补上")
    if present(root, "scripts/harness_log.py") and "cmd_pending" not in read_text_or_empty(root / "scripts/harness_log.py"):
        warnings.append("scripts/harness_log.py 缺 intent 类型与 pending 子命令；按 migration-rules.md 手工合并或换用新模板")
    return warnings


def gate_warnings(root: Path, agents: str) -> list[str]:
    """Unscored for now: installs made before the pre-resume gate existed must not lose points."""
    if present(root, "AGENTS.md") and not contains_all(agents, GATE_TERMS):
        return ["AGENTS.md 缺恢复前闸门规则（昂贵/不可逆/do_not 点名的动作先问用户）；从合并提示补上"]
    return []


def walkthrough_warnings(root: Path) -> list[str]:
    """Unscored for now: installs made before the plan walkthrough gate existed must not lose points."""
    roadmap = "docs/exec-plans/roadmap.md"
    if present(root, roadmap) and not contains_all(read_text_or_empty(root / roadmap), WALKTHROUGH_TERMS):
        return ["docs/exec-plans/roadmap.md 缺人类讲解评审步骤（评审通过后、激活前先问用户要不要听讲解）；从合并提示补上"]
    return []


def entry_pointer_warnings(root: Path) -> list[str]:
    """Unscored: Claude Code auto-loads CLAUDE.md, not AGENTS.md, so a project used from Claude Code needs the pointer."""
    claude = root / "CLAUDE.md"
    if not claude.is_file():
        return ["CLAUDE.md 缺失；Claude Code 不会自动读 AGENTS.md，重跑 apply_harness.py 补装一行指针"]
    if "agents.md" not in read_text_or_empty(claude).lower():
        return ["CLAUDE.md 没有指向 AGENTS.md；追加合并提示里的一行指针，不要把规则复制进去"]
    return []


def agents_check(agents: str, requirement: dict[str, Any]) -> dict[str, Any]:
    return check(requirement["label"], contains_all(agents, requirement["groups"]), "AGENTS.md",
                 critical=requirement["critical"])


def instructions_checks(root: Path, agents: str, is_git: bool = True) -> list[dict[str, Any]]:
    """Startup contract in AGENTS.md."""
    required = agents_requirements(is_git)
    keys = ("routes", "git_status", "precedence", "ledger") if is_git else ("routes", "precedence", "ledger")
    return [check("AGENTS.md exists", present(root, "AGENTS.md"), "AGENTS.md", critical=True)] + [
        agents_check(agents, required[key]) for key in keys
    ]


def state_checks(root: Path, instructions: str, progress: str, handoff: str) -> list[dict[str, Any]]:
    """Presence and content of the INSTRUCTIONS/PROGRESS/HANDOFF state files."""
    return [
        check("INSTRUCTIONS.md exists", present(root, "INSTRUCTIONS.md"), "INSTRUCTIONS.md", critical=True),
        check("PROGRESS.md exists", present(root, "PROGRESS.md"), "PROGRESS.md", critical=True),
        check("HANDOFF.md exists", present(root, "HANDOFF.md"), "HANDOFF.md", critical=True),
        check(
            "Progress exposes facts and pending backlog",
            contains_all(progress, [("facts", "事实"), ("backlog", "待办")]),
            "PROGRESS.md",
        ),
        check(
            "Handoff carries a progress anchor",
            "progress_ref" in handoff.lower(),
            "HANDOFF.md",
            critical=True,
        ),
        check(
            "History ledger entry point exists",
            present(root, "scripts/harness_log.py"),
            "scripts/harness_log.py",
            critical=True,
        ),
        check(
            "Instructions reserve learned constraints",
            contains_all(instructions, [("learned constraints", "沉淀")]),
            "INSTRUCTIONS.md",
        ),
    ]


def verification_checks(root: Path, agents: str, progress: str, handoff: str) -> list[dict[str, Any]]:
    """Declared acceptance, checker scripts and the evidence requirement."""
    return [
        # Critical: an install whose acceptance was never declared is not calibrated yet.
        check(
            "Domain acceptance is declared (not proof it ran)",
            acceptance_declared(root),
            ".harness/config.json",
            critical=True,
        ),
        check(
            "Local structural checker exists",
            present(root, "scripts/check-project-harness.py"),
            "scripts/check-project-harness.py",
            critical=True,
        ),
        check(
            "Startup document budget checker exists",
            present(root, "scripts/check-startup-doc-budget.py"),
            "scripts/check-startup-doc-budget.py",
        ),
        check(
            "Completion requires evidence",
            contains_all(agents + progress + handoff, [("evidence", "证据"), ("verify", "验证")]),
            "AGENTS.md / PROGRESS.md / HANDOFF.md",
        ),
    ]


def scope_checks(agents: str, instructions: str, is_git: bool = True) -> list[dict[str, Any]]:
    """Protection of unrelated changes, scope boundary and the completion policy."""
    required = agents_requirements(is_git)
    return [
        agents_check(agents, required["unrelated"]),
        check(
            "Scope boundary is explicit",
            contains_all(agents + instructions, [("scope", "范围", "边界")]),
            "AGENTS.md / INSTRUCTIONS.md",
        ),
        agents_check(agents, required["completion"]),
    ]


def lifecycle_checks(agents: str, progress: str, handoff: str) -> list[dict[str, Any]]:
    """Task triage, progress outcomes and the handoff resume point."""
    return [
        agents_check(agents, agents_requirements(True)["triage"]),
        check(
            "Progress records lifecycle outcomes",
            contains_all(progress, [("in progress", "进行中"), ("blocked", "阻塞"), ("completed", "已完成")]),
            "PROGRESS.md",
        ),
        check(
            "Handoff records resume point and next gate",
            contains_all(handoff, [("current_task", "resume", "恢复"), ("first_action", "next gate", "下一闸门")]),
            "HANDOFF.md",
            critical=True,
        ),
        check(
            "Handoff stays separate from history",
            contains_all(agents + handoff, [("index", "索引"), ("history", "历史", "archive", "归档")]),
            "AGENTS.md / HANDOFF.md",
        ),
    ]
