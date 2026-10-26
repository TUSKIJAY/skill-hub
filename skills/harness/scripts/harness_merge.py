#!/usr/bin/env python3
"""Hand-merge hints for root harness files that already exist and are therefore skipped.

apply_harness.py never rewrites an existing file. When AGENTS.md, INSTRUCTIONS.md, PROGRESS.md or
HANDOFF.md already exists, this module names what the file still lacks and, for AGENTS.md and a missing
Context Budget, renders paste-ready text. It only reads files; preview stays write-free.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import json
import re

from harness_checks import acceptance_declared, agents_requirements, contains_all, has_context_budget_section
from harness_portability import read_json_file, read_text_or_empty
from harness_templates import (
    FRAGMENTS_ROOT,
    checked_context_budget,
    context_budget_json,
    context_budget_replacements,
    render_context_budget_section,
    render_template,
    render_text,
)

AGENTS_MERGE_FRAGMENT = FRAGMENTS_ROOT / "agents-merge-section.md"
# Mirrors the generated scripts/check-project-harness.py; a regression test keeps them equal.
PROGRESS_REQUIRED_HEADINGS = (
    "## Facts",
    "## In Progress",
    "## Blocked",
    "## Backlog",
    "## Open Unknowns",
    "## Verified Baseline",
    "## Completed",
)
HANDOFF_REQUIRED_KEYS = (
    "progress_ref:",
    "just_finished:",
    "current_task:",
    "first_action:",
    "do_not:",
    "open_questions:",
    "verify:",
)
CONTEXT_BUDGET_LABEL = "Context Budget section"
# The sentence that step 4 of the AGENTS.md template ends with, tokens unrendered; a regression test keeps
# them equal. It carries the short form of all four Context Budget rules, because AGENTS.md is the instruction
# authority every CLI reaches (directly, or through the one-line CLAUDE.md pointer). Rendered by
# agents_context_sentence(), it is the whole hint when an existing AGENTS.md lacks nothing else, and reads as
# well after a bullet.
AGENTS_CONTEXT_SENTENCE = ("读取和输出按 `INSTRUCTIONS.md` 的 Context Budget 执行：读文件先 `outline`（启动四件除外），"
                           "超预算只读行段；输出长短不确定先落盘再 `head`；"
                           "交给子代理时写明只回结论（不超过 {{CB_HEAD_LINES}} 行，每条带\"文件:行\"），不回原文。")
# The State Discipline bullet of the AGENTS.md template that carries the two-phase external-write rule, tokens
# unrendered; a regression test keeps template, fragment and this constant equal. Rendered by
# agents_intent_sentence(), it is the hint when an existing AGENTS.md lacks only this rule.
AGENTS_INTENT_SENTENCE = ('外部写入两段记账：会改变外部系统状态的操作（对外提交、发送、发布、下单、调用写接口），动手前先 `{{PYTHON}} scripts/harness_log.py append --type intent --summary "准备做 X" --evidence "<操作标识/幂等键/目标位置>"`，完成后用 `--closes <那条 seq>` 追加 `milestone`（成功，写回执）或 `incident`（失败或不确定）。写入前和接手时先跑 `{{PYTHON}} scripts/harness_log.py pending`，有未闭合意图先核实外部状态，核实前不得重做；能带幂等键的操作必须带。')
# The whole generated CLAUDE.md: Claude Code auto-loads CLAUDE.md, not AGENTS.md, so this one line (an
# @import) makes it read the same entry. A regression test keeps it equal to assets/minimal/CLAUDE.md.tmpl.
CLAUDE_POINTER_LINE = "本项目的指令入口是 @AGENTS.md，先读它；本文件不放其他规则。"
# The Hard Rules bullet of the AGENTS.md template that gates expensive, irreversible or do_not-named actions on
# resume; no tokens. A regression test keeps template, fragment and this constant equal.
AGENTS_GATE_SENTENCE = ('恢复前闸门：接手或续接时，昂贵（长时间运行、占用大量算力或配额）、不可逆、或 `HANDOFF.md` `do_not` 点名的动作，动手前必须向用户出示要做什么、预计成本、现有产物或状态为何不够，等用户确认后再做；不得因为「上次的任务已不在」「时间过去很久」或「状态文件过期」就自行解除 `do_not`，它只由用户解除。确认前只核实和报告，不启动后台进程、不建计划任务、不把状态改写成进行中。')
# Parts of the current scripts/harness_log.py, each found by a name the template defines.
LEDGER_SCRIPT_PARTS = (
    ("`intent` entry type, `--closes <seq>` on append and the `pending` subcommand (cmd_pending)", "cmd_pending"),
)
INSTRUCTIONS_REQUIREMENTS = (
    ("Learned Constraints section", [("learned constraints", "沉淀")]),
    ("acceptance / Verification section that the AGENTS.md section points to",
     [("verification", "验收", "验证")]),
)
# Parts of the current scripts/check-project-harness.py and scripts/check-startup-doc-budget.py, each found
# by a name the template defines.
PROJECT_CHECK_PARTS = (
    ("INSTRUCTIONS.md Context Budget numbers checked against .harness/config.json (lint_context_budget)",
     "lint_context_budget"),
    ("context_budget.scratch_dir must stay inside the project (scratch_dir_problem)", "scratch_dir_problem"),
    ("scripts/harness_read.py among the required files", "scripts/harness_read.py"),
    ("CLAUDE.md pointer lint (lint_entry_pointer)", "lint_entry_pointer"),
)
BUDGET_SCRIPT_PARTS = (
    ("PROGRESS.md shape limits (progress_shape)", "progress_shape"),
    ("four-file total (total_budget)", "total_budget"),
    ("thresholds read from .harness/config.json startup_budget", "startup_budget"),
    ("printed actions (动作：)", "动作："),
)
MANIFEST_PREFIXES = ("manifest", "sha256sums", "sha1sums", "md5sums", "checksums")
MANIFEST_SUFFIXES = (".sha256", ".sha1", ".md5")
# A checksum line: a 32-128 digit hex digest, whitespace, then a path (sha256sum / md5sum style).
CHECKSUM_LINE = re.compile(r"^\s*[0-9a-fA-F]{32,128}\s+\*?\S", re.M)


def agents_context_sentence(context_budget: dict[str, object] | None = None) -> str:
    """AGENTS_CONTEXT_SENTENCE with the installed numbers (defaults where the config has none)."""
    return render_text(AGENTS_CONTEXT_SENTENCE, context_budget_replacements(checked_context_budget(context_budget)))


def agents_intent_sentence(python_command: str) -> str:
    """AGENTS_INTENT_SENTENCE with the project's interpreter."""
    return render_text(AGENTS_INTENT_SENTENCE, {"{{PYTHON}}": python_command})


