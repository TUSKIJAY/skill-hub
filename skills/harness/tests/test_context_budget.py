"""Context Budget: the INSTRUCTIONS section, harness_read.py, the startup budget script and the merge hints."""
from __future__ import annotations

import hashlib
import json
import re
import sys
import unittest

from harness_test_support import SCRIPTS, SKILL, ProjectTestCase

sys.path.insert(0, str(SCRIPTS))
import harness_merge  # noqa: E402
from harness_templates import default_context_budget, render_context_budget_section  # noqa: E402

EXIT_FAIL = 1
EXIT_USAGE = 2
LEGACY_CONSOLES = ({}, {"PYTHONUTF8": "0", "PYTHONIOENCODING": "cp936"},
                   {"PYTHONUTF8": "0", "PYTHONIOENCODING": "cp1252"})
UTF8_BOM = b"\xef\xbb\xbf"
SECTION = re.compile(r"## Context Budget\n.*?(?=\n\n## )", re.S)
NEXT = "下一段从第 "


def without_section(text: str) -> str:
    """INSTRUCTIONS.md as an install made before the Context Budget existed would have it."""
    return text.replace(SECTION.search(text).group(0) + "\n\n", "")


def snapshot(root):
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob("*") if p.is_file()}


class InstallTests(ProjectTestCase):
    project_dir_name = "cb 项目"

    def validate(self, expected=0):
        return json.loads(self.run_script(SCRIPTS / "validate_harness.py", "--target", self.root, "--json",
                                          expected=expected).stdout)

    def project_check(self, expected=0):
        return json.loads(self.run_script(self.root / "scripts/check-project-harness.py", "--root", self.root,
                                          expected=expected).stdout)

    def config(self):
        return json.loads(self.read(".harness/config.json"))

    def write_config(self, config):
        (self.root / ".harness/config.json").write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")

    def test_new_install_section_matches_config_and_scores_100(self):
        self.install()
        self.assertEqual(self.config()["context_budget"], default_context_budget())
        instructions = self.read("INSTRUCTIONS.md")
        order = [instructions.index(h) for h in ("## AI Behavior Rules", "## Context Budget", "## Verification")]
        self.assertEqual(order, sorted(order))
        section = SECTION.search(instructions).group(0)
        self.assertEqual(section, render_context_budget_section(self.config()["python_command"],
                                                                default_context_budget()))
        for text in ("总行数不超过 200、总字节不超过 16384", "一条命令合计最多 80 行，不要用循环把多段拼在一起输出",
                     "看总行数和前 40 行", '`.harness/tmp/<YYYY-MM-DD>-<主题>.txt`',
                     'scripts/harness_read.py outline "<文件>"`（启动四件除外）；已知要找的词时，也可以先用 '
                     '`grep -n "<词>" "<文件>"`（Windows 用 `Select-String`）找行号；不要先用读文件工具读开头再决定。',
                     "用命令或接口自带的限行参数只取前 40 行", "每页不超过 80 条或 8192 字节",
                     "不回什么（整段原文；任务明确要求的短引文除外，带定位）"):
            self.assertIn(text, section)
        self.assertEqual(len(section.splitlines()), 8)  # heading, lead, four rules, two blank lines
        sentence = harness_merge.agents_context_sentence()
        self.assertIn(sentence, self.read("AGENTS.md").split("## Use / Maintain")[0])
        # The short form of all four rules, rule 4 included: AGENTS.md is the only file surely loaded.
        for text in ("读文件先 `outline`（启动四件除外）", "超预算只读行段", "先落盘再 `head`",
                     '交给子代理时写明只回结论（不超过 40 行，每条带"文件:行"），不回原文。'):
            self.assertIn(text, sentence)
        for path in self.root.rglob("*"):
            if path.is_file():
                self.assertNotIn("{{", path.read_text(encoding="utf-8"), path)
        result = self.validate()
        self.assertEqual(result["overall_score"], 100)
        self.assertFalse([w for w in result["warnings"] if "Context Budget" in w or "harness_read" in w])
        check = self.project_check()
        self.assertTrue(check["passed"])
        self.assertEqual(check["warnings"], [])
        self.assertIn("scripts/harness_read.py", [item["path"] for item in check["files"]])

    def test_config_parses_with_and_without_task_cards(self):
        base = self.root
        for flags in ((), ("--task-cards",)):
            with self.subTest(flags=flags):
                self.root = base / ("cards" if flags else "plain")
                self.root.mkdir()
                self.install(*flags)
                keys = list(self.config())
                self.assertEqual(keys.index("context_budget"), keys.index("workflow_entry") + 1)
                if flags:
                    self.assertEqual(keys.index("task_cards"), keys.index("context_budget") + 1)
                self.assertEqual(self.validate()["overall_score"], 100)

    def test_scratch_dir_option_is_validated_and_rendered(self):
        for bad in ("../outside", "/abs/path", "C:/x", "", ".git/x"):
            with self.subTest(bad=bad):
                result = self.apply("--scratch-dir", bad, "--apply", expected=EXIT_USAGE)
                self.assertIn("Scratch directory", result.stderr)
                self.assertEqual(list(self.root.iterdir()), [])
        self.install("--scratch-dir", "work\\agent tmp")
        self.assertEqual(self.config()["context_budget"]["scratch_dir"], "work/agent tmp")
        self.assertIn("`work/agent tmp/<YYYY-MM-DD>-<主题>.txt`", self.read("INSTRUCTIONS.md"))
        self.assertFalse((self.root / "work").exists())  # declared, never created
        self.assertTrue(self.project_check()["passed"])

    def test_rerun_renders_the_installed_numbers_and_scratch_dir(self):
        self.install("--scratch-dir", "work/tmp")
        config = self.config()
        config["context_budget"]["output_lines"] = 60
        self.write_config(config)
        (self.root / "INSTRUCTIONS.md").unlink()
        (self.root / "scripts/harness_read.py").unlink()
        self.install()
        instructions = self.read("INSTRUCTIONS.md")
        self.assertIn("一条命令合计最多 60 行", instructions)
        self.assertIn("`work/tmp/<YYYY-MM-DD>-<主题>.txt`", instructions)
        self.assertIn('"output_lines": 60', self.read("scripts/harness_read.py"))
        self.assertTrue(self.project_check()["passed"])

    def test_gitignore_hint_is_printed_never_written(self):
        cases = (("node_modules/\n", True), ("node_modules/\n.harness/tmp/\n", False), ("/.harness\n", False),
                 ("# .harness/tmp\n", True), (".harness/tmp/*\n", False), (None, False))
        for text, hinted in cases:
            with self.subTest(text=text):
                gitignore = self.root / ".gitignore"
                if text is None:
                    gitignore.unlink()
                else:
                    gitignore.write_text(text, encoding="utf-8")
                before = snapshot(self.root)
                hint = json.loads(self.apply("--json").stdout)["gitignore_hint"]
                self.assertEqual(bool(hint), hinted, hint)
                if hinted:
                    self.assertIn(".harness/tmp/", hint)
                    self.assertIn("Note: .gitignore does not list .harness/tmp/", self.apply().stdout)
                self.assertEqual(snapshot(self.root), before)

    def test_project_check_names_the_line_that_disagrees_with_the_config(self):
        self.install()
        config = self.config()
        config["context_budget"]["output_lines"] = 60
        config["context_budget"]["scratch_dir"] = "tmp"
        self.write_config(config)
        failures = self.project_check(expected=EXIT_FAIL)["lint_failures"]
        lines = self.read("INSTRUCTIONS.md").splitlines()
        rule1 = next(n for n, line in enumerate(lines, start=1) if line.startswith("1. 读文件先看大纲"))
        self.assertIn(f"INSTRUCTIONS.md line {rule1} states output_lines=80 but .harness/config.json "
                      "context_budget.output_lines=60; change one so they agree", failures)
        self.assertTrue(any("states scratch_dir=.harness/tmp but" in item for item in failures), failures)
        self.assertEqual(len([f for f in failures if "output_lines=80" in f]), 4)
        config["context_budget"]["output_lines"] = -1
        self.write_config(config)
        failures = self.project_check(expected=EXIT_FAIL)["lint_failures"]
        self.assertIn(".harness/config.json context_budget.output_lines is a positive integer", failures)

    def test_project_check_compares_output_bytes(self):
        self.install()
        config = self.config()
        config["context_budget"]["output_bytes"] = 4096
        self.write_config(config)
        failures = self.project_check(expected=EXIT_FAIL)["lint_failures"]
        self.assertTrue(any("states output_bytes=8192 but .harness/config.json context_budget.output_bytes=4096"
                            in item for item in failures), failures)

    def test_project_check_compares_every_number_the_section_states(self):
        self.install()
        config = self.config()
        changed = {"file_lines": 201, "file_bytes": 16001, "output_lines": 61, "output_bytes": 4096,
                   "head_lines": 31, "scratch_dir": "tmp"}
        config["context_budget"].update(changed)
        self.write_config(config)
        failures = self.project_check(expected=EXIT_FAIL)["lint_failures"]
        stated = {key: [f for f in failures if f" states {key}=" in f and f"context_budget.{key}=" in f]
                  for key in changed}
        # Rule 1 states file_lines, file_bytes and output_lines; rule 2 output_lines, scratch_dir and head_lines
        # twice; rule 3 output_lines twice and output_bytes; rule 4 head_lines.
        counts = {"file_lines": 1, "file_bytes": 1, "output_lines": 4, "output_bytes": 1, "head_lines": 3,
                  "scratch_dir": 1}
        self.assertEqual({key: len(found) for key, found in stated.items()}, counts, failures)
        self.assertEqual(len(failures), sum(counts.values()), failures)
        # Every number the section states is one of those: none is left unchecked.
        section = SECTION.search(self.read("INSTRUCTIONS.md")).group(0)
        numbers = re.findall(r"(?<![\w.])\d+(?![\w.])", section)
        defaults = default_context_budget()
        self.assertEqual(sorted(numbers), sorted(str(defaults[key]) for key, n in counts.items() for _ in range(n)
                                                 if key != "scratch_dir"))
        # A rerun renders the config's numbers, and the check agrees with them.
        (self.root / "INSTRUCTIONS.md").unlink()
        self.install()
        self.assertTrue(self.project_check()["passed"])
        self.assertIn("一条命令合计最多 61 行", self.read("INSTRUCTIONS.md"))

    def test_project_check_still_reads_the_wording_of_earlier_installs(self):
        self.install()
        path = self.root / "INSTRUCTIONS.md"
        old = (self.read("INSTRUCTIONS.md").replace("一条命令合计最多 80 行，不要用循环把多段拼在一起输出", "一次最多 80 行")
               .replace("/<YYYY-MM-DD>-", "/<日期>-"))
        self.assertIn("一次最多 80 行", old)
        path.write_text(old, encoding="utf-8")
        self.assertTrue(self.project_check()["passed"])
        config = self.config()
        config["context_budget"].update(output_lines=60, scratch_dir="tmp")
        self.write_config(config)
        failures = self.project_check(expected=EXIT_FAIL)["lint_failures"]
        self.assertEqual(len([f for f in failures if "output_lines=80" in f]), 4, failures)
        self.assertTrue(any("states scratch_dir=.harness/tmp but" in f for f in failures), failures)

    def test_project_check_rejects_a_scratch_dir_outside_the_project(self):
        self.install()
        for bad, reason in (("../outside", "leaves the project (..)"), ("/tmp/x", "is absolute"),
                            ("C:/x", "is absolute"), (".git/tmp", "is inside .git")):
            with self.subTest(bad=bad):
                config = self.config()
                config["context_budget"]["scratch_dir"] = bad
                self.write_config(config)
                path = self.root / "INSTRUCTIONS.md"
                text = re.sub(r"重定向到 `[^`]+?/<YYYY-MM-DD>", f"重定向到 `{bad}/<YYYY-MM-DD>",
                              self.read("INSTRUCTIONS.md"))
                path.write_text(text, encoding="utf-8")
                failures = self.project_check(expected=EXIT_FAIL)["lint_failures"]
                self.assertIn(f".harness/config.json context_budget.scratch_dir={bad!r} {reason}; use a relative "
                              "path inside the project", failures)
        config = self.config()
        config["context_budget"]["scratch_dir"] = "work/tmp/"
        self.write_config(config)
        path.write_text(re.sub(r"重定向到 `[^`]+?/<YYYY-MM-DD>", "重定向到 `work/tmp/<YYYY-MM-DD>",
                               self.read("INSTRUCTIONS.md")), encoding="utf-8")
        self.assertTrue(self.project_check()["passed"])

    def test_project_check_only_warns_without_the_section_or_block(self):
        self.install()
        path = self.root / "INSTRUCTIONS.md"
        path.write_text(without_section(self.read("INSTRUCTIONS.md")), encoding="utf-8")
        config = self.config()
        del config["context_budget"]
        self.write_config(config)
        check = self.project_check()
        self.assertTrue(any("no Context Budget section" in w for w in check["warnings"]), check["warnings"])
        self.assertTrue(any("no context_budget" in w for w in check["warnings"]), check["warnings"])
        # A mention elsewhere is not the section.
        path.write_text(self.read("INSTRUCTIONS.md") + "\n读取规则见 Context Budget（上下文预算），待补。\n", encoding="utf-8")
        check = self.project_check()
        self.assertTrue(any("no Context Budget section" in w for w in check["warnings"]), check["warnings"])


