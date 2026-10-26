#!/usr/bin/env python3
"""Preview or install missing project-harness files without overwriting existing paths."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from harness_common import (
    DEFAULT_TASK_CARDS_DIR,
    PROFILES,
    TASK_CARDS_MAX_ACTIVE,
    TASK_CARDS_ROOT,
    audit_target,
    build_replacements,
    dump_json,
    normalize_task_cards_dir,
    render_template,
    path_status,
    resolve_target,
    safe_destination,
    template_files,
)
from harness_merge import core_manual_merge
from harness_portability import (
    checked_python_command,
    ensure_utf8_stdio,
    read_json_file,
    read_text_or_empty,
    with_python_command,
)
from harness_templates import (
    CLAUDE_SETTINGS,
    DEFAULT_SCRATCH_DIR,
    HOOK_SCRIPT,
    HOOKS_CONFIG,
    checked_context_budget,
    normalize_scratch_dir,
    render_hooks_settings,
    render_pre_commit,
)


def build_plan(target: Path, profile: str, task_cards_dir: str | None = None,
               hooks: bool = False) -> list[dict[str, str]]:
    plan: list[dict[str, str]] = []
    for relative, source in template_files(profile, task_cards_dir, hooks):
        state = path_status(target, relative)["status"]
        status = {"existing-file": "skip-existing", "missing": "create"}.get(state, state)
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


def installed_python_command(target: Path) -> str | None:
    """The interpreter an earlier install recorded, so a re-run renders the same command."""
    text = _existing_text(target, ".harness/config.json")
    if not text:
        return None
    try:
        value = json.loads(text).get("python_command")
        return checked_python_command(value) if isinstance(value, str) else None
    except (json.JSONDecodeError, AttributeError, ValueError):
        return None


def installed_context_budget(target: Path, scratch_dir: str | None) -> dict[str, object]:
    """Defaults, overlaid with an earlier install's valid `context_budget`, then with --scratch-dir."""
    text = _existing_text(target, ".harness/config.json")
    block = None
    if text:
        try:
            config = json.loads(text)
            block = config.get("context_budget") if isinstance(config, dict) else None
        except json.JSONDecodeError:
            block = None
    budget = checked_context_budget(block)
    if scratch_dir is not None:
        budget["scratch_dir"] = scratch_dir
    return budget


def gitignore_hint(target: Path, scratch_dir: str) -> str | None:
    """A reminder (never a write) when the project's .gitignore does not cover the scratch directory."""
    text = _existing_text(target, ".gitignore")
    if text is None:
        return None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith(("#", "!")):
            continue
        pattern = line.strip("/")
        for suffix in ("/**", "/*"):
            pattern = pattern.removesuffix(suffix)
        if pattern and (scratch_dir == pattern or scratch_dir.startswith(pattern + "/")):
            return None
    return (f".gitignore does not list {scratch_dir}/; add a line `{scratch_dir}/` so scratch output stays out of "
            "commits (the installer does not edit .gitignore; .harness/history/log.jsonl must stay tracked)")


def _existing_text(target: Path, relative: str) -> str | None:
    """Text of an existing regular file, or None when the path is missing or blocked."""
    if path_status(target, relative)["status"] != "existing-file":
        return None
    return read_text_or_empty(target / relative)


def task_cards_manual_merge(target: Path, directory: str) -> list[str]:
    """Existing files are never rewritten; name the hand merges an enabled component still needs."""
    hints: list[str] = []
    config_text = _existing_text(target, ".harness/config.json")
    if config_text is not None:
        try:
            config = json.loads(config_text)
        except json.JSONDecodeError:
            config = None
        current = config.get("task_cards") if isinstance(config, dict) else None
        if not isinstance(current, dict) or current.get("dir") != directory:
            expected = json.dumps({"dir": directory, "max_active": TASK_CARDS_MAX_ACTIVE}, ensure_ascii=False)
            hints.append(f'.harness/config.json: add "task_cards": {expected}')
    agents_text = _existing_text(target, "AGENTS.md")
    if agents_text is not None and "## Task Cards" not in agents_text:
        hints.append(
            "AGENTS.md: add the Task Cards section from "
            f"{TASK_CARDS_ROOT / 'agents-section.md'} (replace the directory token with {directory})"
        )
    lint_text = _existing_text(target, "scripts/check-project-harness.py")
    if lint_text is not None and "lint_task_cards" not in lint_text:
        hints.append(
            "scripts/check-project-harness.py: merge the task-card lint from the skill "
            "(assets/fragments/task-card-lint.py.frag, rendered into "
            "assets/minimal/scripts/check-project-harness.py.tmpl) so card states are checked"
        )
    return hints


