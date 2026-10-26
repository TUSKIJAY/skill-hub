"""Hand-merge hints for an existing AGENTS.md and other skipped state files; never installed into projects."""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
import unittest

from harness_test_support import SCRIPTS, SKILL, ProjectTestCase

sys.path.insert(0, str(SCRIPTS))
import harness_merge  # noqa: E402
from harness_checks import agents_requirements, contains_all  # noqa: E402

EXIT_FAIL = 1
READING_CONTRACT = "# 阅读契约\n\n先读 index.md，再按问题进入对应小节。原文节选逐字不改。\n"


def snapshot(root):
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob("*") if p.is_file() and ".git" not in p.relative_to(root).parts}


class ManualMergeTests(ProjectTestCase):
    def preview(self):
        return json.loads(self.apply("--json", "--acceptance-check", "逐项核对产物与来源").stdout)

    def validate(self, expected=0):
        return json.loads(self.run_script(SCRIPTS / "validate_harness.py", "--target", self.root, "--json",
                                          expected=expected).stdout)

    def local_check(self, expected=0):
        return json.loads(self.run_script(self.root / "scripts/check-project-harness.py", "--root", self.root,
                                          expected=expected).stdout)

    def git_init(self):
        for args in (("init", "-q"), ("config", "user.name", "t"), ("config", "user.email", "t@invalid")):
            subprocess.run(["git", "-C", str(self.root), *args], check=True, capture_output=True)

    def agents_hint(self, payload):
        return next(h for h in payload["manual_merge"] if h["path"] == "AGENTS.md")

    def test_existing_agents_gets_missing_list_and_snippet_without_writes(self):
        (self.root / "AGENTS.md").write_text(READING_CONTRACT, encoding="utf-8")
        before = snapshot(self.root)
        hint = self.agents_hint(self.preview())
        self.assertEqual(snapshot(self.root), before)
        self.assertIn("Startup contract routes all four root state files", hint["missing"])
        self.assertIn("Completion and recoverable-version policy is explicit (non-Git)", hint["missing"])
        self.assertIn("Definition of Done is stated", hint["missing"])
        for text in ("PROGRESS.md", "HANDOFF.md", "INSTRUCTIONS.md", "harness_log.py", "可恢复"):
            self.assertIn(text, hint["snippet"])
        self.assertNotIn("git status", hint["snippet"])
        self.assertNotIn("{{", hint["snippet"])
        text_mode = self.apply("--acceptance-check", "逐项核对产物与来源").stdout
        self.assertIn("AGENTS.md lacks:", text_mode)
        pasted = text_mode.split("----- BEGIN harness merge section -----\n", 1)[1].split("\n----- END", 1)[0]
        self.assertEqual(pasted + "\n", hint["snippet"])

    def test_install_next_to_unmerged_agents_fails_until_snippet_is_pasted(self):
        (self.root / "AGENTS.md").write_text(READING_CONTRACT, encoding="utf-8")
        snippet = self.agents_hint(self.preview())["snippet"]
        self.install()
        self.assertEqual(self.read("AGENTS.md"), READING_CONTRACT)
        self.assertFalse(self.validate(expected=EXIT_FAIL)["passed"])
        lint = self.local_check(expected=EXIT_FAIL)["lint_failures"]
        self.assertIn("AGENTS.md routes to `PROGRESS.md`", lint)
        with (self.root / "AGENTS.md").open("a", encoding="utf-8", newline="\n") as handle:
            handle.write("\n" + snippet)
        result = self.validate()
        self.assertEqual(result["overall_score"], 100)
        self.assertFalse(result["git_repository"])
        self.assertTrue(self.local_check()["passed"])
        self.assertEqual(self.preview()["manual_merge"], [])

    def test_git_project_snippet_carries_git_status_and_commit_rules(self):
        self.git_init()
        (self.root / "AGENTS.md").write_text(READING_CONTRACT, encoding="utf-8")
        hint = self.agents_hint(self.preview())
        self.assertIn("Git status is part of startup", hint["missing"])
        self.assertIn("git status --short --branch", hint["snippet"])
        self.assertIn("提交", hint["snippet"])
        self.install("--allow-dirty")
        with (self.root / "AGENTS.md").open("a", encoding="utf-8", newline="\n") as handle:
            handle.write("\n" + hint["snippet"])
        result = self.validate()
        self.assertTrue(result["git_repository"])
        self.assertEqual(result["overall_score"], 100)

    def test_rendered_snippet_meets_every_agents_requirement(self):
        for is_git in (True, False):
            with self.subTest(is_git=is_git):
                snippet = harness_merge.render_agents_section(is_git, "python")
                for requirement in agents_requirements(is_git).values():
                    self.assertTrue(contains_all(snippet, requirement["groups"]), requirement["label"])

    def test_template_install_needs_no_merge(self):
        self.install()
        self.assertEqual(self.preview()["manual_merge"], [])

    def test_existing_progress_and_handoff_list_missing_fields(self):
        (self.root / "PROGRESS.md").write_text("# 我的进度\n\n- 已完成第一章\n", encoding="utf-8")
        (self.root / "HANDOFF.md").write_text("# 交接\n\n- progress_ref: PROGRESS.md\n", encoding="utf-8")
        hints = {h["path"]: h for h in self.preview()["manual_merge"]}
        self.assertIn("## Facts", hints["PROGRESS.md"]["missing"])
        self.assertNotIn("progress_ref:", hints["HANDOFF.md"]["missing"])
        self.assertIn("first_action:", hints["HANDOFF.md"]["missing"])
        self.assertIsNone(hints["PROGRESS.md"]["snippet"])

    def test_checksum_manifest_listing_a_merged_file_is_flagged(self):
        (self.root / "AGENTS.md").write_text(READING_CONTRACT, encoding="utf-8")
        (self.root / "MANIFEST.sha256").write_text("0" * 64 + "  AGENTS.md\n", encoding="utf-8")
        hints = {h["path"]: h for h in self.preview()["manual_merge"]}
        self.assertEqual(hints["MANIFEST.sha256"]["kind"], "checksum-manifest")
        self.assertEqual(hints["MANIFEST.sha256"]["missing"], ["update the entry for AGENTS.md after the merge"])

    def test_only_real_checksum_files_count_as_manifests(self):
        (self.root / "AGENTS.md").write_text(READING_CONTRACT, encoding="utf-8")
        (self.root / "manifest.json").write_text('{"name": "web app", "icons": []}', encoding="utf-8")
        (self.root / "MANIFEST.in").write_text("include README.md\n", encoding="utf-8")
        (self.root / "SHA256SUMS").write_bytes(("a" * 64 + "  agents.md\n").encode("utf-16"))
        hints = {h["path"]: h for h in self.preview()["manual_merge"]}
        self.assertNotIn("manifest.json", hints)
        self.assertNotIn("MANIFEST.in", hints)
        self.assertEqual(hints["SHA256SUMS"]["missing"], ["update the entry for AGENTS.md after the merge"])

    def test_existing_config_without_acceptance_is_flagged(self):
        self.apply("--apply")
        hints = {h["path"]: h for h in json.loads(self.apply("--json").stdout)["manual_merge"]}
        self.assertEqual(hints[".harness/config.json"]["missing"], ["acceptance_checks or verification_commands"])

    def test_rerun_reuses_the_installed_python_command(self):
        self.install("--python-command", "py -3")
        (self.root / "AGENTS.md").write_text(READING_CONTRACT, encoding="utf-8")
        payload = json.loads(self.apply("--json").stdout)
        self.assertEqual(payload["python_command"], "py -3")
        self.assertIn("py -3 scripts/harness_log.py", self.agents_hint(payload)["snippet"])

    def test_filling_the_listed_progress_and_handoff_items_passes_the_project_check(self):
        (self.root / "PROGRESS.md").write_text("# 我的进度\n\n- 已完成第一章\n", encoding="utf-8")
        (self.root / "HANDOFF.md").write_text("# 交接\n", encoding="utf-8")
        hints = {h["path"]: h for h in self.preview()["manual_merge"]}
        self.assertIn("pointer to scripts/harness_log.py for history reads", hints["PROGRESS.md"]["missing"])
        self.install()
        self.local_check(expected=EXIT_FAIL)
        with (self.root / "PROGRESS.md").open("a", encoding="utf-8", newline="\n") as handle:
            for heading in harness_merge.PROGRESS_REQUIRED_HEADINGS:
                handle.write(f"\n{heading}\n\n- 无。\n")
            handle.write("\n历史经 `python3 scripts/harness_log.py query` 按需检索。\n")
        with (self.root / "HANDOFF.md").open("a", encoding="utf-8", newline="\n") as handle:
            for key in harness_merge.HANDOFF_REQUIRED_KEYS:
                handle.write(f"- {key} 无额外项。\n")
        self.assertTrue(self.local_check()["passed"])
        self.assertEqual([h for h in self.preview()["manual_merge"] if h["path"] in ("PROGRESS.md", "HANDOFF.md")], [])

    def test_project_check_matches_route_names_case_insensitively(self):
        self.install()
        agents = self.root / "AGENTS.md"
        agents.write_text(self.read("AGENTS.md").replace("PROGRESS.md", "progress.md"), encoding="utf-8")
        self.assertTrue(self.local_check()["passed"])

    def test_failed_git_status_counts_as_dirty(self):
        self.git_init()
        subprocess.run(["git", "-C", str(self.root), "commit", "-q", "--allow-empty", "-m", "base"], check=True,
                       capture_output=True)
        (self.root / ".git/index").write_bytes(b"corrupt")
        audit = json.loads(self.run_script(SCRIPTS / "audit_harness.py", "--target", self.root, "--json").stdout)
        self.assertTrue(audit["git"]["dirty"])
        self.assertTrue(audit["git"]["status_error"])
        self.apply("--apply", expected=2)
        self.assertFalse((self.root / "PROGRESS.md").exists())

    def test_snippet_carries_the_context_budget_sentence_with_the_installed_head_lines(self):
        for is_git in (True, False):
            with self.subTest(is_git=is_git):
                self.assertIn(harness_merge.agents_context_sentence(),
                              harness_merge.render_agents_section(is_git, "python"))
                snippet = harness_merge.render_agents_section(is_git, "python", {"head_lines": 25})
                self.assertIn(harness_merge.agents_context_sentence({"head_lines": 25}), snippet)
                self.assertIn('只回结论（不超过 25 行，每条带"文件:行"），不回原文。', snippet)

    def test_snippet_keeps_the_read_only_exception_for_assumptions(self):
        for is_git in (True, False):
            self.assertIn("只读问答在回答里说明假设即可", harness_merge.render_agents_section(is_git, "python"))

    def test_older_project_check_without_routing_lint_is_flagged_with_the_agents_merge(self):
        self.install()
        script = self.root / "scripts/check-project-harness.py"
        self.assertEqual([h for h in self.preview()["manual_merge"] if h["path"] == script.name], [])
        (self.root / "AGENTS.md").write_text(READING_CONTRACT, encoding="utf-8")
        hints = {h["path"]: h for h in self.preview()["manual_merge"]}
        self.assertNotIn("scripts/check-project-harness.py", hints)
        script.write_text(script.read_text(encoding="utf-8").replace("AGENTS_REQUIRED_ROUTES", "OLD_NAME"),
                          encoding="utf-8")
        hints = {h["path"]: h for h in self.preview()["manual_merge"]}
        self.assertIn("AGENTS.md routing lint (AGENTS_REQUIRED_ROUTES)", hints["scripts/check-project-harness.py"]["missing"])

    def test_large_manifest_is_streamed_and_listing_found_at_the_end(self):
        (self.root / "AGENTS.md").write_text(READING_CONTRACT, encoding="utf-8")
        line = "f" * 64 + "  images/frame-%05d.jpg\n"
        body = "".join(line % n for n in range(50000)) + "0" * 64 + "  AGENTS.md\n"
        (self.root / "SHA256SUMS").write_text(body, encoding="utf-8")
        hints = {h["path"]: h for h in self.preview()["manual_merge"]}
        self.assertEqual(hints["SHA256SUMS"]["missing"], ["update the entry for AGENTS.md after the merge"])

    def test_merge_constants_match_the_generated_project_check(self):
        source = (SKILL / "assets/minimal/scripts/check-project-harness.py.tmpl").read_text(encoding="utf-8")
        for name, values in (("PROGRESS_REQUIRED_HEADINGS", harness_merge.PROGRESS_REQUIRED_HEADINGS),
                             ("HANDOFF_REQUIRED_KEYS", harness_merge.HANDOFF_REQUIRED_KEYS)):
            block = re.search(name + r" = \((.*?)\n\)", source, re.S).group(1)
            self.assertEqual(tuple(re.findall(r'"([^"]+)"', block)), values, name)


if __name__ == "__main__":
    unittest.main()