def render_agents_section(is_git: bool, python_command: str,
                          context_budget: dict[str, object] | None = None) -> str:
    replacements = {
        **context_budget_replacements(checked_context_budget(context_budget)),
        "{{PYTHON}}": python_command,
        "{{GIT_RULE}}": "Git 项目写入前先运行 `git status --short --branch`。" if is_git else "",
        "{{RECOVERY_RULE}}": (
            "按项目提交策略只暂存本次的文件并提交，形成可恢复的边界。" if is_git
            else "本目录不是 Git：在 `PROGRESS.md` 记下可恢复的版本，例如备份位置或哈希清单的哈希。"
        ),
    }
    return render_template(AGENTS_MERGE_FRAGMENT, replacements)


def installed_config(target: Path) -> dict[str, Any] | None:
    try:
        config = read_json_file(target / ".harness/config.json")
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return config if isinstance(config, dict) else None


# Detection looks at the first lines only; listing streams the file, so a huge manifest is never loaded whole.
MANIFEST_SNIFF_LINES = 200


def manifest_encoding(path: Path) -> str:
    """PowerShell writes UTF-16 with a BOM; everything else is read as UTF-8."""
    with path.open("rb") as handle:
        head = handle.read(2)
    return "utf-16" if head in (b"\xff\xfe", b"\xfe\xff") else "utf-8-sig"


def checksum_manifests(target: Path) -> list[Path]:
    """Root files that record file checksums (MANIFEST.sha256, SHA256SUMS, ...).

    The name only nominates a file; it counts when its first lines hold checksum lines, so a web-app
    manifest.json or a packaging MANIFEST.in is not reported.
    """
    found = []
    for path in sorted(target.iterdir()):
        name = path.name.lower()
        if path.is_symlink() or not path.is_file():
            continue
        if not (name.startswith(MANIFEST_PREFIXES) or name.endswith(MANIFEST_SUFFIXES)):
            continue
        try:
            with path.open(encoding=manifest_encoding(path), errors="replace") as handle:
                for number, line in enumerate(handle):
                    if CHECKSUM_LINE.match(line):
                        found.append(path)
                        break
                    if number >= MANIFEST_SNIFF_LINES:
                        break
        except OSError:
            continue
    return found


