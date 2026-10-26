"""check.py: sentence rules, ID rules, config, CLI modes and portability."""

from __future__ import annotations

import json
import subprocess
import unittest

from support import ProjectTestCase, check, rules_at, settings

NOTE = "NOTES.md"


def lines_of(text: str, rule: str, **overrides: object) -> list:
    return sorted({f.line for f in rules_at(text, rule, **overrides)})


class SentenceRuleTests(unittest.TestCase):
    def test_modal_words_are_never_flagged(self):
        findings = check.analyze("请求可能已失败。\n结果也许不完整，大概要重跑。\n", "doc.md", settings())
        self.assertEqual(findings, [])

    def test_clean_text_has_no_findings(self):
        self.assertEqual(check.analyze("打开配置文件。读取第三行。把结果写入日志。\n", "doc.md", settings()), [])

    def test_semicolon_long_sentence_and_nominalization(self):
        self.assertEqual(lines_of("先开票；再发货。\n", "semicolon"), [1])
        self.assertEqual(lines_of("把" + "很长的说明" * 9 + "写完了。\n", "long-sentence"), [1])
        self.assertEqual(lines_of("我们需要对日志进行分析。\n", "nominalization"), [1])

    def test_max_chars_comes_from_config(self):
        text = "读取配置并写入日志。\n"
        self.assertEqual(lines_of(text, "long-sentence"), [])
        self.assertEqual(lines_of(text, "long-sentence", max_chars={"explanation": 5}), [1])

    def test_sentences_without_chinese_are_skipped(self):
        text = "This English sentence keeps going; it has a semicolon and " + "many words " * 20 + "\n"
        self.assertEqual(check.analyze(text, "doc.md", settings()), [])

    def test_code_blocks_inline_code_links_and_comments_are_skipped(self):
        text = ("```\n先开票；再发货\n```\n"
                "用 `a；b` 分隔。\n"
                "见 [说明](https://example.invalid/a;b)。\n"
                "<!-- 先开票；再发货 -->\n"
                "<!--\n先开票；再发货\n-->\n"
                "---\n")
        self.assertEqual(lines_of(text, "semicolon"), [])

    def test_off_on_markers_skip_quoted_blocks(self):
        text = ("先开票；再发货。\n<!-- readable-docs:off -->\n原话：先开票；再发货。\nTASK-1、TASK-2\n"
                "<!-- readable-docs:on -->\n又一句；再一句。\n")
        self.assertEqual(lines_of(text, "semicolon"), [1, 6])
        self.assertEqual(lines_of(text, "bare-id-run"), [])

    def test_front_matter_is_skipped(self):
        self.assertEqual(lines_of("---\ntitle: 先开票；再发货\n---\n正文。\n", "semicolon"), [])

    def test_table_cells_are_checked_separately(self):
        self.assertEqual(lines_of("| 甲 | 先开票；再发货 |\n", "semicolon"), [1])

    def test_marketing_and_empty_phrases_respect_allow_list(self):
        text = "评审闭环后上线。需要注意的是，缓存会过期。\n"
        self.assertEqual(lines_of(text, "marketing-adjective"), [1])
        self.assertEqual(lines_of(text, "marketing-adjective", terms={"allow": ["闭环"]}), [])
        self.assertEqual(lines_of(text, "empty-phrase"), [1])

    def test_synonym_rotation_and_distinct_terms(self):
        text = "用户登录。\n用户退出。\n客户付款。\n"
        found = rules_at(text, "synonym-rotation")
        self.assertEqual([(f.line, f.match) for f in found], [(3, "客户")])
        self.assertEqual(rules_at(text, "synonym-rotation", terms={"distinct": [["用户", "客户"]]}), [])
        self.assertEqual(rules_at("客户端版本过旧。客户端重试。用户登录。\n", "synonym-rotation"), [])

    def test_advisory_rules(self):
        self.assertEqual(lines_of("日志被清空了。\n", "passive-voice"), [1])
        self.assertEqual(lines_of("被动语态要少用。被告到庭。\n", "passive-voice"), [])
        self.assertEqual(lines_of("在必要时做适当调整。\n", "vague-word"), [1])
        self.assertEqual(lines_of("先开票——再发货。\n", "dash-join"), [1])
        self.assertEqual(lines_of("先开票,再发货。\n", "halfwidth-punct"), [1])


