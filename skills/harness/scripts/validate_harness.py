#!/usr/bin/env python3
"""Score a project harness and fail when critical restartability gates are missing."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from harness_checks import (
    check,
    context_budget_warnings,
    entry_pointer_warnings,
    gate_warnings,
    instructions_checks,
    intent_warnings,
    lifecycle_checks,
    scope_checks,
    state_checks,
    task_cards_state,
    verification_checks,
)
from harness_checks_optional import governance_checks, hooks_checks, hooks_enabled, task_cards_checks
from harness_common import PROFILES, dump_json, git_state, resolve_target
from harness_portability import ensure_utf8_stdio, read_json_file
from harness_portability import read_text_or_empty as read_text


def infer_profile(root: Path) -> str:
    config = root / ".harness" / "config.json"
    if config.is_file():
        try:
            value = read_json_file(config).get("profile")
            if value in PROFILES:
                return value
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, AttributeError):
            pass
    if (root / "docs" / "exec-plans" / "roadmap.md").is_file():
        return "governed"
    return "minimal"


# Installer text that stays in INSTRUCTIONS.md until a maintainer wires the real workflow entry.
WORKFLOW_ENTRY_PLACEHOLDER = "待维护者从项目现有说明接线"


def build_checks(root: Path, profile: str, is_git: bool) -> dict[str, list[dict[str, Any]]]:
    agents = read_text(root / "AGENTS.md")
    instructions = read_text(root / "INSTRUCTIONS.md")
    progress = read_text(root / "PROGRESS.md")
    handoff = read_text(root / "HANDOFF.md")
    docs_index = read_text(root / "docs" / "README.md")

    categories: dict[str, list[dict[str, Any]]] = {
        "instructions": instructions_checks(root, agents, is_git),
        "state": state_checks(root, instructions, progress, handoff),
        "verification": verification_checks(root, agents, progress, handoff),
        "scope": scope_checks(agents, instructions, is_git),
        "lifecycle": lifecycle_checks(agents, progress, handoff),
    }
    if profile == "governed":
        categories["governance"] = governance_checks(root, agents, docs_index)
    enabled, card_dir = task_cards_state(root)
    if enabled:
        categories["task_cards"] = task_cards_checks(root, agents, card_dir)
    if hooks_enabled(root):
        categories["hooks"] = hooks_checks(root)
    return categories


def calibration_warnings(root: Path) -> list[str]:
    """Unscored reminders: installer placeholders still in place, and parts an older install lacks."""
    instructions = read_text(root / "INSTRUCTIONS.md")
    agents = read_text(root / "AGENTS.md")
    warnings: list[str] = []
    if WORKFLOW_ENTRY_PLACEHOLDER in instructions:
        warnings.append("INSTRUCTIONS.md Use Contract still has the installer placeholder for the workflow entry; "
                        "wire the real entry (or pass --workflow-entry) during calibration")
    return (warnings + context_budget_warnings(root, instructions) + intent_warnings(root, agents)
            + gate_warnings(root, agents) + entry_pointer_warnings(root))


def score(root: Path, profile: str) -> dict[str, Any]:
    is_git = bool(git_state(root)["is_repository"])
    categories = build_checks(root, profile, is_git)
    category_results: dict[str, Any] = {}
    critical_failures: list[dict[str, Any]] = []
    for name, checks in categories.items():
        passed = sum(item["passed"] for item in checks)
        category_score = round((passed / len(checks)) * 100)
        category_results[name] = {"score": category_score, "passed": passed, "total": len(checks), "checks": checks}
        critical_failures.extend(item for item in checks if item["critical"] and not item["passed"])
    overall = round(sum(item["score"] for item in category_results.values()) / len(category_results))
    return {
        "schema_version": "project-harness-validation-v1",
        "target": str(root),
        "profile": profile,
        "git_repository": is_git,
        "overall_score": overall,
        "categories": category_results,
        "critical_failures": critical_failures,
        "warnings": calibration_warnings(root),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", required=True)
    parser.add_argument("--profile", choices=("auto", *PROFILES), default="auto")
    parser.add_argument("--min-score", type=int, default=80)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if not 0 <= args.min_score <= 100:
        parser.error("--min-score must be between 0 and 100")

    try:
        root = resolve_target(args.target)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    profile = infer_profile(root) if args.profile == "auto" else args.profile
    payload = score(root, profile)
    try:
        config = read_json_file(root / ".harness/config.json")
        config_profile = config.get("profile") if isinstance(config, dict) else None
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        config_profile = None
    if config_profile != profile:
        payload["critical_failures"].append(check(
            f"profile mismatch: config={config_profile} requested={profile}", False,
            ".harness/config.json", critical=True))
    passed = payload["overall_score"] >= args.min_score and not payload["critical_failures"]
    payload["minimum_score"] = args.min_score
    payload["passed"] = passed

    if args.json:
        print(dump_json(payload))
    else:
        print(f"Target: {payload['target']}")
        print(f"Profile: {profile}")
        for name, category in payload["categories"].items():
            print(f"{name}: {category['score']}/100 ({category['passed']}/{category['total']})")
            for item in category["checks"]:
                mark = "PASS" if item["passed"] else "FAIL"
                suffix = " [critical]" if item["critical"] else ""
                print(f"  - {mark}: {item['label']} ({item['path']}){suffix}")
        print(f"Overall: {payload['overall_score']}/100")
        print(f"Critical failures: {len(payload['critical_failures'])}")
        for warning in payload["warnings"]:
            print(f"Warning: {warning}")
        print(f"Result: {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


if __name__ == "__main__":
    ensure_utf8_stdio()
    raise SystemExit(main())
