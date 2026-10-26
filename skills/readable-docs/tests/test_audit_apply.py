"""audit.py and apply.py across project shapes: preview purity, placement, no overwrite."""

from __future__ import annotations

import json

from support import ProjectTestCase, check, common

HARNESS_CONFIG = {"schema_version": "project-harness-config-v1", "python_command": "py -3",
                  "verification_commands": ["py -3 scripts/a.py", "py -3 scripts/b.py"]}
DECISION_INDEX = ("# 决策索引\n\n| 决定 | 状态 |\n| --- | --- |\n"
                  "| D0001 快照保存全部字段 | Accepted |\n| D0002 订单范围先行 | Accepted |\n"
                  "| D0003 技术参照 Palantir | Accepted |\n")


class ShapeFixtures(ProjectTestCase):
    def make(self, shape: str) -> None:
        self.write("README.md", "# 项目\n\n说明。\n")
        if shape in ("harness", "agents-instructions"):
            self.write("AGENTS.md", "# AGENTS\n\n启动先读 INSTRUCTIONS。\n")
            self.write("INSTRUCTIONS.md", "# 说明\n\n## Learned Constraints\n\n| 触发 | 入口 |\n| --- | --- |\n")
        if shape == "harness":
            self.write_json(".harness/config.json", HARNESS_CONFIG)
            self.write("scripts/harness_log.py", "# ledger stub\n")
            self.write("docs/decisions/index.md", DECISION_INDEX)
            self.write("docs/exec-plans/plan-template.md", "# 计划模板\n\n- 目标：\n")
            self.write("docs/notes.md", "账本记了（3d4407cc4fe7）。\n")
        if shape == "agents":
            self.write("AGENTS.md", "# AGENTS\n\n规则。\n")
            self.write("CLAUDE.md", "见 AGENTS.md。\n")
        if shape == "claude":
            self.write("CLAUDE.md", "# CLAUDE\n\n规则。\n")

    def apply(self, *extra: object, expected: int = 0, config: dict = None) -> dict:
        args = ["--target", self.root]
        if config is None:
            args.append("--use-draft")
        else:
            path = self.tmp / "confirmed.json"
            path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
            args += ["--config", path]
        return self.run_json("apply.py", *args, *extra, expected=expected)

    def statuses(self, payload: dict) -> dict:
        return {a["kind"]: a["status"] for a in payload["actions"]}


class AuditTests(ShapeFixtures):
    def test_shapes_and_card_targets(self):
        expected = {"harness": "INSTRUCTIONS.md", "agents-instructions": "INSTRUCTIONS.md",
                    "agents": "AGENTS.md", "claude": "CLAUDE.md", "none": None}
        for shape, target in expected.items():
            with self.subTest(shape=shape):
                self.tearDown()
                self.setUp()
                self.make(shape)
                report = self.run_json("audit.py", "--target", self.root)
                self.assertEqual((report["shape"], report["card_target"]), (shape, target))

    def test_harness_draft_uses_records_and_finds_ids(self):
        self.make("harness")
        report = self.run_json("audit.py", "--target", self.root)
        draft = report["config_draft"]
        self.assertEqual(report["config_path"], ".harness/readable-docs.json")
        self.assertEqual(report["python_command"], "py -3")
        self.assertEqual(draft["card"]["id_example"], "D0001（快照保存全部字段）")
        self.assertIn("hex12", [k["name"] for k in draft["id_kinds"]])
        self.assertEqual(report["lookup_sources"]["index_tables"][0]["file"], "docs/decisions/index.md")
        self.assertIn("docs/exec-plans/plan-template.md", report["template_candidates"])
        check.build_settings(check.merge_config(draft))

    def test_draft_follows_whether_the_project_uses_git(self):
        self.make("agents")
        draft = self.run_json("audit.py", "--target", self.root)["config_draft"]
        lookups = [lk for kind in draft["id_kinds"] if kind["name"] == "hex-ref" for lk in kind["lookup"]]
        self.assertEqual(draft["check"], {"changed_only": False})
        self.assertEqual([lk["type"] for lk in lookups], ["manual"])
        check.build_settings(check.merge_config(draft))

        self.git_init()
        draft = self.run_json("audit.py", "--target", self.root)["config_draft"]
        lookups = [lk for kind in draft["id_kinds"] if kind["name"] == "hex-ref" for lk in kind["lookup"]]
        self.assertEqual(draft["check"], {"changed_only": True})
        self.assertEqual([lk["type"] for lk in lookups], ["git"])

    def test_audit_writes_nothing(self):
        self.make("harness")
        before = self.snapshot()
        draft = self.tmp / "draft.json"
        self.run_script("audit.py", "--target", self.root, "--draft-out", draft)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(json.loads(draft.read_text(encoding="utf-8"))["schema_version"], check.CONFIG_SCHEMA)
        self.run_script("audit.py", "--target", self.root, "--draft-out", draft, expected=2)
        self.run_script("audit.py", "--target", self.root, "--draft-out", self.root / "README.md", expected=2)
        self.run_script("audit.py", "--target", self.root, "--draft-out", self.root / "new.json", expected=2)
        self.assertEqual(self.snapshot(), before)


