"""`harness_log.py show`: explain a cited ledger entry by seq or id."""
from __future__ import annotations

import json
import unittest

from harness_test_support import ProjectTestCase

EXIT_NOT_FOUND = 1
EXIT_USAGE = 2


def entry(seq: int, summary: str, **extra: str) -> dict:
    return {"seq": seq, "ts": "2026-10-23T10:00:00+08:00", "type": "decision", "summary": summary,
            "evidence": None, "refs": [], "actor": "agent", **extra}


class LedgerShowTests(ProjectTestCase):
    def setUp(self):
        super().setUp()
        self.install()
        self.ledger = self.root / "scripts/harness_log.py"

    def write_ledger(self, *entries: dict) -> None:
        log = self.root / ".harness/history/log.jsonl"
        log.parent.mkdir(parents=True, exist_ok=True)
        lines = "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in entries)
        log.write_text(lines, encoding="utf-8")

    def show(self, *args: object, expected: int = 0):
        return self.run_script(self.ledger, "show", *args, expected=expected)

    def test_show_by_seq_prints_only_that_entry(self):
        self.write_ledger(entry(1, "第一条"), entry(2, "批准方案"), entry(3, "第三条"))
        result = self.show("--seq", 2)
        self.assertIn("批准方案", result.stdout)
        self.assertNotIn("第一条", result.stdout)
        self.assertNotIn("第三条", result.stdout)
        records = [json.loads(line) for line in self.show("--seq", 2, "--format", "json").stdout.splitlines()]
        self.assertEqual([item["summary"] for item in records], ["批准方案"])

    def test_show_by_id_and_query_expose_the_id(self):
        self.write_ledger(entry(1, "旧条目"), entry(2, "合并完成", id="c6098c"))
        result = self.show("--id", "c6098c")
        self.assertIn("seq 2 id c6098c", result.stdout)
        self.assertIn("合并完成", result.stdout)
        self.assertNotIn("旧条目", result.stdout)
        self.assertIn("合并完成", self.run_script(self.ledger, "query", "--grep", "c6098c").stdout)

    def test_not_found_exits_one_with_a_reason(self):
        self.show("--seq", 1, expected=EXIT_NOT_FOUND)
        self.write_ledger(entry(1, "第一条", id="aaa111"))
        missing_seq = self.show("--seq", 9, expected=EXIT_NOT_FOUND)
        self.assertEqual(missing_seq.stdout, "")
        self.assertIn("no ledger entry with seq 9", missing_seq.stderr)
        missing_id = self.show("--id", "bbb222", expected=EXIT_NOT_FOUND)
        self.assertIn("no ledger entry with id bbb222", missing_id.stderr)

    def test_id_lookup_on_a_ledger_without_ids_says_so(self):
        self.write_ledger(entry(1, "第一条"), entry(2, "第二条"))
        result = self.show("--id", "abc123", expected=EXIT_NOT_FOUND)
        self.assertIn("no ledger entry has an `id` field", result.stderr)
        self.assertIn("--seq", result.stderr)

    def test_duplicate_seq_prints_all_with_a_note(self):
        self.write_ledger(entry(5, "分支甲", id="aaa111"), entry(5, "分支乙", id="bbb222"))
        result = self.show("--seq", 5)
        self.assertIn("分支甲", result.stdout)
        self.assertIn("分支乙", result.stdout)
        self.assertIn("2 entries share seq 5", result.stderr)
        self.assertNotIn("WARNING", result.stderr)

    def test_duplicate_id_prints_all_with_an_integrity_warning(self):
        self.write_ledger(entry(1, "条目甲", id="abc123"), entry(2, "条目乙", id="abc123"))
        result = self.show("--id", "abc123")
        self.assertIn("条目甲", result.stdout)
        self.assertIn("条目乙", result.stdout)
        self.assertIn("WARNING: 2 entries share id abc123", result.stderr)
        self.assertIn("integrity", result.stderr)

    def test_exactly_one_selector_is_required(self):
        self.write_ledger(entry(1, "第一条"))
        self.show(expected=EXIT_USAGE)
        self.show("--seq", 1, "--id", "abc123", expected=EXIT_USAGE)


if __name__ == "__main__":
    unittest.main()
