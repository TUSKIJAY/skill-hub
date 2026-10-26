"""Regressions for the opt-in hooks component (--hooks); development only, never installed."""
from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

from harness_test_support import CHILD_OUTPUT_ENCODING, SCRIPTS, ProjectTestCase

EXIT_BLOCK = 2
MAX_STDERR_LINES = 3
HOOK = "scripts/harness_hook.py"
SETTINGS = ".claude/settings.json"
LEDGER = ".harness/history/log.jsonl"
HUMAN_PENDING = "| A2 | human | 上板观察 | 灯亮 |  | 待人工验收 |  |  |"
HUMAN_PASSED = "| A2 | human | 上板观察 | 灯亮 | photos/a2.jpg | 已通过 | 王工 | 2026-10-25 |"
SCRIPT_PENDING = "| A1 | script | `run-check` | 输出 ok |  | 待执行 |  |  |"
SCRIPT_RUN = "| A1 | script | `run-check` | 输出 ok | logs/a1.txt | 已执行 |  |  |"


def card(*rows: str, status: str = "实施中") -> str:
    return "\n".join([
        "# TASK-001-demo：演示", "", f"status: {status}", "requirements: REQ-1", "acceptance_owner: 王工", "",
        "## 目标", "", "演示。", "", "## 验收项", "",
        "| ID | 方式 | 步骤或命令 | 预期 | 证据位置 | 状态 | 记录人 | 时间 |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |", *rows, "", "## 结论", "", "待定。", "",
    ])


class HooksTestCase(ProjectTestCase):
    def hook(self, payload: dict, *args: str) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            [sys.executable, str(self.root / HOOK), *args], input=json.dumps(payload, ensure_ascii=False),
            capture_output=True, encoding=CHILD_OUTPUT_ENCODING, cwd=self.root,
        )
        self.assertLessEqual(len(result.stderr.splitlines()), MAX_STDERR_LINES, result.stderr)
        return result

    def assert_silent_pass(self, result: subprocess.CompletedProcess[str]) -> None:
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, "", ""))

    def assert_blocked(self, result: subprocess.CompletedProcess[str], needle: str) -> None:
        self.assertEqual(result.returncode, EXIT_BLOCK, result.stdout + result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertIn(needle, result.stderr)

    def shell(self, command: str, tool: str = "Bash", cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
        return self.hook({"hook_event_name": "PreToolUse", "tool_name": tool, "cwd": str(cwd or self.root),
                          "tool_input": {"command": command}})

    def file_tool(self, tool: str, relative: str, **tool_input: object) -> subprocess.CompletedProcess[str]:
        return self.hook({"hook_event_name": "PreToolUse", "tool_name": tool, "cwd": str(self.root),
                          "tool_input": {"file_path": str(self.root / relative), **tool_input}})

    def stop(self, active: bool = False) -> subprocess.CompletedProcess[str]:
        return self.hook({"hook_event_name": "Stop", "stop_hook_active": active})

    def ledger(self, *args: str) -> None:
        self.run_script(self.root / "scripts/harness_log.py", *args)

    def config(self) -> dict:
        return json.loads(self.read(".harness/config.json"))

    def write_config(self, config: dict) -> None:
        (self.root / ".harness/config.json").write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")

    def put(self, relative: str, text: str) -> None:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def git(self, *args: str) -> None:
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args], cwd=self.root,
                       check=True, capture_output=True)


