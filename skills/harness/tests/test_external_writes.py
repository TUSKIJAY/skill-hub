"""Two-phase external writes: the `intent` entry, `--closes`, `pending`, and the wording and merge hints around them."""
from __future__ import annotations

import json
import sys
import unittest

from harness_test_support import SCRIPTS, SKILL, ProjectTestCase

sys.path.insert(0, str(SCRIPTS))
import harness_merge  # noqa: E402

EXIT_PENDING = 1
EXIT_USAGE = 2
INTENT_LABEL = "External writes are logged as an intent before and closed after"


class LedgerIntentTests(ProjectTestCase):
    def setUp(self):
        super().setUp()
        self.install()
        self.ledger = self.root / "scripts/harness_log.py"

    def log(self, *args, expected=0):
        return self.run_script(self.ledger, *args, expected=expected)

    def entries(self):
        path = self.root / ".harness/history/log.jsonl"
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def test_pending_lists_open_intents_until_a_closing_entry(self):
        self.assertIn("no open intents", self.log("pending").stdout)
        self.log("append", "--type", "intent", "--summary", "准备提交订单 A", "--evidence", "order-key=A-2026")
        result = self.log("pending", expected=EXIT_PENDING)
        self.assertIn("准备提交订单 A", result.stdout)
        self.assertIn("order-key=A-2026", result.stdout)
        self.assertIn("1 open intent", result.stderr)
        self.assertIn("--closes", result.stderr)
        self.log("append", "--type", "milestone", "--summary", "订单 A 已提交", "--evidence", "回执 123", "--closes", 1)
        self.assertEqual(self.entries()[-1]["refs"], ["seq:1"])
        self.assertIn("no open intents", self.log("pending").stdout)

    def test_a_manual_seq_ref_also_closes_and_json_format_works(self):
        self.log("append", "--type", "intent", "--summary", "准备发送通知", "--evidence", "msg-id=7")
        self.log("append", "--type", "incident", "--summary", "发送超时，结果未知", "--refs", "seq:1", "notes.md")
        self.assertIn("no open intents", self.log("pending").stdout)
        self.log("append", "--type", "intent", "--summary", "第二个意图", "--evidence", "k=2")
        lines = self.log("pending", "--format", "json", expected=EXIT_PENDING).stdout.splitlines()
        self.assertEqual([json.loads(line)["summary"] for line in lines], ["第二个意图"])

    def test_closes_is_validated_before_anything_is_appended(self):
        result = self.log("append", "--type", "milestone", "--summary", "x", "--closes", 9, expected=EXIT_USAGE)
        self.assertIn("no ledger entry with seq 9", result.stderr)
        self.log("append", "--type", "milestone", "--summary", "普通里程碑")
        result = self.log("append", "--type", "milestone", "--summary", "y", "--closes", 1, expected=EXIT_USAGE)
        self.assertIn("not an intent entry", result.stderr)
        self.log("append", "--type", "intent", "--summary", "准备 X", "--evidence", "k")
        result = self.log("append", "--type", "intent", "--summary", "准备 Y", "--closes", 2, expected=EXIT_USAGE)
        self.assertIn("cannot close another intent", result.stderr)
        self.assertEqual([item["summary"] for item in self.entries()], ["普通里程碑", "准备 X"])
        self.assertIn("seq 2", self.log("query", "--type", "intent").stdout)


