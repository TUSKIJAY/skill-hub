"""Portability regressions restored from project-harness-engineer: UTF-8 output, BOM, interpreter command."""
from __future__ import annotations

import json
import os
import unittest

from harness_test_support import SCRIPTS, ProjectTestCase

# cp1252 cannot encode Chinese: without forced UTF-8 output these runs crash or emit non-UTF-8 bytes.
LEGACY_CONSOLE = {"PYTHONUTF8": "0", "PYTHONIOENCODING": "cp1252"}
UTF8_BOM = b"\xef\xbb\xbf"
EXIT_USAGE = 2
GENERATED_SCRIPTS = ("check-project-harness.py", "check-startup-doc-budget.py")


class PortabilityTests(ProjectTestCase):
    project_dir_name = "中文 space"

    def test_chinese_output_survives_a_legacy_console_encoding(self):
        self.run_script(SCRIPTS / "audit_harness.py", "--target", self.root, env=LEGACY_CONSOLE)
        preview = self.apply("--project-name", "中文项目", env=LEGACY_CONSOLE)
        self.assertIn("中文 space", preview.stdout)
        self.install("--project-name", "中文项目", env=LEGACY_CONSOLE)
        validation = self.run_script(SCRIPTS / "validate_harness.py", "--target", self.root,
                                     "--min-score", 90, env=LEGACY_CONSOLE)
        self.assertIn("中文 space", validation.stdout)
        ledger = self.root / "scripts/harness_log.py"
        self.run_script(ledger, "append", "--type", "verification", "--summary", "中文测试 — 破折号",
                        env=LEGACY_CONSOLE)
        for args in (("query", "--grep", "中文"), ("show", "--seq", 1), ("tail",)):
            self.assertIn("中文测试 — 破折号", self.run_script(ledger, *args, env=LEGACY_CONSOLE).stdout)
        for name in GENERATED_SCRIPTS:
            result = self.run_script(self.root / "scripts" / name, "--root", self.root, env=LEGACY_CONSOLE)
            self.assertIn("中文 space", result.stdout)

    def test_bom_in_package_json_and_config_is_tolerated(self):
        (self.root / "package.json").write_bytes(UTF8_BOM + b'{"scripts":{"test":"echo ok"}}')
        audit = json.loads(self.run_script(SCRIPTS / "audit_harness.py", "--target", self.root, "--json").stdout)
        self.assertEqual(audit["project"]["verification_commands"], ["npm test"])
        self.install()
        config = self.root / ".harness/config.json"
        config.write_bytes(UTF8_BOM + config.read_bytes())
        self.run_script(self.root / "scripts/check-project-harness.py", "--root", self.root)
        validation = json.loads(self.run_script(SCRIPTS / "validate_harness.py", "--target", self.root,
                                                "--min-score", 90, "--json").stdout)
        self.assertEqual(validation["critical_failures"], [])
        # apply must not mistake a BOM-prefixed config for a profile mismatch.
        repeat = json.loads(self.install().stdout)
        self.assertIsNone(repeat["profile_mismatch"])
        self.assertEqual(repeat["summary"]["create"], 0)

    def test_bom_ledger_is_still_read_and_appended(self):
        self.install()
        ledger = self.root / "scripts/harness_log.py"
        self.run_script(ledger, "append", "--type", "verification", "--summary", "中文测试")
        log = self.root / ".harness/history/log.jsonl"
        log.write_bytes(UTF8_BOM + log.read_bytes())
        self.assertIn("中文测试", self.run_script(ledger, "query", "--grep", "中文").stdout)
        self.assertIn("中文测试", self.run_script(ledger, "show", "--seq", 1).stdout)
        self.run_script(ledger, "append", "--type", "note", "--summary", "第二条")
        self.assertIn("第二条", self.run_script(ledger, "show", "--seq", 2).stdout)

    def test_python_command_override_reaches_every_generated_command(self):
        (self.root / "pyproject.toml").write_text("[tool.pytest.ini_options]\n", encoding="utf-8")
        result = json.loads(self.install("--profile", "governed", "--python-command", "py -3").stdout)
        self.assertEqual(result["python_command"], "py -3")
        config = json.loads(self.read(".harness/config.json"))
        self.assertEqual(config["python_command"], "py -3")
        self.assertIn("py -3 -m pytest", config["verification_commands"])
        self.assertIn("py -3 -m pytest", self.read("INSTRUCTIONS.md"))
        for name in ("AGENTS.md", "PROGRESS.md", "HANDOFF.md", "docs/decisions/index.md",
                     "docs/decisions/decision-template.md", "docs/progress-archive/index.md"):
            with self.subTest(name=name):
                text = self.read(name)
                self.assertIn("py -3 scripts/", text)
                self.assertNotIn("python scripts/", text)
                self.assertNotIn("{{", text)

    def test_default_python_command_follows_the_platform(self):
        self.install()
        expected = "python" if os.name == "nt" else "python3"
        self.assertEqual(json.loads(self.read(".harness/config.json"))["python_command"], expected)
        self.assertIn(f"`{expected} scripts/harness_log.py show --seq <N>`", self.read("AGENTS.md"))

    def test_invalid_python_command_is_rejected_before_any_write(self):
        for bad in ("", "   ", "py -3\nrm -rf x"):
            with self.subTest(bad=bad):
                result = self.apply("--python-command", bad, "--apply", expected=EXIT_USAGE)
                self.assertIn("--python-command", result.stderr)
                self.assertEqual(list(self.root.iterdir()), [])

    def test_unreadable_package_json_warns_instead_of_failing_silently(self):
        (self.root / "package.json").write_text("{broken", encoding="utf-8")
        result = self.run_script(SCRIPTS / "audit_harness.py", "--target", self.root)
        self.assertIn("WARNING: cannot read", result.stderr)

    def test_generated_check_script_is_one_self_contained_file(self):
        self.install()
        text = self.read("scripts/check-project-harness.py")
        self.assertNotIn("{{", text)
        self.assertIn("def lint_task_cards", text)
        self.assertNotIn("import harness_", text)
        self.assertEqual(list(self.root.rglob("*.frag")), [])  # fragments are rendered, never installed


if __name__ == "__main__":
    unittest.main()