class InstallTests(HooksTestCase):
    def test_default_install_has_no_hooks(self):
        payload = json.loads(self.install().stdout)
        self.assertIsNone(payload["hooks"])
        self.assertFalse((self.root / HOOK).exists())
        self.assertFalse((self.root / SETTINGS).exists())
        self.assertNotIn("hooks", self.config())

    def test_hooks_install_creates_missing_files_with_exec_form_handlers(self):
        payload = json.loads(self.install("--hooks", "--python-command", "py -3").stdout)
        self.assertEqual(payload["hooks"]["manual_merge"], [])
        self.assertEqual(self.config()["hooks"], {"enabled": True})
        settings = json.loads(self.read(SETTINGS))["hooks"]
        matchers = [entry["matcher"] for entry in settings["PreToolUse"]]
        self.assertEqual(matchers, ["Edit|Write|MultiEdit", "Bash|PowerShell"])
        handlers = [hook for entries in settings.values() for entry in entries for hook in entry["hooks"]]
        self.assertEqual(len(handlers), 3)
        for handler in handlers:
            self.assertEqual(handler, {"type": "command", "command": "py",
                                       "args": ["-3", "${CLAUDE_PROJECT_DIR}/scripts/harness_hook.py"]})
        self.assertIn("exec py -3 scripts/harness_hook.py --git-pre-commit", payload["hooks"]["pre_commit"])

    def test_existing_settings_is_kept_and_gets_a_merge_hint(self):
        original = '{\n  "permissions": {"allow": ["Bash(ls)"]}\n}\n'
        self.put(SETTINGS, original)
        payload = json.loads(self.install("--hooks").stdout)
        self.assertEqual(self.read(SETTINGS), original)
        self.assertTrue((self.root / HOOK).is_file())
        hints = [hint for hint in payload["manual_merge"] if hint["path"] == SETTINGS]
        self.assertEqual(len(hints), 1)
        self.assertEqual(hints[0]["kind"], "hooks")
        self.assertIn("harness_hook.py", json.dumps(json.loads(hints[0]["snippet"])))
        preview = self.apply("--hooks").stdout
        self.assertIn("----- BEGIN harness merge section -----", preview)
        self.assertIn('"Stop"', preview)

    def test_settings_that_already_run_the_hook_need_no_hint(self):
        self.put(SETTINGS, '{"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "python", '
                           '"args": ["scripts/harness_hook.py"]}]}]}}\n')
        payload = json.loads(self.install("--hooks").stdout)
        self.assertEqual([hint for hint in payload["manual_merge"] if hint["path"] == SETTINGS], [])

    def test_rerun_on_installed_harness_lists_the_config_merge(self):
        self.install()
        payload = json.loads(self.apply("--json", "--hooks").stdout)
        self.assertEqual(payload["hooks"]["manual_merge"], ['.harness/config.json: add "hooks": {"enabled": true}'])
        self.assertIn({"path": HOOK, "status": "create"},
                      [{"path": item["path"], "status": item["status"]} for item in payload["plan"]])

    def test_validation_checks_hooks_only_when_configured(self):
        self.install()
        report = json.loads(self.run_script(SCRIPTS / "validate_harness.py", "--target", self.root, "--json").stdout)
        self.assertNotIn("hooks", report["categories"])
        self.install("--hooks")
        config = self.config()
        config["hooks"] = {"enabled": True}
        self.write_config(config)
        report = json.loads(self.run_script(SCRIPTS / "validate_harness.py", "--target", self.root, "--json").stdout)
        self.assertEqual(report["categories"]["hooks"]["score"], 100)
        (self.root / HOOK).unlink()
        report = json.loads(self.run_script(SCRIPTS / "validate_harness.py", "--target", self.root, "--json",
                                            expected=1).stdout)
        self.assertIn(HOOK, [item["path"] for item in report["critical_failures"]])


class LedgerRuleTests(HooksTestCase):
    def setUp(self):
        super().setUp()
        self.install("--hooks")

    def test_direct_ledger_writes_are_blocked(self):
        history = self.root / ".harness/history"
        cases = [
            ("echo '{}' >> .harness/history/log.jsonl", "Bash", None),
            ("printf x | tee -a .harness/history/log.jsonl", "Bash", None),
            ("sed -i '' 's/a/b/' log.jsonl", "Bash", history),
            ("cp /tmp/other.jsonl .harness/history/log.jsonl", "Bash", None),
            ("rm -f .harness/history/log.jsonl", "Bash", None),
            ('python -c "open(\'.harness/history/log.jsonl\', \'a\').write(\'x\')"', "Bash", None),
            ("Add-Content -Path .harness\\history\\log.jsonl -Value x", "PowerShell", None),
            ("Get-Date | Out-File -Append .harness/history/log.jsonl", "PowerShell", None),
        ]
        for command, tool, cwd in cases:
            with self.subTest(command=command):
                self.assert_blocked(self.shell(command, tool, cwd), "scripts/harness_log.py append")
        for tool, extra in (("Write", {"content": "{}\n"}), ("Edit", {"old_string": "a", "new_string": "b"})):
            with self.subTest(tool=tool):
                self.assert_blocked(self.file_tool(tool, LEDGER, **extra), "harness_log.py append")

    def test_reads_and_the_ledger_script_pass_silently(self):
        for command in ("tail -5 .harness/history/log.jsonl | grep seq 2>&1",
                        "cp .harness/history/log.jsonl /tmp/ledger-copy.jsonl",
                        "git add .harness/history/log.jsonl",
                        'python scripts/harness_log.py append --type note --summary "x" > /dev/null',
                        "echo hi > notes/log.jsonl",
                        "Get-Content .harness\\history\\log.jsonl"):
            with self.subTest(command=command):
                self.assert_silent_pass(self.shell(command))

    def test_enabled_false_turns_every_rule_off(self):
        config = self.config()
        config["hooks"]["enabled"] = False
        self.write_config(config)
        self.assert_silent_pass(self.shell("echo x >> .harness/history/log.jsonl"))