class BareIdRunTests(unittest.TestCase):
    """Cases ported from the harness skill's check-id-readability tests."""

    def test_bare_id_run_reports_line_and_snippet(self):
        found = rules_at("# 标题\n- 标书 `3d496a`、`84ba21`、`6d67dc`；四图 `328272`。\n", "bare-id-run")
        self.assertEqual(len(found), 1)
        self.assertEqual((found[0].line, found[0].match), (2, "`3d496a`、`84ba21`、`6d67dc`"))

    def test_every_id_kind_and_separator_is_detected(self):
        lines = ["TASK-001, TASK-002 已排期", "决策 D001；D002", "见 #D3 #D4", "提交 `794238c`,`7901c82`",
                 "TASK-003（SD 卡挂载）、TASK-004（日志落盘）", "TASK-005 TASK-006"]
        self.assertEqual(lines_of("\n".join(lines), "bare-id-run"), [1, 2, 3, 4, 6])

    def test_evidence_parenthetical_after_a_sentence_is_exempt(self):
        text = ("模板合并完成并通过测试（`e2c366`、`c6098c`）。\n"
                "Merge finished (`e2c366`, `c6098c`; `8f8651`).\n"
                "| 基线 | 通过（`9f2b2a`、`36a9ba`） | 2026-10-16 |\n")
        self.assertEqual(lines_of(text, "bare-id-run"), [])

    def test_parenthetical_with_words_or_without_preceding_text_is_checked(self):
        text = "（`e2c366`、`c6098c`）\n完成（见 `e2c366`、`c6098c`）\n- (`e2c366`, `c6098c`)\n"
        self.assertEqual(lines_of(text, "bare-id-run"), [1, 2, 3])

    def test_single_ids_and_plain_text_pass(self):
        text = ("合并完成（`e2c366`）。\nTASK-007（串口日志）已排期。\n"
                "普通文字，`deadbeef` 不含数字，`abc1234567890` 超过 12 位，ADD123 不是决策号。\n")
        self.assertEqual(lines_of(text, "bare-id-run"), [])

    def test_fenced_code_blocks_are_skipped(self):
        text = "```\nTASK-001、TASK-002\n```\n```sh\n`a1b2c3` `d4e5f6`\n```\nTASK-003、TASK-004\n"
        self.assertEqual(lines_of(text, "bare-id-run"), [7])

    def test_chinese_and_ascii_brackets_and_semicolons(self):
        text = "完成（TASK-001；TASK-002）\n完成(TASK-001; TASK-002）\nTASK-001；TASK-002 待验收\n"
        self.assertEqual(lines_of(text, "bare-id-run"), [3])


