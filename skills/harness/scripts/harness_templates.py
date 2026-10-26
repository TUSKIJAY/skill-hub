#!/usr/bin/env python3
"""Template assets: locations, profile list, placeholder replacements and rendering."""

from __future__ import annotations

import json
import shlex
from datetime import date
from pathlib import Path
from typing import Iterable

from harness_portability import READ_ENCODING, default_python_command


SKILL_ROOT = Path(__file__).resolve().parents[1]
ASSET_ROOT = SKILL_ROOT / "assets"
PROFILES = ("minimal", "governed")
TASK_CARDS_ROOT = ASSET_ROOT / "task-cards"
FRAGMENTS_ROOT = ASSET_ROOT / "fragments"
HOOKS_ROOT = ASSET_ROOT / "hooks"
DEFAULT_TASK_CARDS_DIR = "docs/tasks"
TASK_CARDS_MAX_ACTIVE = 1
CONTEXT_BUDGET_FRAGMENT = "context-budget-section.md"
DEFAULT_SCRATCH_DIR = ".harness/tmp"
# Opt-in hooks component (--hooks): installed path -> template under assets/hooks.
HOOK_SCRIPT = "scripts/harness_hook.py"
CLAUDE_SETTINGS = ".claude/settings.json"
HOOK_TEMPLATES = ((HOOK_SCRIPT, "harness_hook.py.tmpl"), (CLAUDE_SETTINGS, "settings.json.tmpl"))
PRE_COMMIT_SAMPLE = "pre-commit.sample"
# Claude Code substitutes this placeholder itself, so the hook runs from any working directory.
HOOK_SCRIPT_ARG = "${CLAUDE_PROJECT_DIR}/" + HOOK_SCRIPT
HOOKS_CONFIG = {"enabled": True}
# Context Budget defaults (.harness/config.json `context_budget`). The numbers are not installer
# options yet; a project changes them in its config and its INSTRUCTIONS.md together.
CONTEXT_BUDGET_NUMBERS = {
    "file_lines": 200,
    "file_bytes": 16_384,
    "output_lines": 80,
    "output_bytes": 8_192,
    "head_lines": 40,
    "line_bytes": 1_000,
}


def normalize_project_dir(value: str, label: str) -> str:
    """Return a POSIX-style directory relative to the project, or raise ValueError."""
    text = str(value).strip().replace("\\", "/")
    parts = [part for part in text.split("/") if part not in ("", ".")]
    unsafe = (
        not parts
        or text.startswith("/")
        or any(part == ".." or ":" in part or part.lower() == ".git" for part in parts)
    )
    if unsafe:
        raise ValueError(f"{label} must be a relative path inside the project: {value!r}")
    return "/".join(parts)


def normalize_task_cards_dir(value: str) -> str:
    return normalize_project_dir(value, "Task cards directory")


def normalize_scratch_dir(value: str) -> str:
    return normalize_project_dir(value, "Scratch directory")


def default_context_budget() -> dict[str, object]:
    return {**CONTEXT_BUDGET_NUMBERS, "scratch_dir": DEFAULT_SCRATCH_DIR}


def checked_context_budget(value: object) -> dict[str, object]:
    """Defaults overlaid with the valid fields of a config `context_budget` block; invalid fields are ignored."""
    budget = default_context_budget()
    if not isinstance(value, dict):
        return budget
    for key in CONTEXT_BUDGET_NUMBERS:
        number = value.get(key)
        if isinstance(number, int) and not isinstance(number, bool) and number > 0:
            budget[key] = number
    scratch = value.get("scratch_dir")
    if isinstance(scratch, str):
        try:
            budget["scratch_dir"] = normalize_scratch_dir(scratch)
        except ValueError:
            pass
    return budget


def context_budget_json(budget: dict[str, object], indent: str = "  ") -> str:
    """The block as it sits in .harness/config.json, nested one level under the top-level object."""
    return json.dumps(budget, ensure_ascii=False, indent=2).replace("\n", "\n" + indent)