class ExternalWriteRuleTests(HooksTestCase):
    def setUp(self):
        super().setUp()
        self.install("--hooks")

    def test_rule_is_absent_without_the_field(self):
        self.assert_silent_pass(self.shell("curl -X POST https://example.com/api"))

    def test_declared_write_needs_an_open_intent_last(self):
        config = self.config()
        config["hooks"]["external_writes"] = ["curl -X POST"]
        self.write_config(config)
        command = "curl -X POST https://example.com/api"
        self.assert_blocked(self.shell(command), "--type intent")
        self.assert_silent_pass(self.shell(
            'python scripts/harness_log.py append --type intent --summary "准备 curl -X POST" --evidence k1'))
        self.ledger("append", "--type", "intent", "--summary", "准备提交", "--evidence", "key-1")
        self.assert_silent_pass(self.shell(command))
        self.ledger("append", "--type", "milestone", "--summary", "已提交", "--closes", "1")
        self.assert_blocked(self.shell(command), "not an open intent")


class HumanAcceptanceRuleTests(HooksTestCase):
    CARD = "docs/tasks/TASK-001-demo.md"

    def setUp(self):
        super().setUp()
        self.install("--hooks", "--task-cards")
        self.put(self.CARD, card(SCRIPT_PENDING, HUMAN_PENDING))

    def test_agent_cannot_record_a_human_result(self):
        self.assert_blocked(self.file_tool("Edit", self.CARD, old_string=HUMAN_PENDING, new_string=HUMAN_PASSED),
                            "human acceptance item(s) A2")
        failed = HUMAN_PENDING.replace("|  | 待人工验收 |", "| photos/a2.jpg | 未通过 |")
        self.assert_blocked(self.file_tool("Edit", self.CARD, old_string=HUMAN_PENDING, new_string=failed), "A2")
        recorder_only = HUMAN_PENDING.replace("|  |  |", "| 王工 |  |")
        self.assert_blocked(self.file_tool("Edit", self.CARD, old_string=HUMAN_PENDING, new_string=recorder_only),
                            "A2")

    def test_changing_the_method_first_is_no_way_around(self):
        edits = [{"old_string": "| A2 | human |", "new_string": "| A2 | script |"},
                 {"old_string": "|  | 待人工验收 |", "new_string": "| logs/a2.txt | 已通过 |"}]
        self.assert_blocked(self.file_tool("MultiEdit", self.CARD, edits=edits), "A2")

    def test_new_card_written_with_a_human_result_is_blocked(self):
        self.assert_blocked(self.file_tool("Write", "docs/tasks/TASK-002-new.md",
                                           content=card(SCRIPT_PENDING, HUMAN_PASSED)), "TASK-002-new.md")

    def test_script_items_and_other_text_pass_silently(self):
        self.assert_silent_pass(self.file_tool("Edit", self.CARD, old_string=SCRIPT_PENDING, new_string=SCRIPT_RUN))
        self.assert_silent_pass(self.file_tool("Edit", self.CARD, old_string="演示。", new_string="演示，改了说明。"))
        self.put(self.CARD, card(SCRIPT_PENDING, HUMAN_PASSED))
        self.assert_silent_pass(self.file_tool("Edit", self.CARD, old_string="待定。", new_string="已完成。"))

    def test_files_outside_the_card_directory_are_not_checked(self):
        self.put("docs/notes/TASK-001-demo.md", card(HUMAN_PENDING))
        self.assert_silent_pass(self.file_tool("Edit", "docs/notes/TASK-001-demo.md",
                                               old_string=HUMAN_PENDING, new_string=HUMAN_PASSED))

    def test_without_task_cards_configured_the_rule_is_off(self):
        config = self.config()
        del config["task_cards"]
        self.write_config(config)
        self.assert_silent_pass(self.file_tool("Edit", self.CARD, old_string=HUMAN_PENDING, new_string=HUMAN_PASSED))

    def test_post_tool_use_relints_cards_after_a_shell_change(self):
        inconsistent = HUMAN_PENDING.replace("|  | 待人工验收 |", "|  | 已通过 |")
        self.put(self.CARD, card(SCRIPT_PENDING, inconsistent))
        payload = {"hook_event_name": "PostToolUse", "tool_name": "Bash", "cwd": str(self.root)}
        self.assert_blocked(self.hook({**payload, "tool_input": {"command": "python fix.py docs/tasks/TASK-001-demo.md"}}),
                            "Task-card lint fails")
        self.assert_silent_pass(self.hook({**payload, "tool_input": {"command": "ls"}}))