class WordingAndMergeTests(ProjectTestCase):
    def preview(self):
        return json.loads(self.apply("--json", "--acceptance-check", "逐项核对产物与来源").stdout)

    def hints(self):
        return {hint["path"]: hint for hint in self.preview()["manual_merge"]}

    def validate(self):
        return json.loads(self.run_script(SCRIPTS / "validate_harness.py", "--target", self.root, "--json").stdout)

    def python(self):
        return json.loads(self.read(".harness/config.json"))["python_command"]

    def test_template_fragment_and_constant_agree(self):
        bullet = "- " + harness_merge.AGENTS_INTENT_SENTENCE + "\n"
        self.assertIn(bullet, (SKILL / "assets/minimal/AGENTS.md.tmpl").read_text(encoding="utf-8"))
        self.assertIn(bullet, (SKILL / "assets/fragments/agents-merge-section.md").read_text(encoding="utf-8"))
        self.assertIn("--type intent", harness_merge.AGENTS_INTENT_SENTENCE)
        self.assertIn("harness_log.py pending", harness_merge.AGENTS_INTENT_SENTENCE)

    def test_generated_files_carry_the_two_phase_rule(self):
        self.install()
        agents = self.read("AGENTS.md")
        self.assertIn("- " + harness_merge.agents_intent_sentence(self.python()) + "\n", agents)
        startup = agents.split("## Use / Maintain")[0]
        self.assertIn("scripts/harness_log.py pending", startup)
        self.assertIn("核实前不得重做", startup)
        self.assertIn("只读查询可跳过基线确认", startup)
        self.assertIn("|intent>", agents)
        self.assertIn("intent 条目均已用 `--closes` 闭合", agents.split("## Definition of Done")[1])
        self.assertIn("外部写入与核实方式", self.read("INSTRUCTIONS.md"))
        self.assertIn("`verify` 必须写明核实其是否已发生的方法", self.read("HANDOFF.md"))
        self.assertIn("scripts/harness_log.py pending", self.read("PROGRESS.md"))
        self.assertIn("## Procedure promotion", self.read("docs/harness-maintenance.md"))
        warnings = self.validate()["warnings"]
        self.assertFalse(any("intent" in w or "pending" in w for w in warnings), warnings)
        self.assertEqual(self.preview()["manual_merge"], [])

    def test_agents_lacking_only_the_rule_gets_the_sentence_and_a_warning(self):
        self.install()
        sentence = harness_merge.agents_intent_sentence(self.python())
        agents = self.root / "AGENTS.md"
        agents.write_text(self.read("AGENTS.md").replace("- " + sentence + "\n", ""), encoding="utf-8")
        hint = self.hints()["AGENTS.md"]
        self.assertEqual(hint["missing"], [INTENT_LABEL])
        self.assertEqual(hint["snippet"], sentence + "\n")
        self.assertIn("State Discipline", hint["note"])
        result = self.validate()
        self.assertEqual(result["overall_score"], 100)
        self.assertTrue(any("--type intent" in w for w in result["warnings"]), result["warnings"])
        # Both one-sentence gaps at once: one hint carrying both sentences, still no whole section.
        context = harness_merge.agents_context_sentence()
        agents.write_text(self.read("AGENTS.md").replace(context, ""), encoding="utf-8")
        hint = self.hints()["AGENTS.md"]
        self.assertEqual(hint["missing"], ["Reads and output follow the INSTRUCTIONS.md Context Budget", INTENT_LABEL])
        self.assertEqual(hint["snippet"], context + "\n" + sentence + "\n")
        self.assertNotIn("## 状态与交接", hint["snippet"])
        self.assertNotIn("scripts/check-project-harness.py", self.hints())  # no routing gap, no routing-lint hint

    def test_rendered_merge_section_carries_the_rule(self):
        for is_git in (True, False):
            snippet = harness_merge.render_agents_section(is_git, "py -3")
            self.assertIn("- " + harness_merge.agents_intent_sentence("py -3") + "\n", snippet)
            self.assertIn("|intent>", snippet)
            self.assertIn("intent 条目均已闭合", snippet)

    def test_older_ledger_script_is_flagged_and_warned(self):
        self.install()
        script = self.root / "scripts/harness_log.py"
        script.write_text("print('older ledger')\n", encoding="utf-8")
        hint = self.hints()["scripts/harness_log.py"]
        self.assertEqual(hint["missing"], [label for label, _ in harness_merge.LEDGER_SCRIPT_PARTS])
        self.assertIsNone(hint["snippet"])
        result = self.validate()
        self.assertEqual(result["overall_score"], 100)
        self.assertTrue(any("pending" in w for w in result["warnings"]), result["warnings"])


if __name__ == "__main__":
    unittest.main()