class ApplyTests(ShapeFixtures):
    def test_preview_writes_nothing_in_any_shape(self):
        for shape in ("harness", "agents-instructions", "agents", "claude", "none"):
            with self.subTest(shape=shape):
                self.tearDown()
                self.setUp()
                self.make(shape)
                before = self.snapshot()
                payload = self.apply()
                self.assertEqual(payload["mode"], "preview")
                self.assertEqual(self.snapshot(), before)

    def test_harness_apply_places_everything_once(self):
        self.make("harness")
        self.git_init()
        report = self.run_json("audit.py", "--target", self.root)
        config = dict(report["config_draft"], templates=["docs/exec-plans/plan-template.md"])
        payload = self.apply("--apply", config=config)
        self.assertTrue(payload["applied"])
        self.assertEqual(self.statuses(payload), {
            "config": "done:create", "check-script": "done:create", "rule-card": "done:append-section",
            "verification-command": "done:insert", "template": "done:insert-summary"})

        installed = self.root / common.CHECK_TARGET
        self.assertEqual(installed.read_bytes(), common.CHECK_SOURCE.read_bytes())
        instructions = (self.root / "INSTRUCTIONS.md").read_text(encoding="utf-8")
        self.assertTrue(instructions.startswith("# 说明\n\n## Learned Constraints"))
        self.assertIn(common.RULE_CARD_MARKER, instructions)
        self.assertIn("D0001（快照保存全部字段）", instructions)
        self.assertIn("`py -3 scripts/check-readable-docs.py --changed`", instructions)
        self.assertNotIn("{{", instructions)
        harness = json.loads((self.root / ".harness/config.json").read_text(encoding="utf-8"))
        self.assertEqual(harness["verification_commands"],
                         HARNESS_CONFIG["verification_commands"] + ["py -3 scripts/check-readable-docs.py --changed"])
        template = (self.root / "docs/exec-plans/plan-template.md").read_text(encoding="utf-8")
        self.assertTrue(template.startswith("# 计划模板\n\n" + common.SUMMARY_MARKER))
        self.assertTrue(template.endswith("- 目标：\n"))
        saved = json.loads((self.root / ".harness/readable-docs.json").read_text(encoding="utf-8"))
        self.assertEqual(saved["skill_version"], common.SKILL_VERSION)

        before = self.snapshot()
        again = self.apply("--apply", config=config)
        self.assertEqual(set(self.statuses(again).values()), {"skip-exists", "skip-same", "skip-present"})
        self.assertEqual(self.snapshot(), before)

        self.run_script("check.py", "--report", "--json")

    def test_non_git_commands_run_outside_git(self):
        self.make("harness")
        payload = self.apply("--apply")
        self.assertEqual(self.statuses(payload)["verification-command"], "done:insert")
        instructions = (self.root / "INSTRUCTIONS.md").read_text(encoding="utf-8")
        self.assertIn("`py -3 scripts/check-readable-docs.py --files <改过的文件>`", instructions)
        self.assertNotIn("--changed", instructions)
        harness = json.loads((self.root / ".harness/config.json").read_text(encoding="utf-8"))
        self.assertEqual(harness["verification_commands"][-1], "py -3 scripts/check-readable-docs.py --report")
        installed = self.root / common.CHECK_TARGET
        self.run_script(installed, "--report", "--json")
        self.run_script(installed, "--files", "README.md", "--json")

    def test_rule_card_is_readable_itself(self):
        self.make("harness")
        self.apply("--apply")
        instructions = (self.root / "INSTRUCTIONS.md").read_text(encoding="utf-8")
        card = instructions[instructions.index("## 给人看的文字"):]
        findings = check.analyze(card, "card.md", check.build_settings(check.load_config(None)))
        self.assertEqual([f for f in findings if f.rule != "unregistered-id"], [])

    def test_existing_config_and_different_check_are_never_overwritten(self):
        self.make("agents-instructions")
        self.write("readable-docs.json", '{"schema_version": "readable-docs-config-v1", "mine": true}\n')
        self.write("scripts/check-readable-docs.py", "CHECK_VERSION = \"0.0.1\"\n")
        before = {p: self.snapshot()[p] for p in ("readable-docs.json", "scripts/check-readable-docs.py")}
        payload = self.apply("--apply")
        statuses = self.statuses(payload)
        self.assertEqual(statuses["config"], "manual-merge")
        self.assertEqual(statuses["check-script"], "manual-upgrade")
        after = self.snapshot()
        self.assertEqual({p: after[p] for p in before}, before)
        self.assertNotIn("verification-command", statuses)

    def test_agents_claude_and_none_shapes(self):
        self.make("agents")
        self.write("scripts/.keep", "")
        self.apply("--apply")
        self.assertIn(common.RULE_CARD_MARKER, (self.root / "AGENTS.md").read_text(encoding="utf-8"))
        self.assertEqual((self.root / "CLAUDE.md").read_text(encoding="utf-8"), "见 AGENTS.md。\n")

        self.tearDown()
        self.setUp()
        self.make("claude")
        payload = self.apply("--apply", "--check-path", "tools/check-readable-docs.py")
        self.assertIn(common.RULE_CARD_MARKER, (self.root / "CLAUDE.md").read_text(encoding="utf-8"))
        self.assertEqual(self.statuses(payload)["check-script"], "done:create")
        self.assertTrue((self.root / "tools/check-readable-docs.py").is_file())

        self.tearDown()
        self.setUp()
        self.make("none")
        payload = self.apply("--apply")
        self.assertEqual(self.statuses(payload)["rule-card"], "suggest")
        self.assertEqual(self.statuses(payload)["check-script"], "manual")
        self.assertFalse((self.root / "AGENTS.md").exists())

    def test_crlf_and_bom_instruction_file_keeps_its_format(self):
        self.make("agents")
        self.write("AGENTS.md", "# AGENTS\n\n规则。\n", newline="\r\n", bom=True)
        self.write("scripts/.keep", "")
        self.apply("--apply")
        raw = (self.root / "AGENTS.md").read_bytes()
        self.assertTrue(raw.startswith(b"\xef\xbb\xbf# AGENTS\r\n"))
        self.assertNotIn(b"\n", raw.replace(b"\r\n", b""))
        self.assertIn(common.RULE_CARD_MARKER.encode("utf-8"), raw)

    def test_dirty_files_block_the_whole_apply(self):
        self.make("harness")
        self.git_init()
        self.write("INSTRUCTIONS.md", "# 说明\n\n改动中。\n")
        before = self.snapshot()
        payload = self.apply("--apply", expected=3)
        self.assertFalse(payload["applied"])
        self.assertEqual(self.statuses(payload)["rule-card"], "blocked-dirty")
        self.assertEqual(self.snapshot(), before)
        payload = self.apply("--apply", "--allow-dirty")
        self.assertTrue(payload["applied"])

    def test_paths_outside_the_project_are_rejected(self):
        self.make("agents")
        self.write("scripts/.keep", "")
        outside = self.tmp / "outside.md"
        outside.write_text("# 外部\n", encoding="utf-8")
        before = self.snapshot()
        report = self.run_json("audit.py", "--target", self.root)
        for config, extra in ((dict(report["config_draft"], templates=["../outside.md"]), ()),
                              (report["config_draft"], ("--check-path", "../evil.py")),
                              (report["config_draft"], ("--check-path", str(self.tmp / "abs.py")))):
            payload = self.apply("--apply", *extra, config=config, expected=2)
            self.assertFalse(payload["applied"])
            self.assertIn("rejected-outside", [a["status"] for a in payload["actions"]])
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(outside.read_text(encoding="utf-8"), "# 外部\n")
        self.assertFalse((self.tmp / "evil.py").exists() or (self.tmp / "abs.py").exists())

    def test_installed_config_drives_the_rule_card(self):
        self.make("agents")
        self.write("scripts/.keep", "")
        installed = dict(check.DEFAULT_CONFIG, card={"id_example": "BUG-7（已装配置里的示例）"})
        self.write_json("readable-docs.json", installed)
        report = self.run_json("audit.py", "--target", self.root)
        supplied = dict(report["config_draft"], card={"id_example": "TASK-9（这次给的示例）"})
        payload = self.apply("--apply", config=supplied)
        self.assertEqual(self.statuses(payload)["config"], "manual-merge")
        agents = (self.root / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("BUG-7（已装配置里的示例）", agents)
        self.assertNotIn("TASK-9", agents)

    def test_unconfirmed_bad_config_is_rejected(self):
        self.make("agents")
        before = self.snapshot()
        path = self.tmp / "bad.json"
        for bad in ({"schema_version": "wrong"},
                    {"schema_version": check.CONFIG_SCHEMA, "rules": {"semicolon": "loud"}}):
            path.write_text(json.dumps(bad), encoding="utf-8")
            result = self.run_script("apply.py", "--target", self.root, "--config", path, "--apply", expected=2)
            self.assertIn("ERROR", result.stderr.decode("utf-8"))
        self.assertEqual(self.snapshot(), before)


if __name__ == "__main__":
    import unittest
    unittest.main()