def hooks_manual_merge(target: Path, plan: list[dict[str, str]], python_command: str) -> tuple[list[str], list[dict]]:
    """(config hints, manual_merge entries) for an enabled hooks component; existing files stay untouched."""
    hints: list[str] = []
    config_text = _existing_text(target, ".harness/config.json")
    if config_text is not None:
        try:
            config = json.loads(config_text)
        except json.JSONDecodeError:
            config = None
        current = config.get("hooks") if isinstance(config, dict) else None
        if not isinstance(current, dict) or current.get("enabled") is not True:
            hints.append(f'.harness/config.json: add "hooks": {json.dumps(HOOKS_CONFIG)}')
    merges: list[dict] = []
    skipped = {item["path"] for item in plan if item["status"] == "skip-existing"}
    settings_text = _existing_text(target, CLAUDE_SETTINGS) if CLAUDE_SETTINGS in skipped else None
    if settings_text is not None and "harness_hook.py" not in settings_text:
        merges.append({
            "path": CLAUDE_SETTINGS, "kind": "hooks",
            "missing": ["the harness hook entries (PreToolUse Edit|Write|MultiEdit and Bash|PowerShell, Stop)"],
            "snippet": render_hooks_settings(python_command),
            "note": ("Merge the hooks block into the existing file: keep its other keys, and when it already has "
                     "\"hooks\", add these entries to its PreToolUse and Stop arrays."),
        })
    return hints, merges


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", required=True, help="Existing target project directory; Git is optional")
    parser.add_argument("--profile", choices=PROFILES, default="minimal")
    parser.add_argument("--project-name", help="Name inserted into missing templates")
    parser.add_argument("--objective", help="Evidence-backed project objective inserted into missing templates")
    parser.add_argument("--verification-command", action="append", default=[], help="Override inferred command; repeat as needed")
    parser.add_argument("--acceptance-check", action="append", default=[], help="Observable manual/source/artifact check; repeat as needed, never executed by installer")
    parser.add_argument("--workflow-entry", default="", help="Existing workflow entrypoint or document, declared only")
    parser.add_argument("--project-type", help="Evidence-backed domain description; overrides software-marker inference")
    parser.add_argument("--python-command", default=None, help="Verified one-line interpreter command written into generated files, e.g. python, python3 or \"py -3\" (default: python on Windows, python3 elsewhere); never executed")
    parser.add_argument("--task-cards", action="store_true", help="Opt in to the task-card component: index, template, config field and AGENTS rules (off by default)")
    parser.add_argument("--task-cards-dir", default=None, help=f"Task-card directory relative to the target (default {DEFAULT_TASK_CARDS_DIR}); requires --task-cards")
    parser.add_argument("--hooks", action="store_true", help=f"Opt in to the Claude Code hooks component: {HOOK_SCRIPT}, {CLAUDE_SETTINGS} when missing, and the config field; silent unless a rule is broken (off by default)")
    parser.add_argument("--scratch-dir", default=None, help=f"Directory, relative to the target, where the Context Budget sends output of unknown length (default {DEFAULT_SCRATCH_DIR}, or the installed config's value); never created by the installer")
    parser.add_argument("--apply", action="store_true", help="Write missing files; without this flag the command is preview-only")
    parser.add_argument("--allow-dirty", action="store_true", help="Permit apply on a dirty Git worktree after explicit review")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if args.task_cards_dir is not None and not args.task_cards:
        parser.error("--task-cards-dir requires --task-cards")

    try:
        target = resolve_target(args.target)
        audit = audit_target(target, args.profile)
        task_cards_dir = None
        if args.task_cards:
            task_cards_dir = normalize_task_cards_dir(DEFAULT_TASK_CARDS_DIR if args.task_cards_dir is None else args.task_cards_dir)
        project_name = (args.project_name or target.name).strip()
        objective = (args.objective or f"以可验证、可恢复、可审计的方式维护并演进 {project_name}。").strip()
        python_command = checked_python_command(
            args.python_command if args.python_command is not None else installed_python_command(target)
        )
        scratch_dir = None if args.scratch_dir is None else normalize_scratch_dir(args.scratch_dir)
        context_budget = installed_context_budget(target, scratch_dir)
        commands = args.verification_command or [
            with_python_command(command, python_command) for command in audit["project"]["verification_commands"]
        ]
        replacements = build_replacements(
            project_name=project_name,
            objective=objective,
            project_type=args.project_type or audit["project"]["project_type"],
            profile=args.profile,
            verification_commands=commands,
            acceptance_checks=args.acceptance_check,
            workflow_entry=args.workflow_entry,
            task_cards_dir=task_cards_dir,
            python_command=python_command,
            context_budget=context_budget,
            hooks=args.hooks,
        )
        plan = build_plan(target, args.profile, task_cards_dir, args.hooks)
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    blocked = [item for item in plan if item["status"].startswith("blocked-")]
    if args.apply and blocked:
        print("ERROR: apply blocked because one or more target paths are unsafe", file=sys.stderr)
        for item in blocked:
            print(f"  - {item['status']}: {item['path']}", file=sys.stderr)
        return 2
    config_path = target / ".harness/config.json"
    profile_mismatch = None
    if not path_status(target, ".harness/config.json")["blocked"] and config_path.is_file():
        try:
            config = read_json_file(config_path)
            installed_profile = config.get("profile") if isinstance(config, dict) else None
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            installed_profile = None
        if installed_profile != args.profile:
            profile_mismatch = f"profile mismatch: config={installed_profile} requested={args.profile}; manually align config during authorized migration before apply"
    if args.apply and profile_mismatch:
        print(f"ERROR: {profile_mismatch}", file=sys.stderr)
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

    manual_merge = core_manual_merge(target, plan, bool(audit["git"]["is_repository"]), python_command,
                                     context_budget)
    hooks = None
    if args.hooks:
        hook_hints, hook_merges = hooks_manual_merge(target, plan, python_command)
        manual_merge.extend(hook_merges)
        hooks = {
            "enabled": True,
            "script": HOOK_SCRIPT,
            "settings": CLAUDE_SETTINGS,
            "manual_merge": hook_hints,
            "pre_commit": render_pre_commit(python_command),
        }
    scratch_hint = gitignore_hint(target, str(context_budget["scratch_dir"]))
    task_cards = None
    if task_cards_dir:
        task_cards = {
            "enabled": True,
            "dir": task_cards_dir,
            "max_active": TASK_CARDS_MAX_ACTIVE,
            "manual_merge": task_cards_manual_merge(target, task_cards_dir),
        }
    payload = {
        "schema_version": "project-harness-apply-v1",
        "mode": "apply" if args.apply else "preview",
        "target": str(target),
        "profile": args.profile,
        "git_dirty": audit["git"]["dirty"],
        "profile_mismatch": profile_mismatch,
        "python_command": python_command,
        "verification_commands": list(commands),
        "acceptance_checks": args.acceptance_check,
        "workflow_entry": args.workflow_entry,
        "project_type": args.project_type or audit["project"]["project_type"],
        "task_cards": task_cards,
        "hooks": hooks,
        "context_budget": context_budget,
        "gitignore_hint": scratch_hint,
        "manual_merge": manual_merge,
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
        if manual_merge:
            print("Manual merge (existing files are never rewritten; merge by hand during authorized maintenance):")
            for hint in manual_merge:
                verb = "lacks" if hint["kind"] == "state" else "needs"
                if hint["missing"]:
                    print(f"  - {hint['path']} {verb}: " + "; ".join(hint["missing"]))
                else:
                    print(f"  - {hint['path']}")
                print(f"    {hint['note']}")
                if hint["snippet"]:
                    # Unindented, so the lines can be pasted into Markdown as they are.
                    print(f"    Paste the lines between the markers into {hint['path']} (rendered for this project):")
                    print("----- BEGIN harness merge section -----")
                    print(hint["snippet"].rstrip("\n"))
                    print("----- END harness merge section -----")
        if scratch_hint:
            print(f"Note: {scratch_hint}")
        if task_cards:
            print(f"Task cards: enabled dir={task_cards['dir']} max_active={task_cards['max_active']}")
            for hint in task_cards["manual_merge"]:
                print(f"  - manual merge: {hint}")
        if hooks:
            print(f"Hooks: enabled script={hooks['script']} settings={hooks['settings']}")
            for hint in hooks["manual_merge"]:
                print(f"  - manual merge: {hint}")
            if audit["git"]["is_repository"]:
                print("  Optional Git pre-commit hook for other CLIs (printed only, never installed); "
                      "save as .git/hooks/pre-commit and make it executable:")
                print("----- BEGIN harness pre-commit -----")
                print(hooks["pre_commit"].rstrip("\n"))
                print("----- END harness pre-commit -----")
        if not args.apply:
            print("Preview only: no files were written. Re-run with --apply after approval.")
    return 0


if __name__ == "__main__":
    ensure_utf8_stdio()
    raise SystemExit(main())
