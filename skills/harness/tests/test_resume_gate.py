"""Pre-resume gate: the AGENTS Hard Rules bullet, HANDOFF/PROGRESS wording, merge hint and validator warning."""
from __future__ import annotations

import json
import sys
import unittest

from harness_test_support import SCRIPTS, SKILL, ProjectTestCase

sys.path.insert(0, str(SCRIPTS))
import harness_merge  # noqa: E402

GATE_LABEL = "Expensive, irreversible or do_not-named actions wait for the user on resume"


class ResumeGateTests(ProjectTestCase):
    def preview(self):
        return json.loads(self.apply("--json", "--acceptance-check", "逐项核对产物与来源").stdout)

    def hints(self):
        return {hint["path"]: hint for hint in self.preview()["manual_merge"]}

    def validate(self):
        return json.loads(self.run_script(SCRIPTS / "validate_harness.py", "--target", self.root, "--json").stdout)

    def test_template_fragment_and_constant_agree(self):
        bullet = "- " + harness_merge.AGENTS_GATE_SENTENCE + "\n"
        self.assertIn(bullet, (SKILL / "assets/minimal/AGENTS.md.tmpl").read_text(encoding="utf-8"))
        self.assertIn(bullet, (SKILL / "assets/fragments/agents-merge-section.md").read_text(encoding="utf-8"))
        self.assertIn("恢复前闸门", harness_merge.AGENTS_GATE_SENTENCE)
        self.assertNotIn("{{", harness_merge.AGENTS_GATE_SENTENCE)

    def test_generated_files_carry_the_gate(self):
        self.install()
        agents = self.read("AGENTS.md")
        hard = agents.split("## Hard Rules")[1].split("## Verification")[0]
        self.assertIn("- " + harness_merge.AGENTS_GATE_SENTENCE + "\n", hard)
        self.assertIn("不启动后台进程、不建计划任务", hard)
        handoff = self.read("HANDOFF.md")
        self.assertIn("`do_not` 写成无条件、不带时效的闸门", handoff)
        self.assertIn("`first_action` 不能是昂贵或不可逆的动作", handoff)
        self.assertIn("接手时据此核实它是否仍在跑", self.read("PROGRESS.md"))
        self.assertFalse(any("恢复前闸门" in w for w in self.validate()["warnings"]))
        self.assertEqual(self.preview()["manual_merge"], [])

    def test_agents_lacking_only_the_gate_gets_the_sentence_and_a_warning(self):
        self.install()
        agents = self.root / "AGENTS.md"
        agents.write_text(self.read("AGENTS.md").replace("- " + harness_merge.AGENTS_GATE_SENTENCE + "\n", ""),
                          encoding="utf-8")
        hint = self.hints()["AGENTS.md"]
        self.assertEqual(hint["missing"], [GATE_LABEL])
        self.assertEqual(hint["snippet"], harness_merge.AGENTS_GATE_SENTENCE + "\n")
        self.assertIn("Hard Rules", hint["note"])
        result = self.validate()
        self.assertEqual(result["overall_score"], 100)
        self.assertTrue(any("恢复前闸门" in w for w in result["warnings"]), result["warnings"])

    def test_rendered_merge_section_carries_the_gate(self):
        for is_git in (True, False):
            self.assertIn("- " + harness_merge.AGENTS_GATE_SENTENCE + "\n",
                          harness_merge.render_agents_section(is_git, "python"))


if __name__ == "__main__":
    unittest.main()
