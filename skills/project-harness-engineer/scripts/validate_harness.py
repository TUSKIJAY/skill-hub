#!/usr/bin/env python3
"""Score a project harness and fail when critical restartability gates are missing."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from harness_common import PROFILES, dump_json, resolve_target


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def present(root: Path, relative: str) -> bool:
    return (root / relative).is_file()


def contains_all(text: str, groups: list[tuple[str, ...]]) -> bool:
    lowered = text.lower()
    return all(any(term.lower() in lowered for term in group) for group in groups)


def check(label: str, passed: bool, path: str, *, critical: bool = False) -> dict[str, Any]:
    return {"label": label, "passed": bool(passed), "path": path, "critical": critical}


def infer_profile(root: Path) -> str:
    config = root / ".harness" / "config.json"
    if config.is_file():
        try:
            value = json.loads(config.read_text(encoding="utf-8")).get("profile")
            if value in PROFILES:
                return value
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, AttributeError):
            pass
    if (root / "docs" / "exec-plans" / "roadmap.md").is_file():
        return "governed"
    return "minimal"


def build_checks(root: Path, profile: str) -> dict[str, list[dict[str, Any]]]:
    agents = read_text(root / "AGENTS.md")
    instructions = read_text(root / "INSTRUCTIONS.md")
    progress = read_text(root / "PROGRESS.md")
    handoff = read_text(root / "HANDOFF.md")
    roadmap = read_text(root / "docs" / "exec-plans" / "roadmap.md")
    docs_index = read_text(root / "docs" / "README.md")

    categories: dict[str, list[dict[str, Any]]] = {
        "instructions": [
            check("AGENTS.md exists", present(root, "AGENTS.md"), "AGENTS.md", critical=True),
            check(
                "Startup contract routes all four root state files",
                contains_all(
                    agents,
                    [("startup", "启动"), ("instructions.md",), ("progress.md",), ("handoff.md",)],
                ),
                "AGENTS.md",
                critical=True,
            ),
            check("Git status is part of startup", "git status" in agents.lower(), "AGENTS.md"),
            check(
                "Conflict precedence chain is declared",
                contains_all(agents, [("优先级", "precedence")]),
                "AGENTS.md",
            ),
            check(
                "Ledger discipline is declared",
                "harness_log" in agents.lower(),
                "AGENTS.md",
            ),
        ],
        "state": [
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
        ],
        "verification": [
            check(
                "Native verification commands are documented",
                contains_all(instructions, [("verification", "验证"), ("test", "pytest", "unittest", "build", "lint", "compile", "待补充")]),
                "INSTRUCTIONS.md",
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
        ],
        "scope": [
            check(
                "Unrelated user changes are protected",
                contains_all(agents, [("unrelated", "无关"), ("preserve", "保留", "不得覆盖")]),
                "AGENTS.md",
                critical=True,
            ),
            check(
                "Scope boundary is explicit",
                contains_all(agents + instructions, [("scope", "范围", "边界")]),
                "AGENTS.md / INSTRUCTIONS.md",
            ),
            check(
                "Completion and commit policy is explicit",
                contains_all(agents, [("commit", "提交"), ("complete", "完成")]),
                "AGENTS.md",
            ),
        ],
        "lifecycle": [
            check(
                "Task triage fast path lets small work execute directly",
                contains_all(agents, [("triage", "分级"), ("direct", "直接执行", "fast path")]),
                "AGENTS.md",
            ),
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
        ],
    }

    if profile == "governed":
        categories["governance"] = [
            check("Docs authority map exists", present(root, "docs/README.md"), "docs/README.md", critical=True),
            check("Exec-plan roadmap exists", present(root, "docs/exec-plans/roadmap.md"), "docs/exec-plans/roadmap.md", critical=True),
            check(
                "Plan lifecycle separates proposed, active, and completed",
                contains_all(roadmap, [("proposed",), ("active",), ("completed",), ("review",)]),
                "docs/exec-plans/roadmap.md",
                critical=True,
            ),
            check(
                "Optimization intake carries no execution authority",
                contains_all(read_text(root / "docs/optimization/SOP.md"), [("optimization", "优化"), ("not authorize", "不授权", "不得授权")]),
                "docs/optimization/SOP.md",
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
    return categories


def score(root: Path, profile: str) -> dict[str, Any]:
    categories = build_checks(root, profile)
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
        "overall_score": overall,
        "categories": category_results,
        "critical_failures": critical_failures,
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
        print(f"Result: {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
