#!/usr/bin/env python3
"""readable-docs apply: install the rule card, config and check into one project.

Preview by default; --apply writes. It only creates missing files, appends a
marked section or inserts one marked line; it never overwrites an existing file.
Files with uncommitted changes block the whole apply unless --allow-dirty.
Ledger entries, decision records and commits stay with the agent, who follows
the project's own rules; this script prints them as next steps.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path, PureWindowsPath
from typing import Callable, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import audit as auditor  # noqa: E402
import check  # noqa: E402
import rd_common as common  # noqa: E402

APPLY_SCHEMA = "readable-docs-apply-v1"
EXIT_OK, EXIT_ERROR, EXIT_BLOCKED = 0, 2, 3
H1_RE = re.compile(r"^# .*$", re.MULTILINE)


class Action:
    """One planned change. `write` performs it; None means report only."""

    def __init__(self, kind: str, path: Optional[str], status: str, detail: str,
                 write: Optional[Callable[[], None]] = None):
        self.kind, self.path, self.status, self.detail, self.write = kind, path, status, detail, write

    def as_dict(self) -> dict:
        return {"kind": self.kind, "path": self.path, "status": self.status, "detail": self.detail}


def inside(root: Path, rel: str) -> bool:
    """True when a relative path stays inside the project, symlinks resolved."""
    if not rel or Path(rel).is_absolute() or PureWindowsPath(rel).drive or PureWindowsPath(rel).root:
        return False
    try:
        (root / rel).resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def newline_of(text: str) -> str:
    return "\r\n" if "\r\n" in text else "\n"


def append_section(path: Path, section: str) -> Callable[[], None]:
    def run() -> None:
        raw = path.read_bytes()
        text = raw.decode(common.READ_ENCODING)
        nl = newline_of(text)
        body = section.replace("\n", nl)
        sep = "" if text.endswith(nl + nl) else nl if text.endswith(nl) else nl + nl
        prefix = b"\xef\xbb\xbf" if raw.startswith(b"\xef\xbb\xbf") else b""
        path.write_bytes(prefix + (text + sep + body).encode("utf-8"))
    return run


def insert_after_h1(path: Path, snippet: str) -> Callable[[], None]:
    def run() -> None:
        raw = path.read_bytes()
        text = raw.decode(common.READ_ENCODING)
        nl = newline_of(text)
        body = snippet.replace("\n", nl)
        match = H1_RE.search(text.replace("\r\n", "\n"))
        if match:
            # Map the position back when the file uses CRLF.
            head = text.replace("\r\n", "\n")[: match.end()]
            position = len(head.replace("\n", nl))
            updated = text[:position] + nl + nl + body.rstrip(nl) + text[position:]
        else:
            updated = body + nl + text
        prefix = b"\xef\xbb\xbf" if raw.startswith(b"\xef\xbb\xbf") else b""
        path.write_bytes(prefix + updated.encode("utf-8"))
    return run


def insert_verification_command(text: str, command: str) -> Optional[str]:
    """Add one entry to verification_commands by text edit, keeping the file's layout."""
    try:
        before = json.loads(text)
    except ValueError:
        return None
    commands = before.get("verification_commands")
    if not isinstance(commands, list):
        return None
    match = re.search(r'"verification_commands"\s*:\s*\[(.*?)\n?(\s*)\]', text, re.DOTALL)
    if not match:
        return None
    items, closing_indent = match.group(1), match.group(2).lstrip("\r\n")
    last_item = re.search(r'\n([ \t]*)"[^\n]*"\s*$', items)
    indent = last_item.group(1) if last_item else closing_indent + "  "
    entry = json.dumps(command, ensure_ascii=False)
    insert = ("," if items.strip() else "") + newline_of(text) + indent + entry
    position = match.start(1) + len(items.rstrip())
    updated = text[:position] + insert + text[position:]
    try:
        after = json.loads(updated)
    except ValueError:
        return None
    expected = dict(before, verification_commands=commands + [command])
    return updated if after == expected else None


