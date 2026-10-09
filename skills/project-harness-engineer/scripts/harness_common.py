#!/usr/bin/env python3
"""Shared, dependency-free helpers for project harness audit/install/validation."""

from __future__ import annotations

import json
import os
import subprocess
from datetime import date
from pathlib import Path
from typing import Any, Iterable


SKILL_ROOT = Path(__file__).resolve().parents[1]
ASSET_ROOT = SKILL_ROOT / "assets"
PROFILES = ("minimal", "governed")


def resolve_target(value: str | Path) -> Path:
    target = Path(value).expanduser().resolve()
    if not target.exists():
        raise ValueError(f"Target does not exist: {target}")
    if not target.is_dir():
        raise ValueError(f"Target is not a directory: {target}")
    return target


def run_git(target: Path, *args: str) -> subprocess.CompletedProcess[str]:
    command = ["git", "-C", str(target), *args]
    try:
        return subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except FileNotFoundError as exc:
        return subprocess.CompletedProcess(command, 127, stdout="", stderr=str(exc))


def git_state(target: Path) -> dict[str, Any]:
    probe = run_git(target, "rev-parse", "--is-inside-work-tree")
    if probe.returncode != 0 or probe.stdout.strip() != "true":
        return {
            "is_repository": False,
            "root": None,
            "branch": None,
            "dirty": False,
            "status_lines": [],
        }

    root_result = run_git(target, "rev-parse", "--show-toplevel")
    branch_result = run_git(target, "branch", "--show-current")
    status_result = run_git(target, "status", "--short", "--branch")
    status_lines = [line for line in status_result.stdout.splitlines() if line.strip()]
    worktree_lines = [line for line in status_lines if not line.startswith("##")]
    return {
        "is_repository": True,
        "root": root_result.stdout.strip() or str(target),
        "branch": branch_result.stdout.strip() or None,
        "dirty": bool(worktree_lines),
        "status_lines": status_lines,
    }


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def _package_commands(target: Path) -> list[str]:
    package_path = target / "package.json"
    if not package_path.is_file():
        return []
    try:
        payload = json.loads(package_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return []

    scripts = payload.get("scripts") if isinstance(payload, dict) else None
    if not isinstance(scripts, dict):
        return []

    if (target / "pnpm-lock.yaml").exists():
        runner = "pnpm"
    elif (target / "yarn.lock").exists():
        runner = "yarn"
    elif (target / "bun.lock").exists() or (target / "bun.lockb").exists():
        runner = "bun"
    else:
        runner = "npm"

    commands: list[str] = []
    for name in ("test", "lint", "typecheck", "type-check", "check", "build"):
        if name not in scripts:
            continue
        if runner == "npm" and name == "test":
            command = "npm test"
        else:
            command = f"{runner} run {name}"
        if command not in commands:
            commands.append(command)
    return commands


def detect_project(target: Path) -> dict[str, Any]:
    markers: list[str] = []
    kinds: list[str] = []
    commands: list[str] = []

    if (target / "package.json").is_file():
        markers.append("package.json")
        kinds.append("Node.js/JavaScript")
        commands.extend(_package_commands(target))

    python_marker = next(
        (name for name in ("pyproject.toml", "requirements.txt", "setup.py") if (target / name).is_file()),
        None,
    )
    if python_marker:
        markers.append(python_marker)
        kinds.append("Python")
        pyproject = _read_text(target / "pyproject.toml").lower()
        has_pytest_files = any((target / "tests").glob("test_*.py")) if (target / "tests").is_dir() else False
        if "pytest" in pyproject or has_pytest_files:
            commands.append("python -m pytest")
        elif (target / "tests").is_dir():
            commands.append("python -m unittest discover -s tests")
        if (target / "src").is_dir():
            commands.append("python -m compileall src")

    marker_commands = (
        ("go.mod", "Go", "go test ./..."),
        ("Cargo.toml", "Rust", "cargo test"),
        ("pom.xml", "Java/Maven", "mvn test"),
        ("build.gradle", "Java/Gradle", ".\\gradlew.bat test" if os.name == "nt" else "./gradlew test"),
        ("build.gradle.kts", "Kotlin/Gradle", ".\\gradlew.bat test" if os.name == "nt" else "./gradlew test"),
    )
    for marker, kind, command in marker_commands:
        if (target / marker).is_file():
            markers.append(marker)
            kinds.append(kind)
            commands.append(command)

    if any(target.glob("*.sln")) or any(target.glob("*.csproj")):
        markers.append("*.sln/*.csproj")
        kinds.append(".NET")
        commands.append("dotnet test")

    unique_commands = list(dict.fromkeys(commands))
    unique_kinds = list(dict.fromkeys(kinds))
    return {
        "project_type": " + ".join(unique_kinds) if unique_kinds else "通用/未识别",
        "markers": markers,
        "verification_commands": unique_commands,
    }


def template_files(profile: str) -> list[tuple[str, Path]]:
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
    return sorted(result, key=lambda item: item[0].lower())


def path_status(target: Path, relative: str) -> dict[str, Any]:
    path = target / Path(relative)
    if path.is_symlink():
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
    if "CLAUDE.md" in existing_instruction_files and "AGENTS.md" not in existing_instruction_files:
        recommendations.append("Preserve CLAUDE.md and decide explicitly whether AGENTS.md should become the single authoritative entry.")
    if "progress.md" in existing_instruction_files and "PROGRESS.md" not in existing_instruction_files:
        recommendations.append("Existing lowercase progress.md requires a manual state-model merge; do not create a parallel history silently.")
    if "session-handoff.md" in existing_instruction_files and "HANDOFF.md" not in existing_instruction_files:
        recommendations.append("Existing session-handoff.md requires a manual naming/authority decision; do not duplicate handoff state silently.")
    if git["dirty"]:
        recommendations.append("Git worktree is dirty. Preview is safe; apply requires explicit --allow-dirty after overlap inspection.")
    if not project["verification_commands"]:
        recommendations.append("No native verification command was inferred; provide --verification-command before applying.")
    if any(item["manual_merge"] for item in artifacts):
        recommendations.append("Existing harness paths will be skipped and must be merged manually from repository evidence.")
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


def build_replacements(
    *,
    project_name: str,
    objective: str,
    project_type: str,
    profile: str,
    verification_commands: Iterable[str],
) -> dict[str, str]:
    commands = list(dict.fromkeys(command.strip() for command in verification_commands if command.strip()))
    markdown_commands = "\n".join(f"- `{command}`" for command in commands)
    if not markdown_commands:
        markdown_commands = "- `[待补充：项目原生验证命令]`"
    return {
        "{{PROJECT_NAME}}": project_name,
        "{{OBJECTIVE}}": objective,
        "{{PROJECT_TYPE}}": project_type,
        "{{PROFILE}}": profile,
        "{{DATE}}": date.today().isoformat(),
        "{{VERIFICATION_COMMANDS}}": markdown_commands,
        "{{PROJECT_NAME_JSON}}": json.dumps(project_name, ensure_ascii=False),
        "{{PROFILE_JSON}}": json.dumps(profile, ensure_ascii=False),
        "{{PROJECT_TYPE_JSON}}": json.dumps(project_type, ensure_ascii=False),
        "{{VERIFICATION_JSON}}": json.dumps(commands, ensure_ascii=False),
    }


def render_template(source: Path, replacements: dict[str, str]) -> str:
    rendered = source.read_text(encoding="utf-8")
    for token, value in replacements.items():
        rendered = rendered.replace(token, value)
    unresolved = sorted({part.split("}}", 1)[0] + "}}" for part in rendered.split("{{")[1:] if "}}" in part})
    if unresolved:
        raise ValueError(f"Unresolved template tokens in {source}: {', '.join(unresolved)}")
    return rendered


def safe_destination(root: Path, relative: str) -> Path:
    destination = root / Path(relative)
    root_resolved = root.resolve()
    parent_resolved = destination.parent.resolve(strict=False)
    if os.path.commonpath([str(root_resolved), str(parent_resolved)]) != str(root_resolved):
        raise ValueError(f"Template destination escapes target: {relative}")
    return destination


def dump_json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