def manifest_lists(path: Path, names: set[str]) -> list[str]:
    """Which of `names` the manifest mentions (case-insensitive), read line by line."""
    wanted = {name.lower(): name for name in names}
    hits: set[str] = set()
    try:
        with path.open(encoding=manifest_encoding(path), errors="replace") as handle:
            for line in handle:
                lowered = line.lower()
                hits.update(original for key, original in wanted.items() if key in lowered)
                if len(hits) == len(wanted):
                    break
    except OSError:
        return []
    return sorted(hits)


def core_manual_merge(target: Path, plan: list[dict[str, str]], is_git: bool,
                      python_command: str, context_budget: dict[str, object] | None = None) -> list[dict[str, Any]]:
    """One hint per skipped root state file that lacks what the harness needs; empty when nothing to merge."""
    skipped = {item["path"] for item in plan if item["status"] == "skip-existing"}
    hints: list[dict[str, Any]] = []
    budget = checked_context_budget(context_budget)
    requirements = agents_requirements(is_git)
    # Rules an existing AGENTS.md takes as one sentence each, with where that sentence goes.
    sentence_hints = {
        requirements["context"]["label"]: (
            agents_context_sentence(budget),
            "the startup step that says what to read (step 4 in the template, or the 启动 bullet of a merged "
            "harness section)"),
        requirements["intent"]["label"]: (
            agents_intent_sentence(python_command),
            "State Discipline as its own bullet (or the merged harness section)"),
        requirements["gate"]["label"]: (
            AGENTS_GATE_SENTENCE,
            "Hard Rules as its own bullet (or the merged harness section)"),
    }

    def text(relative: str) -> str:
        return read_text_or_empty(target / relative)

    if "AGENTS.md" in skipped:
        agents = text("AGENTS.md")
        missing = [req["label"] for req in requirements.values()
                   if not contains_all(agents, req["groups"])]  # scored and hard-rule items alike
        if missing and all(label in sentence_hints for label in missing):
            # Everything else is already there: one sentence per gap, not a second copy of the harness section.
            placements = [f"the sentence for '{label}' to {sentence_hints[label][1]}" for label in missing]
            hints.append({
                "path": "AGENTS.md", "kind": "state",
                "missing": missing,
                "snippet": "".join(sentence_hints[label][0] + "\n" for label in missing),
                "note": "Append " + "; ".join(placements) + "; keep the rest of AGENTS.md as it is.",
            })
        elif missing:
            hints.append({
                "path": "AGENTS.md", "kind": "state",
                "missing": missing,
                "snippet": render_agents_section(is_git, python_command, budget),
                "note": "Append the snippet as its own section; keep the project's existing rules above it.",
            })
    if "INSTRUCTIONS.md" in skipped:
        instructions = text("INSTRUCTIONS.md")
        missing = [label for label, groups in INSTRUCTIONS_REQUIREMENTS if not contains_all(instructions, groups)]
        if not has_context_budget_section(instructions):
            missing.append(CONTEXT_BUDGET_LABEL)
        if missing:
            snippet = None
            note = "Add the missing sections from assets/minimal/INSTRUCTIONS.md.tmpl; keep existing rules."
            if CONTEXT_BUDGET_LABEL in missing:
                snippet = render_context_budget_section(python_command, budget) + "\n"
                note = ("Paste the Context Budget section after AI Behavior Rules. Its numbers come from "
                        ".harness/config.json context_budget (defaults where the config has none); where the project "
                        "already has stricter numbers or reading rules, keep them and write the same numbers into the "
                        "config. " + ("Add the other missing sections from assets/minimal/INSTRUCTIONS.md.tmpl; "
                                      if len(missing) > 1 else "") + "Keep existing rules.")
            hints.append({
                "path": "INSTRUCTIONS.md", "kind": "state",
                "missing": missing,
                "snippet": snippet,
                "note": note,
            })
    for relative, required in (("PROGRESS.md", PROGRESS_REQUIRED_HEADINGS), ("HANDOFF.md", HANDOFF_REQUIRED_KEYS)):
        if relative in skipped:
            existing = text(relative)
            missing = [item for item in required if item not in existing]
            if relative == "PROGRESS.md" and "harness_log.py" not in existing:
                missing.append("pointer to scripts/harness_log.py for history reads")
            if missing:
                hints.append({
                    "path": relative, "kind": "state",
                    "missing": missing,
                    "snippet": None,
                    "note": "scripts/check-project-harness.py fails until these exist; add them without renaming "
                            "or deleting the project's own sections.",
                })
    # An older project check keeps passing an AGENTS.md that does not route to the state files, and never
    # compares the Context Budget numbers with the config.
    project_check = text("scripts/check-project-harness.py")
    if "scripts/check-project-harness.py" in skipped and project_check:
        missing = []
        if (any(hint["path"] == "AGENTS.md" and not set(hint["missing"]) <= set(sentence_hints) for hint in hints)
                and "AGENTS_REQUIRED_ROUTES" not in project_check):
            missing.append("AGENTS.md routing lint (AGENTS_REQUIRED_ROUTES)")
        missing += [label for label, marker in PROJECT_CHECK_PARTS if marker not in project_check]
        if missing:
            hints.append({
                "path": "scripts/check-project-harness.py", "kind": "state",
                "missing": missing,
                "snippet": None,
                "note": "Merge the listed parts from assets/minimal/scripts/check-project-harness.py.tmpl into the "
                        "project's script and keep the project's own checks; until then the project check never "
                        "looks at them.",
            })
    if "CLAUDE.md" in skipped and "agents.md" not in text("CLAUDE.md").lower():
        hints.append({
            "path": "CLAUDE.md", "kind": "state",
            "missing": ["one-line pointer to AGENTS.md (@AGENTS.md import)"],
            "snippet": CLAUDE_POINTER_LINE + "\n",
            "note": "Append this line so Claude Code, which auto-loads CLAUDE.md and not AGENTS.md, reads the same "
                    "entry; keep the file's own content and copy no harness rules into it.",
        })
    ledger_script = text("scripts/harness_log.py")
    if "scripts/harness_log.py" in skipped and ledger_script:
        missing = [label for label, marker in LEDGER_SCRIPT_PARTS if marker not in ledger_script]
        if missing:
            hints.append({
                "path": "scripts/harness_log.py", "kind": "state",
                "missing": missing,
                "snippet": None,
                "note": "If the project never changed this script, replace it with "
                        "assets/minimal/scripts/harness_log.py.tmpl (it has no tokens); otherwise merge the listed parts "
                        "by hand (references/migration-rules.md). Existing entries and ids stay; until then open intents "
                        "cannot be listed.",
            })
    if ".harness/config.json" in skipped:
        config = installed_config(target)
        missing = [] if acceptance_declared(target) else ["acceptance_checks or verification_commands"]
        notes = ["Declare the project's real acceptance checks; validation fails until at least one exists."] if missing else []
        snippet = None
        if config is not None and "context_budget" not in config:
            missing.append("context_budget block (read by scripts/harness_read.py)")
            snippet = f'"context_budget": {context_budget_json(budget, indent="")}\n'
            notes.append("Add the context_budget key to the top-level object (mind the comma); keep its numbers "
                         "equal to the INSTRUCTIONS.md Context Budget section.")
        if missing:
            hints.append({
                "path": ".harness/config.json", "kind": "state",
                "missing": missing,
                "snippet": snippet,
                "note": " ".join(notes),
            })
    if "scripts/check-startup-doc-budget.py" in skipped:
        script = text("scripts/check-startup-doc-budget.py")
        missing = [label for label, marker in BUDGET_SCRIPT_PARTS if marker not in script]
        if script and missing:
            hints.append({
                "path": "scripts/check-startup-doc-budget.py", "kind": "state",
                "missing": missing,
                "snippet": None,
                "note": "If the project never changed this script, replace it with "
                        "assets/minimal/scripts/check-startup-doc-budget.py.tmpl (write the project's interpreter as a "
                        "JSON string where it says {{PYTHON_JSON}}); otherwise merge the listed parts by hand and keep "
                        "the project's own numbers (references/migration-rules.md, Adding The Context Budget).",
            })
    if hints:
        merged = {hint["path"] for hint in hints}
        for manifest in checksum_manifests(target):
            listed = manifest_lists(manifest, merged)
            hints.append({
                "path": manifest.name, "kind": "checksum-manifest",
                "missing": [f"update the entry for {name} after the merge" for name in listed],
                "snippet": None,
                "note": "This file records checksums: update the merged files' entries in the same step, and "
                        "decide whether the new harness files belong in it or stay out of the distributed set.",
            })
    return hints