class FirstMentionTests(unittest.TestCase):
    def test_gloss_after_first_mention_passes_and_later_mentions_are_free(self):
        text = "TASK-003（SD 卡挂载）已排期。\n之后 TASK-003 进入验收。\n"
        self.assertEqual(rules_at(text, "first-mention"), [])

    def test_missing_gloss_is_reported_once(self):
        found = rules_at("D0015 已生效。\nD0015 继续适用。\n", "first-mention")
        self.assertEqual([(f.line, f.match) for f in found], [(1, "D0015")])

    def test_link_and_backtick_forms_with_gloss_pass(self):
        text = ("见 [D0033](decisions/0033.md)（讨论期产物入 Git）。\n"
                "提交 `a1b2c3d`（修复登录超时）。\n")
        self.assertEqual(rules_at(text, "first-mention"), [])

    def test_a_gloss_needs_words_not_only_ids(self):
        found = rules_at("见 TASK-003（TASK-004）。\n", "first-mention")
        self.assertEqual([f.match for f in found], ["TASK-003"])

    def test_evidence_citations_and_definitions_need_no_gloss(self):
        text = ("模板已合并（`e2c366`）。\n"
                "### D0007 改用 Postgres\n"
                "| D0008 | 快照保存全部字段 |\n"
                "- **TASK-009**：串口日志\n")
        self.assertEqual(rules_at(text, "first-mention"), [])

    def test_project_kinds_replace_builtins(self):
        kinds = [{"name": "plan-decision", "pattern": r"待决\d+"}]
        self.assertEqual(lines_of("见待决3。\n", "first-mention", id_kinds=kinds), [1])
        self.assertEqual(lines_of("见待决3（停止本地下载）。\n", "first-mention", id_kinds=kinds), [])


class ReviewRegressionTests(unittest.TestCase):
    """Defects found in the 2026-10-24 Codex review."""

    def test_link_targets_and_comments_are_not_id_mentions(self):
        found = rules_at("[说明](TASK-001.md) 已更新。\nTASK-001 已排期。\n", "first-mention")
        self.assertEqual([(f.line, f.match) for f in found], [(2, "TASK-001")])
        self.assertEqual(rules_at("正文 <!-- TASK-001、TASK-002 --> 结束。\n", "first-mention"), [])
        self.assertEqual(rules_at("正文 <!-- TASK-001、TASK-002 --> 结束。\n", "bare-id-run"), [])

    def test_unclosed_parenthetical_is_not_a_gloss(self):
        self.assertEqual(lines_of("TASK-001（修复登录\n", "first-mention"), [1])

    def test_uppercase_prefix_ids_are_unregistered_but_tech_names_are_not(self):
        kinds = [{"name": "decision", "pattern": r"\bD\d{3,}\b"}]
        found = rules_at("TASK-003 与 BUG-123，编码 UTF-8，摘要 SHA-256。\n", "unregistered-id", id_kinds=kinds)
        self.assertEqual([f.match for f in found], ["TASK-003", "BUG-123"])

    def test_a_third_word_does_not_bridge_distinct_terms(self):
        found = rules_at("用户登录。客户付款。使用者退出。\n", "synonym-rotation",
                         terms={"distinct": [["用户", "客户"]]})
        self.assertEqual([f.match for f in found], ["使用者"])
        self.assertIn("用户×1、使用者×1", found[0].message)


class UnregisteredIdTests(unittest.TestCase):
    def test_unregistered_shapes_are_reported_once_per_token(self):
        found = rules_at("Review-007 已结束。D3 待定。D3 仍待定。`Q1` 在代码里。\n", "unregistered-id")
        self.assertEqual([f.match for f in found], ["Review-007", "D3"])

    def test_registered_tokens_are_not_unregistered(self):
        kinds = [{"name": "plan-decision", "pattern": r"\bD\d\b"}]
        self.assertEqual(rules_at("D3（停止本地下载）。\n", "unregistered-id", id_kinds=kinds), [])


