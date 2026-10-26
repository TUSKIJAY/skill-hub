#!/usr/bin/env python3
"""readable-docs audit: read-only inventory of one project and a config draft.

Prints JSON on stdout and a short Chinese summary on stderr. Writes nothing in
the project; --draft-out saves the config draft to a path you choose (keep it
outside the project until the user has confirmed it).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check  # noqa: E402
import rd_common as common  # noqa: E402

AUDIT_SCHEMA = "readable-docs-audit-v1"
# A bare 12-digit lowercase hex token with a digit and a letter: ledger ids, long commit hashes.
HEX12_PATTERN = r"(?<![0-9A-Za-z`])(?=[0-9a-f]*\d)(?=[0-9a-f]*[a-f])[0-9a-f]{12}(?![0-9A-Za-z`])"
HEX12_RE = re.compile(HEX12_PATTERN)
DIGITS_RE = re.compile(r"\d+")
INDEX_ROW_RE = re.compile(r"^\|\s*\**`?([A-Za-z#][A-Za-z0-9#-]*\d)\b`?\**\s+([^|]+?)\s*\|")
NUMBERED_FILE_RE = re.compile(r"^\d{3,4}-[^/]+\.md$")
FROZEN_CANDIDATES = ("docs/exec-plans/completed", "docs/progress-archive", "docs/references",
                     "docs/archive", "archive")
DEFAULT_ID_EXAMPLE = "TASK-003（SD 卡挂载）"
EXAMPLES_PER_SHAPE = 5


def corpus(root: Path, files: List[str]) -> Dict[str, str]:
    texts = {}
    for rel in files:
        text = common.read_text(root / rel)
        if text is not None:
            texts[rel] = text
    return texts


def index_tables(texts: Dict[str, str]) -> List[dict]:
    """Index pages whose table rows start with an ID: candidate lookup sources."""
    tables = []
    for rel, text in texts.items():
        if Path(rel).name.lower() not in ("index.md", "readme.md"):
            continue
        rows = [m for m in (INDEX_ROW_RE.match(line) for line in text.splitlines()) if m]
        if len(rows) >= 3:
            tables.append({"file": rel, "rows": len(rows),
                           "examples": [{"id": m.group(1), "title": m.group(2).strip()} for m in rows[:3]]})
    return tables


def numbered_dirs(files: List[str]) -> List[str]:
    counts: Counter = Counter(str(Path(f).parent.as_posix()) for f in files if NUMBERED_FILE_RE.match(Path(f).name))
    return sorted(d for d, n in counts.items() if n >= 2)


def scan_ids(texts: Dict[str, str]) -> dict:
    builtin = {name: re.compile(pattern, re.ASCII) for name, pattern in check.BUILTIN_KINDS.items()}
    counts: Counter = Counter()
    hex12 = 0
    shapes: Counter = Counter()
    examples: Dict[str, List[str]] = {}
    for text in texts.values():
        for _, line in check.prose_lines(text):
            for name, pattern in builtin.items():
                counts[name] += len(pattern.findall(line))
            hex12 += len(HEX12_RE.findall(line))
            masked = check.mask(line)
            for match in check.UNREGISTERED_RE.finditer(masked):
                token = match.group(0)
                if any(p.fullmatch(token) for p in builtin.values()):
                    continue
                shape = DIGITS_RE.sub("<n>", token)
                shapes[shape] += 1
                bucket = examples.setdefault(shape, [])
                if token not in bucket and len(bucket) < EXAMPLES_PER_SHAPE:
                    bucket.append(token)
    return {
        "builtin": dict(counts),
        "bare_hex12": hex12,
        "unregistered": [{"shape": s, "count": n, "examples": examples[s]} for s, n in shapes.most_common()],
    }


def scan_terms(texts: Dict[str, str]) -> dict:
    members: Counter = Counter()
    marketing: Counter = Counter()
    for text in texts.values():
        for _, line in check.prose_lines(text):
            masked = check.mask(line)
            for group in check.SYNONYM_GROUPS:
                for member in group:
                    members[member] += len(check.member_positions(masked, member))
            for word in check.MARKETING_WORDS:
                marketing[word] += masked.count(word)
    groups = []
    for group in check.SYNONYM_GROUPS:
        present = {m: members[m] for m in group if members[m]}
        if len(present) >= 2:
            groups.append(present)
    return {"synonym_groups": groups, "marketing_words": {w: n for w, n in marketing.most_common() if n}}


def draft_config(root: Path, shape: dict, ids: dict, tables: List[dict], python: str) -> dict:
    config = json.loads(json.dumps(check.DEFAULT_CONFIG))
    config["skill_version"] = common.SKILL_VERSION
    ledger = (root / "scripts" / "harness_log.py").is_file()
    # Outside Git there is no log to read and no changed lines to compare against.
    commit_lookup = ({"type": "git", "run": "git log -1 --format=%s {id}"} if shape["git"]
                     else {"type": "manual", "hint": "项目不是 Git 仓库；提交号到它所在的仓库用 git log 查"})
    lookups = {
        "task-card": [{"type": "file-title", "hint": "任务卡文件的一级标题"}],
        "decision": ([{"type": "table", "file": t["file"]} for t in tables[:1]]
                     or [{"type": "file-title", "hint": "决策文件的一级标题"}]),
        "hex-ref": ([{"type": "command", "run": f"{python} scripts/harness_log.py query --grep {{id}}"}] if ledger else [])
        + [commit_lookup],
    }
    found = [name for name, n in ids["builtin"].items() if n]
    kinds = [{"name": name, "pattern": check.BUILTIN_KINDS[name], "lookup": lookups[name]}
             for name in (found or list(check.BUILTIN_KINDS))]
    if ids["bare_hex12"]:
        kinds.append({"name": "hex12", "pattern": HEX12_PATTERN, "lookup": lookups["hex-ref"]})
    config["id_kinds"] = kinds
    example = DEFAULT_ID_EXAMPLE
    if tables:
        first = tables[0]["examples"][0]
        example = f"{first['id']}（{first['title']}）"
    config["card"] = {
        "human_facing_kinds": "方案、计划、评审回复、研究报告、汇报和 HANDOFF" if shape["shape"] == "harness"
        else "方案、计划、评审回复、研究报告和汇报",
        "id_example": example,
        "registry_link": shape["config_path"],
    }
    config["templates"] = []
    config["check"] = {"changed_only": shape["git"]}
    return config


def audit(root: Path, python_override: Optional[str] = None) -> dict:
    shape = common.detect_shape(root)
    python = common.python_command(root, python_override)
    settings = check.build_settings(check.load_config(None))
    all_files = check.all_files(root)
    files = [p for p in all_files if check.human_facing(p, settings)]
    texts = corpus(root, files)
    joined = "".join(texts.values())
    tables = index_tables(texts)
    ids = scan_ids(texts)
    target = shape["card_target"]
    target_text = common.read_text(root / target) if target else None
    check_path = root / common.CHECK_TARGET
    return {
        "schema_version": AUDIT_SCHEMA,
        "skill_version": common.SKILL_VERSION,
        "root": str(root),
        **shape,
        "python_command": python,
        "learned_constraints_table": bool(target_text and "## Learned Constraints" in target_text),
        "existing": {
            "config": (root / shape["config_path"]).is_file(),
            "check_script": common.installed_check_version(check_path) if check_path.is_file() else None,
            "rule_card": bool(target_text and common.RULE_CARD_MARKER in target_text),
            "scripts_dir": (root / "scripts").is_dir(),
        },
        "human_facing": {
            "files": len(texts),
            "chars": len(joined),
            "cjk_ratio": round(len(check.CJK_RE.findall(joined)) / len(joined), 3) if joined else 0.0,
        },
        "ids": ids,
        "lookup_sources": {
            "index_tables": tables,
            "numbered_dirs": numbered_dirs(all_files),
            "git": shape["git"],
            "ledger": (root / "scripts" / "harness_log.py").is_file(),
        },
        "terms": scan_terms(texts),
        "template_candidates": sorted(p for p in all_files if p.endswith(".md") and "template" in Path(p).name),
        "frozen_candidates": [f"{d}/**" for d in FROZEN_CANDIDATES if (root / d).is_dir()],
        "config_draft": draft_config(root, shape, ids, tables, python),
    }


def summary(report: dict) -> str:
    lines = [
        f"项目形态：{report['shape']}；规则卡写入：{report['card_target'] or '不写（没有指令文件）'}；"
        f"配置：{report['config_path']}；Git：{'是' if report['git'] else '否'}。",
        f"给人看的文档：{report['human_facing']['files']} 个，约 {report['human_facing']['chars']} 字符，"
        f"中文占比 {report['human_facing']['cjk_ratio']}。",
        f"内置编号命中：{report['ids']['builtin']}；裸 12 位十六进制：{report['ids']['bare_hex12']}。",
    ]
    unregistered = report["ids"]["unregistered"][:8]
    if unregistered:
        lines.append("未登记的编号形状（前 8 种）：" + "；".join(
            f"{u['shape']}×{u['count']}（如 {'、'.join(u['examples'])}）" for u in unregistered))
    if report["terms"]["synonym_groups"]:
        lines.append("可能要声明为不同概念的词组：" + "；".join(
            "、".join(f"{m}×{n}" for m, n in g.items()) for g in report["terms"]["synonym_groups"]))
    lines.append("配置草稿在 JSON 的 config_draft 字段；先请用户确认编号种类、术语、冻结范围和档位。")
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    check.ensure_utf8_stdio()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--target", required=True, help="project root")
    parser.add_argument("--python-command", help="interpreter command for generated lines")
    parser.add_argument("--draft-out", help="also write config_draft to this path")
    args = parser.parse_args(argv)
    root = Path(args.target).expanduser().resolve()
    if not root.is_dir():
        print(f"ERROR: not a directory: {root}", file=sys.stderr)
        return 2
    out = Path(args.draft_out).expanduser().resolve() if args.draft_out else None
    if out is not None and (out == root or root in out.parents):
        print("ERROR: --draft-out must be outside the project; audit never writes into it.", file=sys.stderr)
        return 2
    if out is not None and out.exists():
        print(f"ERROR: {out} already exists; audit does not overwrite files.", file=sys.stderr)
        return 2
    try:
        report = audit(root, args.python_command)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(summary(report), file=sys.stderr)
    if out is not None:
        with open(out, "x", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(report["config_draft"], ensure_ascii=False, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