class HarnessReadTests(ProjectTestCase):
    project_dir_name = "读 space"

    def setUp(self):
        super().setUp()
        self.install()
        self.reader = self.root / "scripts/harness_read.py"

    def read_cmd(self, *args, expected=0, env=None):
        return self.run_script(self.reader, *args, expected=expected, env=env)

    def put(self, relative, data):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(data, str):
            data = data.encode("utf-8")
        path.write_bytes(data)
        return relative

    def test_three_subcommands_survive_legacy_consoles(self):
        name = self.put("笔记 notes.md", "# 总览\n\n正文第一行\n\n## 第二节 — 破折号\n\n```\n# 代码注释不是标题\n```\n")
        for env in LEGACY_CONSOLES:
            with self.subTest(env=env):
                outline = self.read_cmd("outline", name, env=env).stdout
                self.assertIn("共 9 行", outline)
                self.assertIn("在预算内", outline)
                self.assertIn("5: ## 第二节 — 破折号", outline)
                self.assertNotIn("代码注释", outline)
                self.assertEqual(self.read_cmd("lines", name, 3, 3, env=env).stdout, "3: 正文第一行\n")
                head = self.read_cmd("head", name, 2, env=env).stdout
                self.assertTrue(head.startswith("共 9 行，"), head)
                self.assertIn("1: # 总览", head)
                self.assertIn(f'{NEXT}3 行开始', head)

    def test_bom_crlf_and_spaces_in_the_path(self):
        name = self.put("my docs/读我 file.md", UTF8_BOM + "# 标题\r\n第二行\r\n".encode("utf-8"))
        head = self.read_cmd("head", name).stdout
        self.assertIn("1: # 标题\n2: 第二行\n", head)
        self.assertNotIn("\ufeff", head)
        self.assertIn("1: # 标题", self.read_cmd("outline", name).stdout)

    def test_binary_and_missing_files_are_refused(self):
        name = self.put("image.bin", b"PNG\x00\x01\x02" * 10)
        for args in (("outline", name), ("lines", name, 1, 2), ("head", name)):
            result = self.read_cmd(*args, expected=EXIT_USAGE)
            self.assertIn("二进制文件，不读", result.stderr)
            self.assertEqual(result.stdout, "")
        self.assertIn("找不到文件", self.read_cmd("head", "nope.md", expected=EXIT_FAIL).stderr)

    def test_outline_of_ten_thousand_headings_is_capped_with_the_next_position(self):
        name = self.put("big headings.md", "".join(f"## 标题 {n}\n" for n in range(10000)))
        out = self.read_cmd("outline", name).stdout.splitlines()
        self.assertIn("超预算", out[0])
        self.assertIn(f'lines "{name}" <起> <止>', out[0])
        self.assertEqual(out[1], "标题 10000 个（行号: 标题）：")
        body = out[2:-1]
        self.assertEqual(len(body), 80)
        self.assertEqual(out[-1], f'{NEXT}81 行开始：{self.config_python()} scripts/harness_read.py lines "{name}" 81 160')

    def test_five_megabyte_single_line_is_cut_to_line_bytes(self):
        size = 5 * 1024 * 1024
        name = self.put("one line.log", b"x" * size)
        out = self.read_cmd("head", name).stdout
        lines = out.splitlines()
        self.assertEqual(lines[0], f"共 1 行，{size} 字节。前 1 行：")
        self.assertEqual(lines[1], "1: " + "x" * 1000 + f"…[+{size - 1000} 字节]")
        self.assertLess(len(out.encode("utf-8")), 8192)
        cut = self.read_cmd("lines", self.put("wide.txt", "中" * 400 + "\n"), 1, 1).stdout
        self.assertEqual(cut, "1: " + "中" * 333 + "…[+201 字节]\n")  # cut on a character boundary

    def test_line_and_byte_caps_and_ranges(self):
        name = self.put("long.txt", "".join(f"行 {n}\n" for n in range(1, 301)))
        out = self.read_cmd("lines", name, 1, 300).stdout.splitlines()
        self.assertEqual(len(out), 81)
        self.assertEqual(out[79], "80: 行 80")
        self.assertTrue(out[-1].startswith(f"{NEXT}81 行开始"))
        self.assertEqual(self.read_cmd("lines", name, 299, 400).stdout, "299: 行 299\n300: 行 300\n")
        self.assertIn("共 300 行", self.read_cmd("lines", name, 301, 302, expected=EXIT_FAIL).stderr)
        self.read_cmd("lines", name, 5, 3, expected=EXIT_USAGE)
        self.read_cmd("head", name, 0, expected=EXIT_USAGE)
        wide = self.put("wide.txt", "".join("y" * 900 + "\n" for _ in range(50)))
        out = self.read_cmd("lines", wide, 1, 50).stdout.splitlines()
        self.assertEqual(len(out), 10)  # nine 904-byte lines fit in 8192 bytes, then the next position
        self.assertTrue(out[-1].startswith(f"{NEXT}10 行开始"))

    def test_limits_come_from_the_config_field_by_field(self):
        name = self.put("long.txt", "".join(f"{n}\n" for n in range(1, 101)))
        path = self.root / ".harness/config.json"
        config = json.loads(path.read_text(encoding="utf-8"))
        config["context_budget"].update(output_lines=5, head_lines=3)
        path.write_text(json.dumps(config), encoding="utf-8")
        self.assertEqual(self.read_cmd("head", name).stdout.splitlines()[1:],
                         ["1: 1", "2: 2", "3: 3", f'{NEXT}4 行开始：{self.config_python()} scripts/harness_read.py lines "{name}" 4 8'])
        self.assertEqual(len(self.read_cmd("head", name, 50).stdout.splitlines()), 7)
        config["context_budget"].update(output_lines=-1, head_lines=True)
        path.write_text(json.dumps(config), encoding="utf-8")
        result = self.read_cmd("head", name)
        self.assertIn("context_budget.output_lines=-1 不是正整数，改用 80", result.stderr)
        self.assertIn("context_budget.head_lines=True 不是正整数，改用 40", result.stderr)
        self.assertEqual(len(result.stdout.splitlines()), 42)

    def test_tiny_output_bytes_still_bounds_the_first_line(self):
        name = self.put("wide.txt", "z" * 200 + "\n" + "second\n")
        path = self.root / ".harness/config.json"
        config = json.loads(path.read_text(encoding="utf-8"))
        for output_bytes, first in ((1, "1: …[+200 字节]"), (50, "1: " + "z" * 46 + "…[+154 字节]")):
            with self.subTest(output_bytes=output_bytes):
                config["context_budget"]["output_bytes"] = output_bytes
                path.write_text(json.dumps(config), encoding="utf-8")
                out = self.read_cmd("head", name).stdout.splitlines()
                self.assertEqual(out[1], first)
                self.assertEqual(len(out), 3)  # summary, the cut first line, next position
                self.assertTrue(out[2].startswith(f"{NEXT}2 行开始"))
                self.assertEqual(self.read_cmd("lines", name, 1, 2).stdout.splitlines()[0], first)

    def test_outline_keeps_only_what_it_can_print_from_100k_headings(self):
        name = self.put("huge.md", "".join(f"# h{n}\n" for n in range(100_000)))
        out = self.read_cmd("outline", name).stdout.splitlines()
        self.assertEqual(out[1], "标题 100000 个（行号: 标题）：")
        self.assertEqual(len(out), 83)
        self.assertEqual(out[81], "80: # h79")
        self.assertTrue(out[-1].startswith(f"{NEXT}81 行开始"))

    def config_python(self):
        return json.loads(self.read(".harness/config.json"))["python_command"]