class ConfigTests(ProjectTestCase):
    def test_levels_drive_exit_codes(self):
        self.write(NOTE, "见 TASK-001、TASK-002。\n先开票；再发货。\n")
        self.run_script("check.py", "--files", NOTE, expected=0)
        self.write_json("readable-docs.json", {"schema_version": check.CONFIG_SCHEMA,
                                               "rules": {"bare-id-run": "block"}})
        payload = self.run_json("check.py", "--files", NOTE, "--json", expected=1)
        self.assertEqual(payload["blocked"], 1)
        self.write_json("readable-docs.json", {"schema_version": check.CONFIG_SCHEMA,
                                               "rules": {"bare-id-run": "off", "semicolon": "block"}})
        payload = self.run_json("check.py", "--files", NOTE, "--json", expected=1)
        self.assertNotIn("bare-id-run", payload["counts"])

    def test_harness_config_location_wins(self):
        self.write(NOTE, "先开票；再发货。\n")
        self.write_json("readable-docs.json", {"schema_version": check.CONFIG_SCHEMA})
        self.write_json(".harness/readable-docs.json", {"schema_version": check.CONFIG_SCHEMA,
                                                         "rules": {"semicolon": "block"}})
        payload = self.run_json("check.py", "--files", NOTE, "--json", expected=1)
        self.assertTrue(payload["config"].endswith("readable-docs.json"))
        self.assertIn(".harness", payload["config"])

    def test_bad_configs_exit_two(self):
        self.write(NOTE, "正文。\n")
        for bad in ({"schema_version": "other"}, {"schema_version": check.CONFIG_SCHEMA, "rules": {"nope": "warn"}},
                    {"schema_version": check.CONFIG_SCHEMA, "rules": {"semicolon": "loud"}},
                    {"schema_version": check.CONFIG_SCHEMA, "id_kinds": [{"name": "x", "pattern": "("}]},
                    {"schema_version": check.CONFIG_SCHEMA, "rules": []},
                    {"schema_version": check.CONFIG_SCHEMA, "max_chars": {"explanation": "x"}},
                    {"schema_version": check.CONFIG_SCHEMA, "terms": {"allow": "闭环"}},
                    {"schema_version": check.CONFIG_SCHEMA, "frozen": "docs/**"}):
            self.write_json("readable-docs.json", bad)
            self.run_script("check.py", "--files", NOTE, expected=2)
        self.write("readable-docs.json", "{not json")
        self.run_script("check.py", "--files", NOTE, expected=2)

    def test_config_template_is_valid(self):
        template = json.loads((check.Path(check.__file__).resolve().parents[1]
                               / "assets" / "readable-docs.json.tmpl").read_text(encoding="utf-8"))
        merged = check.merge_config(template)
        check.build_settings(merged)
        self.assertEqual(set(template["rules"]), set(check.RULES))
        self.assertEqual(set(template) - {"skill_version", "card", "templates"}, set(check.DEFAULT_CONFIG))


class CliTests(ProjectTestCase):
    def test_json_payload_and_unreadable_files(self):
        self.write(NOTE, "先开票；再发货。\n")
        payload = self.run_json("check.py", "--files", NOTE, "--json")
        self.assertEqual(payload["schema_version"], check.SCHEMA_VERSION)
        self.assertEqual(payload["files"], [NOTE])
        self.assertEqual(payload["counts"], {"semicolon": 1})
        missing = self.run_json("check.py", "--files", "NOPE.md", "--json", expected=2)
        self.assertEqual(missing["errors"][0]["file"], "NOPE.md")
        (self.root / "bad.md").write_bytes(b"\xff\xfe bad bytes \x81")
        self.run_script("check.py", "--files", "bad.md", expected=2)

    def test_bom_and_crlf_input(self):
        self.write(NOTE, "先开票；再发货。\n正文。\n", newline="\r\n", bom=True)
        payload = self.run_json("check.py", "--files", NOTE, "--json")
        self.assertEqual([(f["line"], f["col"]) for f in payload["findings"]], [(1, 4)])

    def test_gbk_console_still_prints_utf8(self):
        self.write(NOTE, "先开票；再发货。\n")
        result = self.run_script("check.py", "--files", NOTE, env={"PYTHONIOENCODING": "gbk"})
        self.assertIn("分号", result.stdout.decode("utf-8"))

    def test_report_mode_never_blocks(self):
        self.write_json("readable-docs.json", {"schema_version": check.CONFIG_SCHEMA,
                                               "rules": {"semicolon": "block"}})
        self.write("docs/a.md", "先开票；再发货。\n")
        payload = self.run_json("check.py", "--report", "--json")
        self.assertEqual(payload["counts"], {"semicolon": 1})
        self.assertEqual(payload["blocked"], 0)


