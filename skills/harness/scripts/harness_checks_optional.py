#!/usr/bin/env python3
"""Optional check categories of the harness validator: governed docs, task cards and hooks."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from harness_checks import check, contains_all, present
from harness_portability import read_json_file
from harness_portability import read_text_or_empty as read_text
from harness_templates import CLAUDE_SETTINGS, HOOK_SCRIPT

# Where Claude Code reads project hooks from; the local file is the per-user variant.
CLAUDE_SETTINGS_FILES = (CLAUDE_SETTINGS, ".claude/settings.local.json")


def governance_checks(root: Path, agents: str, docs_index: str) -> list[dict[str, Any]]:
    """Docs authority map, plan lifecycle and the governed document indexes."""
    return [
        check("Docs authority map exists", present(root, "docs/README.md"), "docs/README.md", critical=True),
        check("Exec-plan roadmap exists", present(root, "docs/exec-plans/roadmap.md"), "docs/exec-plans/roadmap.md", critical=True),
        check(
            "Plan lifecycle separates proposed, active, and completed",
            all(present(root, f"docs/exec-plans/{stage}/index.md")
                   for stage in ("proposed", "active", "completed", "reviews")),
            "docs/exec-plans/{proposed,active,completed,reviews}/index.md",
            critical=True,
        ),
        check(
            "Optimization intake carries no execution authority",
            present(root, "docs/optimization/SOP.md") and (
                contains_all(read_text(root / "docs/optimization/SOP.md"), [("optimization", "优化"), ("not authorize", "不授权", "不得授权")])
                or (not contains_all(read_text(root / "docs/optimization/SOP.md"), [("optimization", "优化")])
                    and "docs/harness-maintenance.md" in agents
                    and contains_all(read_text(root / "docs/harness-maintenance.md"),
                                     [("记录本身不授权实施", "records do not authorize execution")]))),
            "docs/optimization/SOP.md or linked docs/harness-maintenance.md",
            critical=True,
        ),
        check(
            "PRD index exists",
            present(root, "docs/prd/index.md"),
            "docs/prd/index.md",
        ),
        check(
            "Spec index exists",
            present(root, "docs/specs/index.md"),
            "docs/specs/index.md",
        ),
        check(
            "Docs index routes prd and specs",
            contains_all(docs_index, [("prd", "PRD", "产品需求"), ("spec", "Spec", "行为契约", "规格")]),
            "docs/README.md",
        ),
        check(
            "Docs index routes decisions and archive",
            contains_all(docs_index, [("decision", "决策"), ("archive", "归档")])
            and present(root, "docs/decisions/index.md"),
            "docs/README.md",
        ),
    ]


def task_cards_checks(root: Path, agents: str, card_dir: str | None) -> list[dict[str, Any]]:
    """Task card index/template; `card_dir` is None when task_cards.dir is unsafe."""
    shown = card_dir or "<invalid task_cards.dir>"
    return [
        check(
            "Task card index exists",
            card_dir is not None and present(root, f"{card_dir}/index.md"),
            f"{shown}/index.md",
            critical=True,
        ),
        check(
            "Task card template exists",
            card_dir is not None and present(root, f"{card_dir}/task-card-template.md"),
            f"{shown}/task-card-template.md",
            critical=True,
        ),
        check(
            "AGENTS.md declares the Task Cards rules",
            "## task cards" in agents.lower(),
            "AGENTS.md",
        ),
    ]


def hooks_enabled(root: Path) -> bool:
    """True when .harness/config.json carries a `hooks` block that is not switched off."""
    try:
        config = read_json_file(root / ".harness/config.json")
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return False
    spec = config.get("hooks") if isinstance(config, dict) else None
    return isinstance(spec, dict) and spec.get("enabled") is not False


def hooks_checks(root: Path) -> list[dict[str, Any]]:
    """The hook script exists and a Claude Code settings file wires it."""
    return [
        check("Hook script exists", present(root, HOOK_SCRIPT), HOOK_SCRIPT, critical=True),
        check(
            "Claude Code settings run the hook script",
            any("harness_hook.py" in read_text(root / name) for name in CLAUDE_SETTINGS_FILES),
            " or ".join(CLAUDE_SETTINGS_FILES),
        ),
    ]
