"""Plan walkthrough rules: the rule card item, the rules file and the SKILL.md link."""

from __future__ import annotations

from support import SKILL_ROOT, ProjectTestCase, check, common

HARNESS_CONFIG = {"schema_version": "project-harness-config-v1", "python_command": "py -3",
                  "verification_commands": ["py -3 scripts/a.py"]}
WALKTHROUGH_RULES = SKILL_ROOT / "rules" / "plan-walkthrough.md"
CARD_PHRASES = ("流程要求先问的场合", "逐段讲")


def non_id_findings(text: str, name: str) -> list:
    findings = check.analyze(text, name, check.build_settings(check.load_config(None)))
    return [f for f in findings if f.rule != "unregistered-id"]


class RuleCardWalkthroughTests(ProjectTestCase):
    def make_harness(self) -> None:
        self.write("README.md", "# 项目\n\n说明。\n")
        self.write("AGENTS.md", "# AGENTS\n\n启动先读 INSTRUCTIONS。\n")
        self.write("INSTRUCTIONS.md", "# 说明\n\n## Learned Constraints\n\n| 触发 | 入口 |\n| --- | --- |\n")
        self.write_json(".harness/config.json", HARNESS_CONFIG)
        self.write("scripts/harness_log.py", "# ledger stub\n")

    def test_rule_card_asset_has_the_walkthrough_item(self):
        card = common.RULE_CARD_ASSET.read_text(encoding="utf-8")
        for phrase in CARD_PHRASES:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, card)
        numbers = [line.split(".", 1)[0] for line in card.splitlines() if line[:1].isdigit()]
        self.assertEqual(numbers, [str(n) for n in range(1, 9)])

    def test_applied_rule_card_carries_the_item_and_the_version(self):
        self.make_harness()
        self.run_json("apply.py", "--target", self.root, "--use-draft", "--apply")
        instructions = (self.root / "INSTRUCTIONS.md").read_text(encoding="utf-8")
        section = instructions[instructions.index("## 给人看的文字"):]
        for phrase in CARD_PHRASES:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, section)
        self.assertIn(f"{common.RULE_CARD_MARKER} v{check.CHECK_VERSION} -->", section)
        self.assertGreaterEqual(tuple(map(int, check.CHECK_VERSION.split("."))), (0, 1, 2))
        self.assertEqual(non_id_findings(section, "card.md"), [])


class WalkthroughRulesFileTests(ProjectTestCase):
    def test_rules_file_exists_and_is_readable_itself(self):
        self.assertTrue(WALKTHROUGH_RULES.is_file())
        text = WALKTHROUGH_RULES.read_text(encoding="utf-8")
        self.assertEqual(non_id_findings(text, "plan-walkthrough.md"), [])

    def test_skill_md_links_the_rules_file(self):
        skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("](rules/plan-walkthrough.md)", skill)
        self.assertIn("`rules/plan-walkthrough.md`", skill)