class ChangedModeTests(ProjectTestCase):
    def test_only_changed_and_untracked_lines_are_reported(self):
        self.write("docs/a.md", "先开票；再发货。\n正文。\n")
        self.git_init()
        self.write("docs/a.md", "先开票；再发货。\n正文；新加。\n")
        self.write("docs/new.md", "未跟踪；文件。\n")
        payload = self.run_json("check.py", "--json")
        found = sorted((f["path"], f["line"]) for f in payload["findings"])
        self.assertEqual(found, [("docs/a.md", 2), ("docs/new.md", 1)])

    def test_staged_changes_count_and_deleted_files_are_ignored(self):
        self.write("a.md", "正文。\n")
        self.write("gone.md", "正文。\n")
        self.git_init()
        self.write("a.md", "正文。\n先开票；再发货。\n")
        self.git("add", "a.md")
        (self.root / "gone.md").unlink()
        payload = self.run_json("check.py", "--json")
        self.assertEqual([(f["path"], f["line"]) for f in payload["findings"]], [("a.md", 2)])

    def test_repository_without_commits(self):
        self.write("a.md", "先开票；再发货。\n")
        self.git_init(commit=False)
        self.git("add", "a.md")
        payload = self.run_json("check.py", "--json")
        self.assertEqual(payload["counts"], {"semicolon": 1})

    def test_exclude_and_frozen_globs(self):
        self.write_json("readable-docs.json", {"schema_version": check.CONFIG_SCHEMA,
                                               "frozen": ["docs/completed/**"],
                                               "human_facing": {"include": ["**/*.md"], "exclude": ["vendor/**"]}})
        self.git_init()
        for rel in ("docs/completed/old.md", "vendor/x.md", "docs/live.md"):
            self.write(rel, "先开票；再发货。\n")
        payload = self.run_json("check.py", "--json")
        self.assertEqual(payload["files"], ["docs/live.md"])

    def test_block_level_in_changed_lines_exits_one(self):
        self.write_json("readable-docs.json", {"schema_version": check.CONFIG_SCHEMA,
                                               "rules": {"bare-id-run": "block"}})
        self.write("a.md", "旧行 TASK-001、TASK-002。\n")
        self.git_init()
        self.run_script("check.py", expected=0)
        self.write("a.md", "旧行 TASK-001、TASK-002。\n新行 TASK-003、TASK-004。\n")
        payload = self.run_json("check.py", "--json", expected=1)
        self.assertEqual([f["line"] for f in payload["findings"] if f["rule"] == "bare-id-run"], [2])

    def test_report_skips_files_absent_from_the_work_tree(self):
        self.write("a.md", "正文。\n")
        self.write("b.md", "先开票；再发货。\n")
        self.git_init()
        (self.root / "a.md").unlink()
        payload = self.run_json("check.py", "--report", "--json")
        self.assertEqual(payload["errors"], [])
        self.assertEqual(payload["counts"], {"semicolon": 1})

    def test_sha256_repository_without_commits(self):
        try:
            subprocess.run(["git", "-C", str(self.root), "init", "-q", "--object-format=sha256"],
                           capture_output=True, check=True)
        except subprocess.CalledProcessError:
            self.skipTest("this Git cannot create SHA-256 repositories")
        self.write("a.md", "先开票；再发货。\n")
        self.git("add", "a.md")
        payload = self.run_json("check.py", "--json")
        self.assertEqual(payload["counts"], {"semicolon": 1})

    def test_outside_git_exits_two(self):
        self.write("a.md", "正文。\n")
        result = self.run_script("check.py", expected=2)
        self.assertIn("not a Git work tree", result.stderr.decode("utf-8"))


if __name__ == "__main__":
    unittest.main()
