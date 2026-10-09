#!/usr/bin/env python3
"""Preview or install missing project-harness files without overwriting existing paths."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from harness_common import (
    PROFILES,
    audit_target,
    build_replacements,
    dump_json,
    render_template,
    resolve_target,
    safe_destination,
    template_files,
)


def build_plan(target: Path, profile: str) -> list[dict[str, str]]:
    plan: list[dict[str, str]] = []
    for relative, source in template_files(profile):
        destination = safe_destination(target, relative)
        if destination.is_symlink():
            status = "blocked-symlink"
        elif destination.is_file():
            status = "skip-existing"
        elif destination.is_dir():
            status = "blocked-directory"
        elif destination.exists():
            status = "blocked-other"
        else:
            status = "create"
        plan.append({"path": relative, "source": str(source), "status": status})
    return plan


def apply_plan(target: Path, plan: list[dict[str, str]], replacements: dict[str, str]) -> None:
    for item in plan:
        if item["status"] != "create":
            continue
        destination = safe_destination(target, item["path"])
        destination.parent.mkdir(parents=True, exist_ok=True)
        rendered = render_template(Path(item["source"]), replacements)
        with destination.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(rendered)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", required=True, help="Existing target repository directory")
    parser.add_argument("--profile", choices=PROFILES, default="minimal")
    parser.add_argument("--project-name", help="Name inserted into missing templates")
    parser.add_argument("--objective", help="Evidence-backed project objective inserted into missing templates")
    parser.add_argument("--verification-command", action="append", default=[], help="Override inferred command; repeat as needed")
    parser.add_argument("--apply", action="store_true", help="Write missing files; without this flag the command is preview-only")
    parser.add_argument("--allow-dirty", action="store_true", help="Permit apply on a dirty Git worktree after explicit review")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    try:
        target = resolve_target(args.target)
        audit = audit_target(target, args.profile)
        project_name = (args.project_name or target.name).strip()
        objective = (args.objective or f"以可验证、可恢复、可审计的方式维护并演进 {project_name}。").strip()
        commands = args.verification_command or audit["project"]["verification_commands"]
        replacements = build_replacements(
            project_name=project_name,
            objective=objective,
            project_type=audit["project"]["project_type"],
            profile=args.profile,
            verification_commands=commands,
        )
        plan = build_plan(target, args.profile)
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    blocked = [item for item in plan if item["status"].startswith("blocked-")]
    if args.apply and blocked:
        print("ERROR: apply blocked because one or more target paths are unsafe", file=sys.stderr)
        for item in blocked:
            print(f"  - {item['status']}: {item['path']}", file=sys.stderr)
        return 2
    if args.apply and audit["git"]["dirty"] and not args.allow_dirty:
        print("ERROR: Git worktree is dirty; inspect overlap and pass --allow-dirty only with explicit authorization", file=sys.stderr)
        return 2

    if args.apply:
        try:
            apply_plan(target, plan, replacements)
        except (FileExistsError, OSError, ValueError) as exc:
            print(f"ERROR: installation stopped: {exc}", file=sys.stderr)
            return 2

    payload = {
        "schema_version": "project-harness-apply-v1",
        "mode": "apply" if args.apply else "preview",
        "target": str(target),
        "profile": args.profile,
        "git_dirty": audit["git"]["dirty"],
        "verification_commands": list(commands),
        "plan": plan,
        "summary": {
            "create": sum(item["status"] == "create" for item in plan),
            "skip_existing": sum(item["status"] == "skip-existing" for item in plan),
            "blocked": len(blocked),
        },
    }
    if args.json:
        print(dump_json(payload))
    else:
        print(f"Mode: {payload['mode']}")
        print(f"Target: {payload['target']}")
        print(f"Profile: {payload['profile']}")
        for item in plan:
            verb = "created" if args.apply and item["status"] == "create" else item["status"]
            print(f"  - {verb}: {item['path']}")
        print(
            "Summary: "
            f"create={payload['summary']['create']} "
            f"skip_existing={payload['summary']['skip_existing']} "
            f"blocked={payload['summary']['blocked']}"
        )
        if not args.apply:
            print("Preview only: no files were written. Re-run with --apply after approval.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