class BudgetScriptTests(ProjectTestCase):
    def setUp(self):
        super().setUp()
        self.install()

    def budget(self, *args, expected=0):
        result = self.run_script(self.root / "scripts/check-startup-doc-budget.py", "--root", self.root, *args,
                                 expected=expected)
        return json.loads(result.stdout), result.stderr

    def set_startup_budget(self, value):
        path = self.root / ".harness/config.json"
        config = json.loads(path.read_text(encoding="utf-8"))
        config["startup_budget"] = value
        path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")

    def write_progress(self, completed=1, baseline=1, extra=""):
        rows = "".join(f"| `check-{n}` | pass | 2026-10-24 |\n" for n in range(baseline))
        items = "".join(f"- [x] 2026-10-{n:02d} — 完成第 {n} 项\n" for n in range(1, completed + 1))
        text = (f"# Progress\n\n历史经 harness_log.py 查询。\n\n## Facts\n\n- 事实。\n{extra}\n## In Progress\n\n- 无。\n\n"
                "## Blocked\n\n- 无。\n\n## Backlog\n\n- 无。\n\n## Open Unknowns\n\n- 无。\n\n## Verified Baseline\n\n"
                f"| Check / Command | Last result | Date |\n| --- | --- | --- |\n{rows}\n"
                f"## Completed (Rolling Window)\n\n{items}\n## Ledger Pointers\n\n- 无。\n")
        (self.root / "PROGRESS.md").write_text(text, encoding="utf-8")

    def test_output_carries_total_and_progress_shape(self):
        payload, stderr = self.budget()
        self.assertEqual(payload["total"]["bytes"], sum(item["bytes"] for item in payload["documents"]))
        self.assertFalse(payload["total"]["warning_exceeded"])
        shape = payload["progress_shape"]
        self.assertEqual((shape["completed_entries"], shape["baseline_rows"]), (1, 1))  # header row excluded
        self.assertFalse(shape["over_limit"])
        self.assertEqual((payload["actions"], payload["config_warnings"]), ([], []))
        self.assertIn("total: bytes=", stderr)
        self.budget("--strict")

    def test_seven_completed_and_a_baseline_table_fail_strict_with_a_ledger_action(self):
        self.write_progress(completed=7, baseline=3)
        payload, _ = self.budget()
        self.assertEqual(payload["progress_shape"]["completed_entries"], 7)
        self.assertEqual(payload["progress_shape"]["baseline_rows"], 3)
        self.assertTrue(payload["progress_shape"]["over_limit"])
        self.assertFalse(payload["archive_required"])  # file size alone decides this one
        _, stderr = self.budget("--strict", expected=2)
        self.assertIn("动作：PROGRESS.md Completed 有 7 条（上限 5），把最老 2 条迁入账本", stderr)
        self.assertIn("scripts/harness_log.py append --type milestone", stderr)

    def test_baseline_rows_oversized_items_and_long_line_hints(self):
        self.write_progress(baseline=14, extra="- " + "事" * 400 + "\n")
        payload, stderr = self.budget("--strict", expected=2)
        self.assertEqual(payload["progress_shape"]["baseline_rows"], 14)
        self.assertIn("Verified Baseline 有 14 行（上限 12），把最老 2 行迁入账本", stderr)
        oversized = payload["progress_shape"]["oversized_items"]
        self.assertEqual([(item["section"], item["bytes"], item["limit"]) for item in oversized], [("Facts", 1202, 900)])
        self.assertIn(f"第 {oversized[0]['line']} 行 1,202 字节（Facts 上限 900），拆成一行事实 + 链接", stderr)
        self.write_progress()  # only a long Backlog line: a hint, not a limit
        (self.root / "PROGRESS.md").write_text(self.read("PROGRESS.md").replace(
            "## Backlog\n\n- 无。", "## Backlog\n\n- " + "待" * 450), encoding="utf-8")
        payload, stderr = self.budget("--strict")
        self.assertFalse(payload["progress_shape"]["over_limit"])
        self.assertEqual(len(payload["progress_shape"]["long_lines"]), 1)
        self.assertIn("提示：PROGRESS.md 第", stderr)

    def test_startup_budget_falls_back_field_by_field(self):
        default, _ = self.budget()
        comparable = lambda payload: {k: v for k, v in payload.items() if k != "config_warnings"}  # noqa: E731
        explicit = {"files": {name: limits for name, limits in
                              ((d["path"], d["limits"]) for d in default["documents"])},
                    "total": {"warning_bytes": 40960, "hard_bytes": 57344},
                    "shape": {"completed_max_entries": 5, "baseline_max_rows": 12}}
        for value, warned in (({}, False), (explicit, False), ({"files": {}}, False),
                              ({"total": {"warning_bytes": 40960}}, False), ({"total": {"hard_bytes": -5}}, True),
                              ({"shape": {"completed_max_entries": 0, "nope": 1}}, True), ("x", True),
                              ({"total": "x"}, True)):
            with self.subTest(value=value):
                self.set_startup_budget(value)
                payload, stderr = self.budget()
                self.assertEqual(comparable(payload), comparable(default))
                self.assertEqual(bool(payload["config_warnings"]), warned, payload["config_warnings"])
                if warned:
                    self.assertIn("警告：", stderr)
        self.set_startup_budget({"files": {"PROGRESS.md": {"warning_bytes": 100}}})
        payload, stderr = self.budget("--strict", expected=2)
        progress = next(d for d in payload["documents"] if d["path"] == "PROGRESS.md")
        self.assertEqual(progress["limits"]["warning_bytes"], 100)
        self.assertEqual(progress["limits"]["hard_bytes"], 32768)
        self.assertTrue(progress["archive_required"])
        self.assertIn("动作：PROGRESS.md ", stderr)
        self.assertIn("（预警 100 字节、200 行）。最大的小节是第 1 行“开头”", stderr)
        self.assertNotIn("迁入账本", stderr)  # Completed holds one entry and is not the biggest section

    def test_a_long_facts_section_is_named_and_completed_is_left_alone(self):
        facts = "".join(f"- 事实 {n}：" + "细" * 230 + "\n" for n in range(36))  # each item about 700 bytes
        self.write_progress(extra=facts)
        payload, stderr = self.budget("--strict", expected=2)
        progress = next(d for d in payload["documents"] if d["path"] == "PROGRESS.md")
        self.assertTrue(progress["archive_required"])
        self.assertEqual(payload["progress_shape"]["oversized_items"], [])
        facts_line = self.read("PROGRESS.md").splitlines().index("## Facts") + 1
        self.assertIn(f"最大的小节是第 {facts_line} 行“Facts”", stderr)
        self.assertIn("把这一节的长条目拆成一行事实 + 链接", stderr)
        for action in payload["actions"]:
            self.assertNotIn("Completed", action)
            self.assertNotIn("迁入账本", action)

    def test_hard_line_below_warning_line_lowers_the_warning_and_still_prints_an_action(self):
        self.set_startup_budget({"total": {"hard_bytes": 10000}, "files": {"HANDOFF.md": {"hard_lines": 5}}})
        payload, stderr = self.budget(expected=1)
        self.assertIn("startup_budget.total.hard_bytes=10000 低于 warning_bytes=40960，预警线改用 10000",
                      payload["config_warnings"])
        self.assertIn("startup_budget.files.HANDOFF.md.hard_lines=5 低于 warning_lines=60，预警线改用 5",
                      payload["config_warnings"])
        self.assertEqual(payload["total"]["warning_bytes"], 10000)
        self.assertIn(f"动作：四件合计 {payload['total']['bytes']:,} 字节（硬上限 10,000）", stderr)
        self.assertIn("动作：HANDOFF.md ", stderr)
        self.assertIn("（硬上限 16,384 字节、5 行）", stderr)

    def test_a_file_over_its_hard_byte_limit_is_not_read(self):
        (self.root / "PROGRESS.md").write_bytes(b"- " + "大".encode("utf-8") * 12000 + b"\n")
        payload, stderr = self.budget(expected=1)
        progress = next(d for d in payload["documents"] if d["path"] == "PROGRESS.md")
        self.assertIsNone(progress["lines"])
        self.assertEqual(progress["bytes"], 36003)
        self.assertEqual(progress["unread"], "超过硬上限 32,768 字节，未读内容")
        self.assertTrue(payload["progress_shape"]["over_limit"])
        self.assertIn('scripts/harness_read.py outline "PROGRESS.md"', stderr)

    def test_total_warning_names_the_largest_file_and_section(self):
        self.set_startup_budget({"total": {"warning_bytes": 10000}})
        payload, stderr = self.budget()
        largest = max(payload["documents"], key=lambda item: item["bytes"])
        self.assertTrue(payload["total"]["warning_exceeded"])
        self.assertEqual(payload["total"]["largest"]["path"], largest["path"])
        self.assertIn(f"动作：四件合计 {payload['total']['bytes']:,} 字节（预警 10,000）。占比最大的是 {largest['path']}", stderr)
        self.assertIn("其中最大的小节是第", stderr)
        self.budget("--strict", expected=2)
        self.set_startup_budget({"total": {"hard_bytes": 10000}})
        payload, _ = self.budget(expected=1)
        self.assertTrue(payload["hard_limit_exceeded"])


