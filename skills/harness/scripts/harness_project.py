#!/usr/bin/env python3
"""Project inspection: repository state and verification-command detection."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from harness_portability import read_json_file, read_text_or_empty


def run_git(target: Path, *args: str) -> subprocess.CompletedProcess[str]:
    # --no-optional-locks: `git status` must not refresh the index, so preview and audit stay write-free.
    # core.fsmonitor=false: never run a hook the target project configured.
    command = ["git", "--no-optional-locks", "-c", "core.fsmonitor=false", "-C", str(target), *args]
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
    # A failed `git status` (for example a corrupt index) proves nothing about the worktree: treat it as
    # dirty so --apply still needs explicit --allow-dirty.
    status_error = status_result.stderr.strip()[-300:] if status_result.returncode != 0 else None
    return {
        "is_repository": True,
        "root": root_result.stdout.strip() or str(target),
        "branch": branch_result.stdout.strip() or None,
        "dirty": bool(worktree_lines) or status_error is not None,
        "status_lines": status_lines,
        "status_error": status_error,
    }


def _package_commands(target: Path) -> list[str]:
    package_path = target / "package.json"
    if not package_path.is_file():
        return []
    try:
        payload = read_json_file(package_path)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        print(f"WARNING: cannot read {package_path}: {exc}", file=sys.stderr)
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
        pyproject = read_text_or_empty(target / "pyproject.toml").lower()
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
        "project_type": " + ".join(unique_kinds) if unique_kinds else "通用项目（按实际材料与产物验收）",
        "markers": markers,
        "verification_commands": unique_commands,
    }
