#!/usr/bin/env python3
"""Shared helpers for audit.py and apply.py. Standard library only.

check.py stays a single self-contained file because it is copied into projects;
this module is used only from the skill directory.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Dict, Optional

import check

SKILL_ROOT = Path(__file__).resolve().parents[1]
SKILL_VERSION = check.CHECK_VERSION
CHECK_SOURCE = SKILL_ROOT / "scripts" / "check.py"
CHECK_TARGET = "scripts/check-readable-docs.py"
RULE_CARD_ASSET = SKILL_ROOT / "assets" / "rule-card.zh.md"
SUMMARY_ASSET = SKILL_ROOT / "assets" / "template-summary.zh.md"
RULE_CARD_MARKER = "<!-- readable-docs:rule-card"
SUMMARY_MARKER = "<!-- readable-docs:summary -->"
HARNESS_CONFIG = ".harness/config.json"
READ_ENCODING = check.READ_ENCODING

# Where the rule card goes, per project shape (handoff section 7).
CARD_TARGETS: Dict[str, Optional[str]] = {
    "harness": "INSTRUCTIONS.md",
    "agents-instructions": "INSTRUCTIONS.md",
    "instructions": "INSTRUCTIONS.md",
    "agents": "AGENTS.md",
    "claude": "CLAUDE.md",
    "none": None,
}


def read_text(path: Path) -> Optional[str]:
    """Text of a UTF-8 file (BOM allowed); None when absent or unreadable."""
    try:
        return path.read_text(encoding=READ_ENCODING)
    except (OSError, UnicodeDecodeError):
        return None


def detect_shape(root: Path) -> Dict[str, object]:
    files = {name: (root / name).is_file() for name in ("AGENTS.md", "INSTRUCTIONS.md", "CLAUDE.md")}
    harness = (root / HARNESS_CONFIG).is_file()
    if files["AGENTS.md"] and files["INSTRUCTIONS.md"]:
        shape = "harness" if harness else "agents-instructions"
    elif files["AGENTS.md"]:
        shape = "agents"
    elif files["INSTRUCTIONS.md"]:
        shape = "instructions"
    elif files["CLAUDE.md"]:
        shape = "claude"
    else:
        shape = "none"
    return {
        "shape": shape,
        "instruction_files": files,
        "harness_config": harness,
        "git": check.in_git_work_tree(root),
        "card_target": CARD_TARGETS[shape],
        "config_path": ".harness/readable-docs.json" if harness else "readable-docs.json",
    }


def python_command(root: Path, override: Optional[str]) -> str:
    """The interpreter command for generated lines: override, harness config, then OS default."""
    if override is not None:
        command = override.strip()
        if not command or "\n" in command or "\r" in command:
            raise ValueError("--python-command must be one nonempty command line")
        return command
    text = read_text(root / HARNESS_CONFIG)
    if text:
        try:
            value = json.loads(text).get("python_command")
        except (ValueError, AttributeError):
            value = None
        if isinstance(value, str) and value.strip():
            return value.strip()
    return "python" if os.name == "nt" else "python3"


def dirty(root: Path, rel: str) -> bool:
    """True when the file has uncommitted changes in a Git work tree."""
    if not check.in_git_work_tree(root):
        return False
    result = subprocess.run(["git", "-C", str(root), "status", "--porcelain", "--", rel],
                            capture_output=True)
    return bool(result.stdout.strip())


def installed_check_version(path: Path) -> Optional[str]:
    text = read_text(path)
    if text is None:
        return None
    for line in text.splitlines():
        if line.startswith("CHECK_VERSION = "):
            return line.split("=", 1)[1].strip().strip("\"'")
    return "unknown"
