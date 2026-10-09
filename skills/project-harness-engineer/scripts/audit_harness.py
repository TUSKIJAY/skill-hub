#!/usr/bin/env python3
"""Read-only audit of a target repository's coding-agent harness."""

from __future__ import annotations

import argparse
import sys

from harness_common import PROFILES, audit_target, dump_json, resolve_target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", required=True, help="Existing target repository directory")
    parser.add_argument("--profile", choices=PROFILES, default="minimal")
    parser.add_argument("--json", action="store_true", help="Emit only JSON")
    args = parser.parse_args(argv)

    try:
        target = resolve_target(args.target)
        payload = audit_target(target, args.profile)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(dump_json(payload))
        return 0

    summary = payload["summary"]
    project = payload["project"]
    git = payload["git"]
    print(f"Target: {payload['target']}")
    print(f"Profile: {payload['profile']}")
    print(f"Project type: {project['project_type']}")
    print(f"Git: repository={str(git['is_repository']).lower()} dirty={str(git['dirty']).lower()} branch={git['branch'] or '-'}")
    print(f"Artifacts: missing={summary['missing']} existing={summary['existing']} blocked={summary['blocked']}")
    print("Verification commands:")
    if project["verification_commands"]:
        for command in project["verification_commands"]:
            print(f"  - {command}")
    else:
        print("  - [not inferred]")
    print("Artifact plan:")
    for item in payload["artifacts"]:
        print(f"  - {item['status']}: {item['path']}")
    if payload["recommendations"]:
        print("Recommendations:")
        for recommendation in payload["recommendations"]:
            print(f"  - {recommendation}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