def render_card(config: dict, check_command: str) -> str:
    card = config.get("card") or {}
    text = common.RULE_CARD_ASSET.read_text(encoding="utf-8")
    values = {
        "VERSION": common.SKILL_VERSION,
        "HUMAN_FACING_KINDS": card.get("human_facing_kinds", "方案、计划、评审回复、研究报告和汇报"),
        "ID_EXAMPLE": card.get("id_example", auditor.DEFAULT_ID_EXAMPLE),
        "REGISTRY_LINK": card.get("registry_link", "readable-docs.json"),
        "CHECK_COMMAND": check_command,
    }
    for key, value in values.items():
        text = text.replace("{{" + key + "}}", value)
    return text


def check_commands(report: dict, python: str, check_path: str) -> Tuple[str, str]:
    """(rule-card command, harness verification command); changed-line mode needs Git."""
    base = f"{python} {check_path}"
    if report["git"]:
        return f"{base} --changed", f"{base} --changed"
    return f"{base} --files <改过的文件>", f"{base} --report"


def plan(root: Path, report: dict, config: dict, python: str, check_path: str) -> List[Action]:
    actions: List[Action] = []
    config_rel = report["config_path"]
    config_file = root / config_rel
    config = dict(config, skill_version=common.SKILL_VERSION)
    config_text = json.dumps(config, ensure_ascii=False, indent=2) + "\n"
    if config_file.is_file():
        # The installed config is what check.py enforces, so it also drives the rule card.
        try:
            installed = json.loads(config_file.read_text(encoding=common.READ_ENCODING))
            check.build_settings(check.merge_config(installed, f"installed config {config_rel}"))
        except (OSError, ValueError) as exc:
            raise check.ConfigError(f"installed config {config_rel} is unreadable: {exc}") from exc
        strip = lambda c: {k: v for k, v in c.items() if k != "skill_version"}  # noqa: E731
        same = strip(installed) == strip(config)
        actions.append(Action("config", config_rel, "skip-exists" if same else "manual-merge",
                              "配置已存在，不覆盖" if same else
                              "已装配置和这次给的配置不同；规则卡和模板按已装配置渲染，差异请手工合并"))
        config = installed
    else:
        actions.append(Action("config", config_rel, "create", "写入已确认的配置",
                              lambda: write_text(config_file, config_text)))

    target_check = root / check_path
    source = common.CHECK_SOURCE.read_bytes()
    if not inside(root, check_path):
        actions.append(Action("check-script", check_path, "rejected-outside", "路径不在项目里，拒绝写入"))
    elif target_check.is_file():
        same = target_check.read_bytes() == source
        version = common.installed_check_version(target_check)
        actions.append(Action("check-script", check_path, "skip-same" if same else "manual-upgrade",
                              "与 skill 版本一致" if same else
                              f"项目里是 {version}，skill 是 {common.SKILL_VERSION}；用 upgrade 流程对比后再换"))
    elif not target_check.parent.is_dir() and check_path == common.CHECK_TARGET:
        actions.append(Action("check-script", check_path, "manual",
                              "项目没有 scripts/ 目录；问用户放哪，再用 --check-path 指定"))
    else:
        actions.append(Action("check-script", check_path, "create", f"拷贝 check.py {common.SKILL_VERSION}",
                              lambda: (target_check.parent.mkdir(parents=True, exist_ok=True),
                                       target_check.write_bytes(source))))

    card_command, check_command = check_commands(report, python, check_path)
    target = report["card_target"]
    if target is None:
        actions.append(Action("rule-card", None, "suggest",
                              "项目没有指令文件；不新建。用户同意后，建一个最小的 AGENTS.md 再运行 apply"))
    else:
        target_file = root / target
        text = common.read_text(target_file) or ""
        if common.RULE_CARD_MARKER in text:
            actions.append(Action("rule-card", target, "skip-present", "规则卡已在"))
        else:
            actions.append(Action("rule-card", target, "append-section", "在文件末尾追加\"给人看的文字\"一节",
                                  append_section(target_file, render_card(config, card_command))))

    if report["shape"] == "harness":
        harness_file = root / common.HARNESS_CONFIG
        text = common.read_text(harness_file) or ""
        try:
            present = check_command in (json.loads(text).get("verification_commands") or [])
        except ValueError:
            present = False
        if present:
            actions.append(Action("verification-command", common.HARNESS_CONFIG, "skip-present", check_command))
        else:
            updated = insert_verification_command(text, check_command)
            if updated is None:
                actions.append(Action("verification-command", common.HARNESS_CONFIG, "manual",
                                      f"无法安全插入；请手工加入 {check_command}"))
            else:
                bom = b"\xef\xbb\xbf" if harness_file.read_bytes().startswith(b"\xef\xbb\xbf") else b""
                actions.append(Action("verification-command", common.HARNESS_CONFIG, "insert",
                                      check_command, lambda: harness_file.write_bytes(bom + updated.encode("utf-8"))))

    snippet = common.SUMMARY_ASSET.read_text(encoding="utf-8")
    for rel in config.get("templates", []):
        path = root / rel
        if not isinstance(rel, str) or not inside(root, rel):
            actions.append(Action("template", str(rel), "rejected-outside", "路径不在项目里，拒绝写入"))
            continue
        text = common.read_text(path)
        if text is None:
            actions.append(Action("template", rel, "missing", "配置里列了这个模板，但文件不存在"))
        elif common.SUMMARY_MARKER in text:
            actions.append(Action("template", rel, "skip-present", "摘要片段已在"))
        else:
            actions.append(Action("template", rel, "insert-summary", "在一级标题后插入\"给审阅人的摘要\"",
                                  insert_after_h1(path, snippet)))
    return actions


