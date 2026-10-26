"""CLAUDE.md pointer: installed when missing, never overwritten, linted, and offered as a merge hint."""
from __future__ import annotations

import json
import sys
import unittest

from harness_test_support import SCRIPTS, SKILL, ProjectTestCase

sys.path.insert(0, str(SCRIPTS))
import harness_merge  # noqa: E402

EXIT_FAIL = 1


class EntryPointerTests(ProjectTestCase):
    def preview(self):
        return json.loads(self.apply("--json", "--acceptance-check", "逐项核对产物与来源").stdout)

    def hints(self):
        return {hint["path"]: hint for hint in self.preview()["manual_merge"]}

    def validate(self):
        return json.loads(self.run_script(SCRIPTS / "validate_harness.py", "--target", self.root, "--json").stdout)

    def project_check(self, expected=0):
        return json.loads(self.run_script(self.root / "scripts/check-project-harness.py", "--root", self.root,
                                          expected=expected).stdout)

    def audit(self):
        return json.loads(self.run_script(SCRIPTS / "audit_harness.py", "--target", self.root, "--json").stdout)

    def test_template_is_the_one_line_constant(self):
        template = (SKILL / "assets/minimal/CLAUDE.md.tmpl").read_text(encoding="utf-8")
        self.assertEqual(template, harness_merge.CLAUDE_POINTER_LINE + "\n")
        self.assertEqual(template.count("\n"), 1)
        self.assertIn("@AGENTS.md", template)

    def test_new_install_writes_the_pointer_and_nothing_warns(self):
        self.install()
        self.assertEqual(self.read("CLAUDE.md"), harness_merge.CLAUDE_POINTER_LINE + "\n")
        self.assertNotIn("CLAUDE.md", self.hints())
        self.assertFalse(any("CLAUDE.md" in w for w in self.validate()["warnings"]))
        self.assertTrue(self.project_check()["passed"])
        self.assertFalse(any("CLAUDE.md" in r for r in self.audit()["recommendations"]))

    def test_existing_claude_md_is_kept_and_gets_the_line_as_a_hint(self):
        own = "# 项目说明\n\n用 pnpm。\n"
        (self.root / "CLAUDE.md").write_text(own, encoding="utf-8")
        hint = self.hints()["CLAUDE.md"]
        self.assertEqual(hint["snippet"], harness_merge.CLAUDE_POINTER_LINE + "\n")
        self.assertEqual(hint["missing"], ["one-line pointer to AGENTS.md (@AGENTS.md import)"])
        self.assertTrue(any("does not point to AGENTS.md" in r for r in self.audit()["recommendations"]))
        self.install()
        self.assertEqual(self.read("CLAUDE.md"), own)
        self.assertTrue(any("CLAUDE.md 没有指向 AGENTS.md" in w for w in self.validate()["warnings"]))
        self.assertEqual(self.validate()["overall_score"], 100)
        lint = self.project_check(expected=EXIT_FAIL)["lint_failures"]
        self.assertTrue(any(label.startswith("CLAUDE.md points to") for label in lint), lint)
        with (self.root / "CLAUDE.md").open("a", encoding="utf-8", newline="\n") as handle:
            handle.write("\n" + hint["snippet"])
        self.assertTrue(self.project_check()["passed"])
        self.assertNotIn("CLAUDE.md", self.hints())
        self.assertFalse(any("CLAUDE.md" in w for w in self.validate()["warnings"]))
        self.assertFalse(any("CLAUDE.md" in r for r in self.audit()["recommendations"]))

    def test_missing_claude_md_only_warns_and_a_rerun_installs_it(self):
        self.install()
        (self.root / "CLAUDE.md").unlink()
        result = self.validate()
        self.assertEqual(result["overall_score"], 100)
        self.assertTrue(any("CLAUDE.md 缺失" in w for w in result["warnings"]), result["warnings"])
        self.assertTrue(self.project_check()["passed"])  # the project lint only judges a CLAUDE.md that exists
        created = [item["path"] for item in json.loads(self.install().stdout)["plan"] if item["status"] == "create"]
        self.assertEqual(created, ["CLAUDE.md"])

    def test_pointer_match_is_case_insensitive(self):
        (self.root / "CLAUDE.md").write_text("See agents.md first.\n", encoding="utf-8")
        self.assertNotIn("CLAUDE.md", self.hints())
        self.install()
        self.assertTrue(self.project_check()["passed"])

    def test_older_project_check_is_asked_to_merge_the_pointer_lint(self):
        self.install()
        script = self.root / "scripts/check-project-harness.py"
        script.write_text(self.read("scripts/check-project-harness.py").replace("lint_entry_pointer", "older_name"),
                          encoding="utf-8")
        hint = self.hints()["scripts/check-project-harness.py"]
        self.assertEqual(hint["missing"], ["CLAUDE.md pointer lint (lint_entry_pointer)"])


if __name__ == "__main__":
    unittest.main()
