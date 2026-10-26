"""Shared helpers for the newer skill regressions; not a test module itself."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
SCRIPTS = SKILL / "scripts"
# Every script forces UTF-8 output, so the parent always decodes UTF-8 strictly:
# a child that wrote in the console code page instead would fail the decode.
CHILD_OUTPUT_ENCODING = "utf-8"
EXIT_OK = 0


class ProjectTestCase(unittest.TestCase):
    """Each test gets an empty project directory inside a fresh temporary folder."""

    project_dir_name = "project"

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory(prefix="harness-test-")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name) / self.project_dir_name
        self.root.mkdir()

    def run_script(self, path: Path, *args: object, expected: int = EXIT_OK,
                   env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            [sys.executable, str(path), *map(str, args)], capture_output=True,
            encoding=CHILD_OUTPUT_ENCODING, cwd=self.root, env=dict(os.environ, **(env or {})),
        )
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        return result

    def apply(self, *args: object, expected: int = EXIT_OK,
              env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        return self.run_script(SCRIPTS / "apply_harness.py", "--target", self.root, *args,
                               expected=expected, env=env)

    def install(self, *args: object, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        """Apply with --json and a declared acceptance check, so validation can reach 100."""
        return self.apply("--json", "--acceptance-check", "逐项核对产物与来源", "--apply", *args, env=env)

    def read(self, relative: str) -> str:
        return (self.root / relative).read_text(encoding="utf-8")