def next_steps(report: dict, python: str, check_path: str) -> List[str]:
    steps = [f"跑 `{python} {check_path} --report` 看现有文档的基线，确认没有读不到的文件。"]
    if report["shape"] == "harness":
        steps.append("按项目规则追加账本事件、同步 PROGRESS/HANDOFF；规则变更按项目要求登记决定。")
        steps.append("跑项目自己的结构检查和启动篇幅检查，再按提交门禁提交。")
    else:
        steps.append("按项目自己的提交规矩提交改动。")
    return steps


def main(argv: Optional[List[str]] = None) -> int:
    check.ensure_utf8_stdio()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--target", required=True, help="project root")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--config", help="the user-confirmed config JSON")
    source.add_argument("--use-draft", action="store_true", help="use the audit draft as is")
    parser.add_argument("--apply", action="store_true", help="write; without it only preview")
    parser.add_argument("--allow-dirty", action="store_true", help="allow files with uncommitted changes")
    parser.add_argument("--python-command", help="interpreter command for generated lines")
    parser.add_argument("--check-path", default=common.CHECK_TARGET, help="where to copy check.py")
    args = parser.parse_args(argv)

    root = Path(args.target).expanduser().resolve()
    if not root.is_dir():
        print(f"ERROR: not a directory: {root}", file=sys.stderr)
        return EXIT_ERROR
    try:
        python = common.python_command(root, args.python_command)
        report = auditor.audit(root, python)
        if args.config:
            config = json.loads(Path(args.config).read_text(encoding=common.READ_ENCODING))
        else:
            config = report["config_draft"]
        check.build_settings(check.merge_config(config, "confirmed config"))
        actions = plan(root, report, config, python, args.check_path)
    except (OSError, ValueError, check.ConfigError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_ERROR

    rejected = [a for a in actions if a.status == "rejected-outside"]
    writes = [a for a in actions if a.write is not None]
    blocked = [] if args.allow_dirty else [
        a for a in writes if a.path and (root / a.path).exists() and common.dirty(root, a.path)]
    for action in blocked:
        action.status, action.detail = "blocked-dirty", "文件有未提交的改动；核对后用 --allow-dirty"
    if args.apply and not blocked and not rejected:
        for action in writes:
            action.write()
            action.status = "done:" + action.status
    payload = {
        "schema_version": APPLY_SCHEMA,
        "skill_version": common.SKILL_VERSION,
        "root": str(root),
        "shape": report["shape"],
        "mode": "apply" if args.apply else "preview",
        "applied": bool(args.apply and not blocked and not rejected),
        "actions": [a.as_dict() for a in actions],
        "next_steps": next_steps(report, python, args.check_path),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    for action in actions:
        print(f"[{action.status}] {action.kind} {action.path or '-'}：{action.detail}", file=sys.stderr)
    if rejected:
        print("有写入路径不在项目里，本次没有写入任何文件。", file=sys.stderr)
        return EXIT_ERROR
    if blocked:
        print("有文件存在未提交的改动，本次没有写入任何文件。", file=sys.stderr)
        return EXIT_BLOCKED
    if not args.apply:
        print("这是预览，没有写入。确认后加 --apply。", file=sys.stderr)
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
