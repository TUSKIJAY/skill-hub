#!/usr/bin/env python3
"""Shared, dependency-free helpers for project harness audit/install/validation.

Target and path safety plus the audit report live here; template and project-detection
names are re-exported from harness_templates and harness_project for existing importers.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from harness_portability import read_text_or_empty
from harness_project import detect_project, git_state, run_git
from harness_templates import (
    ASSET_ROOT,
    DEFAULT_TASK_CARDS_DIR,
    FRAGMENTS_ROOT,
    PROFILES,
    SKILL_ROOT,
    TASK_CARDS_MAX_ACTIVE,
    TASK_CARDS_ROOT,
    build_replacements,
    normalize_task_cards_dir,
    render_template,
    template_files,
)

__all__ = [
    "ASSET_ROOT",
    "DEFAULT_TASK_CARDS_DIR",
    "FRAGMENTS_ROOT",
    "PROFILES",
    "SKILL_ROOT",
    "TASK_CARDS_MAX_ACTIVE",
    "TASK_CARDS_ROOT",
    "audit_target",
    "build_replacements",
    "detect_project",
    "dump_json",
    "git_state",
    "normalize_task_cards_dir",
    "parent_blocker",
    "path_status",
    "render_template",
    "resolve_target",
    "run_git",
    "safe_destination",
    "template_files",
]


def resolve_target(value: str | Path) -> Path:
    target = Path(value).expanduser().resolve()
    if not target.exists():
        raise ValueError(f"Target does not exist: {target}")
    if not target.is_dir():
        raise ValueError(f"Target is not a directory: {target}")
    return target


def parent_blocker(target: Path, relative: str) -> str | None:
    parts = Path(relative)
    if parts.is_absolute() or ".." in parts.parts:
        return "blocked-unsafe-path"
    cursor = target
    for part in parts.parts[:-1]:
        cursor = cursor / part
        if cursor.is_symlink():
            return "blocked-symlink"
        if cursor.exists() and not cursor.is_dir():
            return "blocked-parent-file"
    return None


def path_status(target: Path, relative: str) -> dict[str, Any]:
    path = target / Path(relative)
    blocker = parent_blocker(target, relative)
    if blocker:
        status = blocker
    elif path.is_symlink():
        status = "blocked-symlink"
    elif path.is_file():
        status = "existing-file"
    elif path.is_dir():
        status = "blocked-directory"
    elif path.exists():
        status = "blocked-other"
    else:
        status = "missing"
    return {
        "path": relative,
        "status": status,
        "manual_merge": status == "existing-file",
        "blocked": status.startswith("blocked-"),
    }


def audit_target(target: Path, profile: str) -> dict[str, Any]:
    project = detect_project(target)
    git = git_state(target)
    artifacts = [path_status(target, relative) for relative, _ in template_files(profile)]
    existing_instruction_files = [
        name
        for name in ("AGENTS.md", "CLAUDE.md", "INSTRUCTIONS.md", "PROGRESS.md", "progress.md", "HANDOFF.md", "session-handoff.md")
        if (target / name).exists()
    ]
    recommendations: list[str] = []
    if "CLAUDE.md" in existing_instruction_files and "agents.md" not in read_text_or_empty(target / "CLAUDE.md").lower():
        recommendations.append("CLAUDE.md does not point to AGENTS.md: append the one-line @AGENTS.md pointer the apply preview "
                               "prints (Claude Code auto-loads CLAUDE.md, not AGENTS.md); never overwrite CLAUDE.md.")
    if "progress.md" in existing_instruction_files and "PROGRESS.md" not in existing_instruction_files:
        recommendations.append("Existing lowercase progress.md requires a manual state-model merge; do not create a parallel history silently.")
    if "session-handoff.md" in existing_instruction_files and "HANDOFF.md" not in existing_instruction_files:
        recommendations.append("Existing session-handoff.md requires a manual naming/authority decision; do not duplicate handoff state silently.")
    if git.get("status_error"):
        recommendations.append(f"git status failed ({git['status_error']}); the worktree is treated as dirty.")
    if git["dirty"]:
        recommendations.append("Git worktree is dirty. Preview is safe; apply requires explicit --allow-dirty after overlap inspection.")
    if not project["verification_commands"]:
        recommendations.append("No executable check inferred. Use existing artifact/source checks via --acceptance-check; do not invent a code/CI requirement.")
    if any(item["manual_merge"] for item in artifacts):
        recommendations.append("Existing harness paths will be skipped and must be merged manually from repository evidence; "
                               "the apply preview lists what each existing file lacks (manual_merge).")
    if any(item["blocked"] for item in artifacts):
        recommendations.append("At least one expected file path is blocked by a directory, symlink, or special path; resolve it before apply.")

    return {
        "schema_version": "project-harness-audit-v1",
        "target": str(target),
        "profile": profile,
        "project": project,
        "git": git,
        "existing_instruction_files": existing_instruction_files,
        "artifacts": artifacts,
        "summary": {
            "missing": sum(item["status"] == "missing" for item in artifacts),
            "existing": sum(item["status"] == "existing-file" for item in artifacts),
            "blocked": sum(bool(item["blocked"]) for item in artifacts),
        },
        "recommendations": recommendations,
    }


def safe_destination(root: Path, relative: str) -> Path:
    blocker = parent_blocker(root, relative)
    if blocker:
        raise ValueError(f"Unsafe template destination ({blocker}): {relative}")
    destination = root / Path(relative)
    root_resolved = root.resolve()
    parent_resolved = destination.parent.resolve(strict=False)
    if os.path.commonpath([str(root_resolved), str(parent_resolved)]) != str(root_resolved):
        raise ValueError(f"Template destination escapes target: {relative}")
    return destination


def dump_json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