class MigrationTests(ProjectTestCase):
    def preview(self):
        return json.loads(self.apply("--json", "--acceptance-check", "逐项核对产物与来源").stdout)

    def hints(self):
        return {hint["path"]: hint for hint in self.preview()["manual_merge"]}

    def validate(self):
        return json.loads(self.run_script(SCRIPTS / "validate_harness.py", "--target", self.root, "--json").stdout)

    def test_install_without_the_section_keeps_its_score_and_gets_a_warning_and_snippet(self):
        self.install()
        score = self.validate()["overall_score"]
        instructions = self.read("INSTRUCTIONS.md")
        section = SECTION.search(instructions).group(0)
        (self.root / "INSTRUCTIONS.md").write_text(without_section(instructions), encoding="utf-8")
        result = self.validate()
        self.assertEqual(result["overall_score"], score)
        self.assertIn("INSTRUCTIONS.md 缺 Context Budget 节；从模板或合并提示补上", result["warnings"])
        before = snapshot(self.root)
        hint = self.hints()["INSTRUCTIONS.md"]
        self.assertEqual(snapshot(self.root), before)
        self.assertEqual(hint["missing"], ["Context Budget section"])
        self.assertEqual(hint["snippet"], section + "\n")
        text = self.apply("--acceptance-check", "逐项核对产物与来源").stdout
        self.assertIn("INSTRUCTIONS.md lacks: Context Budget section", text)
        self.assertIn("## Context Budget", text.split("----- BEGIN harness merge section -----")[1])

    def test_snippet_carries_the_installed_numbers(self):
        self.install()
        path = self.root / ".harness/config.json"
        config = json.loads(path.read_text(encoding="utf-8"))
        config["context_budget"].update(output_lines=60, scratch_dir="var/tmp")
        path.write_text(json.dumps(config), encoding="utf-8")
        (self.root / "INSTRUCTIONS.md").write_text(without_section(self.read("INSTRUCTIONS.md")), encoding="utf-8")
        snippet = self.hints()["INSTRUCTIONS.md"]["snippet"]
        self.assertIn("一条命令合计最多 60 行", snippet)
        self.assertIn("`var/tmp/<YYYY-MM-DD>-<主题>.txt`", snippet)

    def test_missing_reader_only_warns_and_a_rerun_installs_it(self):
        self.install()
        (self.root / "scripts/harness_read.py").unlink()
        result = self.validate()
        self.assertEqual(result["overall_score"], 100)
        self.assertTrue(any("harness_read.py 缺失" in w for w in result["warnings"]))
        created = [item["path"] for item in json.loads(self.install().stdout)["plan"] if item["status"] == "create"]
        self.assertEqual(created, ["scripts/harness_read.py"])

    def test_agents_lacking_only_the_budget_sentence_gets_that_sentence(self):
        template = (SKILL / "assets/minimal/AGENTS.md.tmpl").read_text(encoding="utf-8")
        self.assertIn(harness_merge.AGENTS_CONTEXT_SENTENCE, template)
        fragment = (SKILL / "assets/fragments/agents-merge-section.md").read_text(encoding="utf-8")
        self.assertIn("- " + harness_merge.AGENTS_CONTEXT_SENTENCE + "\n", fragment)
        self.install()
        agents = self.root / "AGENTS.md"
        sentence = harness_merge.agents_context_sentence()
        self.assertIn(sentence, self.read("AGENTS.md"))
        agents.write_text(self.read("AGENTS.md").replace(sentence, ""), encoding="utf-8")
        script = self.root / "scripts/check-project-harness.py"
        script.write_text(self.read("scripts/check-project-harness.py").replace("AGENTS_REQUIRED_ROUTES", "OLD"),
                          encoding="utf-8")
        hints = self.hints()
        self.assertEqual(hints["AGENTS.md"]["missing"], ["Reads and output follow the INSTRUCTIONS.md Context Budget"])
        self.assertEqual(hints["AGENTS.md"]["snippet"], sentence + "\n")
        self.assertNotIn("scripts/check-project-harness.py", hints)  # only a routing gap needs the routing lint
        self.assertEqual(self.validate()["overall_score"], 100)
        # The hint carries the installed head_lines.
        config = json.loads(self.read(".harness/config.json"))
        config["context_budget"]["head_lines"] = 25
        (self.root / ".harness/config.json").write_text(json.dumps(config), encoding="utf-8")
        self.assertIn('只回结论（不超过 25 行，每条带"文件:行"）', self.hints()["AGENTS.md"]["snippet"])

    def test_an_older_project_check_is_asked_to_merge_the_context_budget_lint(self):
        self.install()
        script = self.root / "scripts/check-project-harness.py"
        script.write_text("print('older project check')\nAGENTS_REQUIRED_ROUTES = ()\n", encoding="utf-8")
        before = snapshot(self.root)
        hint = self.hints()["scripts/check-project-harness.py"]
        self.assertEqual(snapshot(self.root), before)
        self.assertEqual(hint["missing"], [label for label, _ in harness_merge.PROJECT_CHECK_PARTS])
        # Together with an AGENTS.md that needs the routing lint, one hint lists both.
        script.write_text("print('older project check')\n", encoding="utf-8")
        (self.root / "AGENTS.md").write_text("# 阅读契约\n\n先读 index.md。\n", encoding="utf-8")
        missing = self.hints()["scripts/check-project-harness.py"]["missing"]
        self.assertEqual(missing[0], "AGENTS.md routing lint (AGENTS_REQUIRED_ROUTES)")
        self.assertEqual(len(missing), 1 + len(harness_merge.PROJECT_CHECK_PARTS))

    def test_a_mention_without_the_heading_still_counts_as_missing(self):
        self.install()
        text = without_section(self.read("INSTRUCTIONS.md")) + "\n读取规则以后按 Context Budget（上下文预算）补。\n"
        (self.root / "INSTRUCTIONS.md").write_text(text, encoding="utf-8")
        self.assertEqual(self.hints()["INSTRUCTIONS.md"]["missing"], ["Context Budget section"])
        self.assertIn("INSTRUCTIONS.md 缺 Context Budget 节；从模板或合并提示补上", self.validate()["warnings"])
        (self.root / "INSTRUCTIONS.md").write_text(text + "\n## 上下文预算\n\n项目自己的读取规则。\n", encoding="utf-8")
        self.assertNotIn("INSTRUCTIONS.md", self.hints())

    def test_config_without_the_block_and_an_older_budget_script_are_flagged(self):
        self.install()
        path = self.root / ".harness/config.json"
        config = json.loads(path.read_text(encoding="utf-8"))
        del config["context_budget"]
        path.write_text(json.dumps(config), encoding="utf-8")
        budget = self.root / "scripts/check-startup-doc-budget.py"
        budget.write_text("print('older budget check')\n", encoding="utf-8")
        before = snapshot(self.root)
        hints = self.hints()
        self.assertEqual(snapshot(self.root), before)
        self.assertEqual(hints[".harness/config.json"]["missing"], ["context_budget block (read by scripts/harness_read.py)"])
        self.assertEqual(json.loads("{" + hints[".harness/config.json"]["snippet"] + "}")["context_budget"],
                         default_context_budget())
        self.assertEqual(len(hints["scripts/check-startup-doc-budget.py"]["missing"]), 4)
        budget.write_text("def progress_shape(text):\n    pass\n", encoding="utf-8")  # a D0035-style project script
        missing = self.hints()["scripts/check-startup-doc-budget.py"]["missing"]
        self.assertEqual(len(missing), 3)
        self.assertFalse(any("progress_shape" in item for item in missing))


if __name__ == "__main__":
    unittest.main()
