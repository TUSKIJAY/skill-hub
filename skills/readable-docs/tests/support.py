"""Shared helpers for the readable-docs tests: temp projects, Git and script runs."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Dict, Optional

SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = SKILL_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import check  # noqa: E402
import rd_common as common  # noqa: E402,F401

GIT_IDENTITY = ["-c", "user.name=readable-docs-test", "-c", "user.email=test@example.invalid",
                "-c", "commit.gpgsign=false", "-c", "core.autocrlf=false"]


def settings(**overrides: object):
    config = check.merge_config(dict({"schema_version": check.CONFIG_SCHEMA}, **overrides))
    return check.build_settings(config)


def rules_at(text: str, rule: str, **overrides: object) -> list:
    return [f for f in check.analyze(text, "doc.md", settings(**overrides)) if f.rule == rule]


class ProjectTestCase(unittest.TestCase):
    """Each test gets an empty project directory under a temp root."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="readable-docs-test-"))
        self.root = self.tmp / "project"
        self.root.mkdir()

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write(self, rel: str, text: str, newline: str = "\n", bom: bool = False) -> Path:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        data = text.replace("\n", newline).encode("utf-8")
        path.write_bytes((b"\xef\xbb\xbf" if bom else b"") + data)
        return path

    def write_json(self, rel: str, data: object) -> Path:
        return self.write(rel, json.dumps(data, ensure_ascii=False, indent=2) + "\n")

    def git(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["git", "-C", str(self.root), *GIT_IDENTITY, *args],
                              capture_output=True, check=True)

    def git_init(self, commit: bool = True) -> None:
        self.git("init", "-q")
        if commit:
            self.git("add", "-A")
            self.git("commit", "-q", "-m", "base")

    def run_script(self, name: str, *args: object, expected: Optional[int] = 0,
                   env: Optional[Dict[str, str]] = None) -> subprocess.CompletedProcess:
        full_env = dict(os.environ, **(env or {}))
        result = subprocess.run([sys.executable, str(SCRIPTS / name), *map(str, args)],
                                capture_output=True, cwd=str(self.root), env=full_env)
        if expected is not None and result.returncode != expected:
            self.fail(f"{name} {args} exited {result.returncode}, expected {expected}\n"
                      f"stdout: {result.stdout.decode('utf-8', 'replace')}\n"
                      f"stderr: {result.stderr.decode('utf-8', 'replace')}")
        return result

    def run_json(self, name: str, *args: object, expected: Optional[int] = 0) -> dict:
        return json.loads(self.run_script(name, *args, expected=expected).stdout.decode("utf-8"))

    def snapshot(self) -> Dict[str, bytes]:
        return {p.relative_to(self.root).as_posix(): p.read_bytes()
                for p in self.root.rglob("*") if p.is_file() and ".git" not in p.parts}