class StopRuleTests(HooksTestCase):
    def setUp(self):
        super().setUp()
        self.install("--hooks", "--task-cards")

    def test_untouched_install_passes_silently(self):
        self.assert_silent_pass(self.stop())

    def test_open_intent_blocks_once(self):
        self.ledger("append", "--type", "intent", "--summary", "准备发布", "--evidence", "key-1")
        self.assert_blocked(self.stop(), "open ledger intent")
        self.assert_silent_pass(self.stop(active=True))
        self.ledger("append", "--type", "milestone", "--summary", "已发布", "--closes", "1")
        self.assert_silent_pass(self.stop())

    def test_failing_project_check_blocks(self):
        handoff = self.read("HANDOFF.md").replace("verify:", "check:")
        self.put("HANDOFF.md", handoff)
        self.assert_blocked(self.stop(), "check-project-harness.py fails")

    def test_startup_budget_warning_blocks(self):
        self.put("HANDOFF.md", self.read("HANDOFF.md") + "".join(f"- 填充 {i}\n" for i in range(80)))
        self.assert_blocked(self.stop(), "over budget")


class GatedActionRuleTests(HooksTestCase):
    def setUp(self):
        super().setUp()
        self.install("--hooks")

    def test_rule_is_absent_without_the_field(self):
        self.assert_silent_pass(self.shell("python run_real.py --all"))

    def test_declared_action_asks_the_user_instead_of_running(self):
        config = self.config()
        config["hooks"]["gated_actions"] = ["run_real.py"]
        self.write_config(config)
        result = self.shell("python run_real.py --all")
        self.assertEqual((result.returncode, result.stderr), (0, ""))
        decision = json.loads(result.stdout)["hookSpecificOutput"]
        self.assertEqual((decision["hookEventName"], decision["permissionDecision"]), ("PreToolUse", "ask"))
        self.assertIn("run_real.py", decision["permissionDecisionReason"])
        self.assertIn("恢复前闸门", decision["permissionDecisionReason"])
        self.assert_silent_pass(self.shell("python scripts/harness_log.py query --grep run_real.py"))
        self.assert_silent_pass(self.shell("dir experiments"))
        result = self.shell("python run_real.py --all", tool="PowerShell")
        self.assertEqual(json.loads(result.stdout)["hookSpecificOutput"]["permissionDecision"], "ask")

    def test_external_write_block_wins_over_the_gate(self):
        config = self.config()
        config["hooks"]["external_writes"] = ["curl -X POST"]
        config["hooks"]["gated_actions"] = ["curl -X POST"]
        self.write_config(config)
        self.assert_blocked(self.shell("curl -X POST https://example.com/api"), "--type intent")


class PreCommitTests(HooksTestCase):
    def setUp(self):
        super().setUp()
        self.git("init", "-q")
        self.install("--hooks", "--allow-dirty")
        self.ledger("append", "--type", "note", "--summary", "一")
        self.ledger("append", "--type", "note", "--summary", "二")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "base")

    def pre_commit(self) -> subprocess.CompletedProcess[str]:
        return subprocess.run([sys.executable, str(self.root / HOOK), "--git-pre-commit"], capture_output=True,
                              encoding=CHILD_OUTPUT_ENCODING, cwd=self.root)

    def test_append_passes_and_rewrite_fails(self):
        self.ledger("append", "--type", "note", "--summary", "三")
        self.git("add", LEDGER)
        result = self.pre_commit()
        self.assertEqual((result.returncode, result.stderr), (0, ""))
        lines = self.read(LEDGER).splitlines(keepends=True)
        (self.root / LEDGER).write_text("".join(lines[1:]), encoding="utf-8")
        self.git("add", LEDGER)
        result = self.pre_commit()
        self.assertEqual(result.returncode, 1)
        self.assertIn("append-only", result.stderr)


if __name__ == "__main__":
    unittest.main()