def context_budget_replacements(budget: dict[str, object]) -> dict[str, str]:
    """Tokens of the Context Budget section and of the generated scripts that read the block."""
    return {
        "{{CB_FILE_LINES}}": str(budget["file_lines"]),
        "{{CB_FILE_BYTES}}": str(budget["file_bytes"]),
        "{{CB_OUTPUT_LINES}}": str(budget["output_lines"]),
        "{{CB_OUTPUT_BYTES}}": str(budget["output_bytes"]),
        "{{CB_HEAD_LINES}}": str(budget["head_lines"]),
        "{{CB_SCRATCH_DIR}}": str(budget["scratch_dir"]),
        "{{CONTEXT_BUDGET_JSON}}": context_budget_json(budget),
        # One-line JSON of ints and strings, which is also a valid Python dict literal.
        "{{CONTEXT_BUDGET_INLINE}}": json.dumps(budget, ensure_ascii=False),
    }


def render_text(text: str, replacements: dict[str, str]) -> str:
    for token, value in replacements.items():
        text = text.replace(token, value)
    return text


def render_context_budget_section(python_command: str, budget: dict[str, object]) -> str:
    """The `## Context Budget` section, shared by the INSTRUCTIONS.md template and the merge hint."""
    replacements = {"{{PYTHON}}": python_command, **context_budget_replacements(budget)}
    return render_text(read_fragment(CONTEXT_BUDGET_FRAGMENT), replacements)


def template_files(profile: str, task_cards_dir: str | None = None,
                   hooks: bool = False) -> list[tuple[str, Path]]:
    if profile not in PROFILES:
        raise ValueError(f"Unknown profile: {profile}")
    roots = [ASSET_ROOT / "minimal"]
    if profile == "governed":
        roots.append(ASSET_ROOT / "governed")

    result: list[tuple[str, Path]] = []
    seen: set[str] = set()
    for root in roots:
        if not root.is_dir():
            raise ValueError(f"Template root missing: {root}")
        for source in sorted(root.rglob("*.tmpl")):
            relative = source.relative_to(root).as_posix()
            target_relative = relative.removesuffix(".tmpl")
            if target_relative in seen:
                raise ValueError(f"Duplicate template target: {target_relative}")
            seen.add(target_relative)
            result.append((target_relative, source))
    if task_cards_dir:
        directory = normalize_task_cards_dir(task_cards_dir)
        if not TASK_CARDS_ROOT.is_dir():
            raise ValueError(f"Template root missing: {TASK_CARDS_ROOT}")
        for source in sorted(TASK_CARDS_ROOT.glob("*.tmpl")):
            target_relative = f"{directory}/{source.name.removesuffix('.tmpl')}"
            if target_relative in seen:
                raise ValueError(f"Duplicate template target: {target_relative}")
            seen.add(target_relative)
            result.append((target_relative, source))
    if hooks:
        for target_relative, name in HOOK_TEMPLATES:
            source = HOOKS_ROOT / name
            if not source.is_file():
                raise ValueError(f"Template missing: {source}")
            if target_relative in seen:
                raise ValueError(f"Duplicate template target: {target_relative}")
            seen.add(target_relative)
            result.append((target_relative, source))
    return sorted(result, key=lambda item: item[0].lower())


def hook_handler(python_command: str) -> dict[str, object]:
    """Exec-form Claude Code hook handler: no shell, so cmd, PowerShell and Git Bash run it alike."""
    words = [word.strip('"\'') for word in shlex.split(python_command, posix=False)] or [python_command]
    return {"type": "command", "command": words[0], "args": [*words[1:], HOOK_SCRIPT_ARG]}


def render_hooks_settings(python_command: str) -> str:
    """The `.claude/settings.json` the component installs, also printed as a merge hint."""
    handler = json.dumps(hook_handler(python_command), ensure_ascii=False)
    return render_text((HOOKS_ROOT / "settings.json.tmpl").read_text(encoding=READ_ENCODING),
                       {"{{HOOK_HANDLER_JSON}}": handler})


def render_pre_commit(python_command: str) -> str:
    """The optional Git pre-commit hook; printed by the preview, never installed."""
    return render_text((HOOKS_ROOT / PRE_COMMIT_SAMPLE).read_text(encoding=READ_ENCODING),
                       {"{{PYTHON}}": python_command})


def read_fragment(name: str) -> str:
    """Text of a file under assets/fragments, without surrounding blank lines."""
    return (FRAGMENTS_ROOT / name).read_text(encoding=READ_ENCODING).strip("\n")


