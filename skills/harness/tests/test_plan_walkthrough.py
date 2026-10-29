"""Plan walkthrough gate: the roadmap Lifecycle step, the governed docs sentences, merge hint and validator warning."""
from __future__ import annotations

import json
import sys
import unittest

from harness_test_support import SCRIPTS, SKILL, ProjectTestCase

sys.path.insert(0, str(SCRIPTS))
import harness_merge  # noqa: E402

ROADMAP = "docs/exec-plans/roadmap.md"
ROADMAP_TEMPLATE = SKILL / "assets/governed/docs/exec-plans/roadmap.md.tmpl"
STEP_LINE = "5. " + harness_merge.ROADMAP_WALKTHROUGH_STEP + "\n"
# Each governed file with a sentence of the gate it must carry (the roadmap step is checked on its own).
GOVERNED_SENTENCES = {
    "docs/README.md": "评审结论为 approve、计划移入 `active/` 之前，agent 先问用户要不要听一遍讲解",
    "docs/exec-plans/reviews/index.md": "agreement between agents is not a decision",
    "docs/exec-plans/reviews/review-template.md": "An approve verdict ends the review, not the decision",
    "docs/exec-plans/plan-template.md": "- Walkthrough offer: 评审结论为 approve 后、激活前，agent 问用户要不要听讲解",
    "docs/exec-plans/active/index.md": "Explicit review, walkthrough offer and user approval required",
    "docs/optimization/SOP.md": "proposed 计划评审通过后，agent 先问用户要不要听讲解",
}


class PlanWalkthroughTests(ProjectTestCase):
    def preview(self, *args):
        return json.loads(self.apply("--json", "--acceptance-check", "逐项核对产物与来源", *args).stdout)

    def hints(self, *args):
        return {hint["path"]: hint for hint in self.preview(*args)["manual_merge"]}

    def validate(self):
        return json.loads(self.run_script(SCRIPTS / "validate_harness.py", "--target", self.root, "--json").stdout)

    def walkthrough_warnings(self):
        return [w for w in self.validate()["warnings"] if "人类讲解评审" in w]

    def test_template_and_constant_agree(self):
        self.assertIn(STEP_LINE, ROADMAP_TEMPLATE.read_text(encoding="utf-8"))
        self.assertIn("人类讲解评审", harness_merge.ROADMAP_WALKTHROUGH_STEP)
        self.assertNotIn("{{", harness_merge.ROADMAP_WALKTHROUGH_STEP)

    def test_governed_install_carries_the_gate(self):
        self.install("--profile", "governed")
        roadmap = self.read(ROADMAP)
        self.assertIn(STEP_LINE, roadmap)
        self.assertIn("6. 经用户批准后，计划移动到 `active/`", roadmap)
        self.assertIn("9. 全部范围完成、验证和收尾后", roadmap)
        self.assertIn("- `proposed/`：草案计划，等待讲解询问和用户批准。\n", roadmap)
        for relative, sentence in GOVERNED_SENTENCES.items():
            self.assertIn(sentence, self.read(relative), relative)
        self.assertEqual(self.walkthrough_warnings(), [])
        self.assertEqual(self.preview("--profile", "governed")["manual_merge"], [])

    def test_roadmap_lacking_the_step_gets_the_snippet_and_a_warning(self):
        self.install("--profile", "governed")
        (self.root / ROADMAP).write_text(self.read(ROADMAP).replace(STEP_LINE, ""), encoding="utf-8")
        hints = self.hints("--profile", "governed")
        self.assertEqual(list(hints), [ROADMAP])
        hint = hints[ROADMAP]
        self.assertEqual(hint["missing"], [harness_merge.ROADMAP_WALKTHROUGH_LABEL])
        self.assertEqual(hint["snippet"], harness_merge.ROADMAP_WALKTHROUGH_STEP + "\n")
        self.assertIn("active/", hint["note"])
        result = self.validate()
        self.assertEqual(result["overall_score"], 100)
        self.assertEqual(len(self.walkthrough_warnings()), 1, result["warnings"])

    def test_minimal_install_is_not_affected(self):
        self.install()
        self.assertEqual(self.walkthrough_warnings(), [])
        self.assertNotIn(ROADMAP, self.hints())


if __name__ == "__main__":
    unittest.main()