def build_replacements(
    *,
    project_name: str,
    objective: str,
    project_type: str,
    profile: str,
    verification_commands: Iterable[str],
    acceptance_checks: Iterable[str] = (),
    workflow_entry: str = "",
    task_cards_dir: str | None = None,
    python_command: str | None = None,
    context_budget: dict[str, object] | None = None,
    hooks: bool = False,
) -> dict[str, str]:
    python_command = python_command or default_python_command()
    budget = checked_context_budget(context_budget)
    commands = list(dict.fromkeys(command.strip() for command in verification_commands if command.strip()))
    checks = list(dict.fromkeys(item.strip() for item in acceptance_checks if item.strip()))
    markdown_commands = "\n".join(f"- `{command}`" for command in commands)
    if not markdown_commands:
        markdown_commands = "- 未声明可执行检查；不要求为此新增测试或 CI。"
    markdown_checks = "\n".join(f"- 核对：{item}" for item in checks)
    if not markdown_checks:
        markdown_checks = "- 人工核对项未单独声明。" if commands else "- 待校准：从项目要求确定实际产物的验收方式，尚不能宣称业务验收通过。"
    # Task cards are opt-in: without a directory the optional tokens render empty.
    task_cards_directory = ""
    task_cards_section = ""
    task_cards_json = ""
    if task_cards_dir:
        task_cards_directory = normalize_task_cards_dir(task_cards_dir)
        fragment = (TASK_CARDS_ROOT / "agents-section.md").read_text(encoding=READ_ENCODING)
        task_cards_section = fragment.replace("{{TASK_CARDS_DIR}}", task_cards_directory).strip("\n")
        task_cards_config = {"dir": task_cards_directory, "max_active": TASK_CARDS_MAX_ACTIVE}
        task_cards_json = ",\n  \"task_cards\": " + json.dumps(task_cards_config, ensure_ascii=False)
    hooks_json = ",\n  \"hooks\": " + json.dumps(HOOKS_CONFIG, ensure_ascii=False) if hooks else ""
    return {
        "{{PYTHON}}": python_command,
        "{{PYTHON_JSON}}": json.dumps(python_command, ensure_ascii=False),
        "{{PROJECT_NAME}}": project_name,
        "{{OBJECTIVE}}": objective,
        "{{PROJECT_TYPE}}": project_type,
        "{{PROFILE}}": profile,
        "{{DATE}}": date.today().isoformat(),
        "{{VERIFICATION_COMMANDS}}": markdown_commands,
        "{{ACCEPTANCE_CHECKS}}": markdown_checks,
        "{{WORKFLOW_ENTRY}}": workflow_entry.strip() or "待维护者从项目现有说明接线；这不是已可运行的声明。",
        "{{PROJECT_NAME_JSON}}": json.dumps(project_name, ensure_ascii=False),
        "{{PROFILE_JSON}}": json.dumps(profile, ensure_ascii=False),
        "{{PROJECT_TYPE_JSON}}": json.dumps(project_type, ensure_ascii=False),
        "{{VERIFICATION_JSON}}": json.dumps(commands, ensure_ascii=False),
        "{{ACCEPTANCE_JSON}}": json.dumps(checks, ensure_ascii=False),
        "{{WORKFLOW_ENTRY_JSON}}": json.dumps(workflow_entry.strip(), ensure_ascii=False),
        "{{TASK_CARDS_DIR}}": task_cards_directory,
        "{{TASK_CARDS_SECTION}}": task_cards_section,
        "{{TASK_CARDS_JSON}}": task_cards_json,
        "{{TASK_CARD_CONSTANTS}}": read_fragment("task-card-constants.py.frag"),
        "{{TASK_CARD_LINT}}": read_fragment("task-card-lint.py.frag"),
        "{{HOOKS_JSON}}": hooks_json,
        "{{HOOK_HANDLER_JSON}}": json.dumps(hook_handler(python_command), ensure_ascii=False),
        **context_budget_replacements(budget),
        # Rendered before insertion: the section's own tokens are already replaced.
        "{{CONTEXT_BUDGET_SECTION}}": render_context_budget_section(python_command, budget),
    }


def render_template(source: Path, replacements: dict[str, str]) -> str:
    rendered = source.read_text(encoding=READ_ENCODING)
    for token, value in replacements.items():
        if not value and token.endswith("_SECTION}}"):
            # An empty optional section also drops the blank line that followed it.
            rendered = rendered.replace(f"{token}\n\n", "")
        rendered = rendered.replace(token, value)
    unresolved = sorted({part.split("}}", 1)[0] + "}}" for part in rendered.split("{{")[1:] if "}}" in part})
    if unresolved:
        raise ValueError(f"Unresolved template tokens in {source}: {', '.join(unresolved)}")
    return rendered
