#!/usr/bin/env python3
"""readable-docs check: mechanical checks for human-facing Markdown.

Installed into a project as scripts/check-readable-docs.py. Standard library
only, Python 3.9+. Reads the project config (.harness/readable-docs.json, then
readable-docs.json); without one it uses the built-in defaults.

Modes:
  --changed (default)  lines changed against HEAD: staged, unstaged, untracked
  --files PATH...      whole files, as given
  --report             every human-facing file; statistics only, never blocks

Exit codes: 0 no block-level finding; 1 a block-level finding; 2 unreadable
input, a bad config, or --changed outside a Git work tree.

The check is mechanical. Zero findings does not prove a text is clear, and it
cannot prove that a gloss matches its record. Modal words (可能, 也许, 大概,
倾向于) are never flagged: confidence is content.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

CHECK_VERSION = "0.1.1"
SCHEMA_VERSION = "readable-docs-check-v1"
CONFIG_SCHEMA = "readable-docs-config-v1"
CONFIG_CANDIDATES = (".harness/readable-docs.json", "readable-docs.json")
READ_ENCODING = "utf-8-sig"
EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
# Quoted originals and counterexamples go between these markers and are not checked.
OFF_MARKER = "<!-- readable-docs:off -->"
ON_MARKER = "<!-- readable-docs:on -->"
EXIT_OK, EXIT_BLOCK, EXIT_ERROR = 0, 1, 2
WARN, BLOCK, OFF = "warn", "block", "off"
LEVELS = (WARN, BLOCK, OFF)

ID_RULES = ("bare-id-run", "first-mention", "unregistered-id")
SENTENCE_RULES = (
    "semicolon", "long-sentence", "nominalization", "marketing-adjective",
    "empty-phrase", "synonym-rotation", "passive-voice", "compound-aspect",
    "vague-word", "halfwidth-punct", "dash-join",
)
RULES = ID_RULES + SENTENCE_RULES

# Built-in ID kinds; a project config replaces them with its own list.
BUILTIN_KINDS: Dict[str, str] = {
    "task-card": r"TASK-\d+",
    "decision": r"#D\d+|\bD\d{3,}\b",
    "hex-ref": r"`(?=[0-9A-Fa-f]*\d)[0-9A-Fa-f]{6,12}`",
}

DEFAULT_CONFIG: Dict[str, object] = {
    "schema_version": CONFIG_SCHEMA,
    "language": "zh",
    "human_facing": {
        "include": ["**/*.md"],
        "exclude": ["**/node_modules/**", "**/.git/**", "CHANGELOG.md"],
    },
    "frozen": [],
    "id_kinds": [{"name": name, "pattern": pattern} for name, pattern in BUILTIN_KINDS.items()],
    "terms": {"distinct": [], "allow": [], "define": {}},
    "rules": {rule: WARN for rule in RULES},
    "max_chars": {"instruction": 25, "explanation": 40},
    "check": {"changed_only": True},
}

# --- ID rules ---------------------------------------------------------------

SEPARATORS = r"[、,，;；\s　]*"
GAP_RE = re.compile(SEPARATORS, re.ASCII)
PAREN_RE = re.compile(r"[（(]([^（）()]*)[）)]")
LEADING_MARKER_RE = re.compile(r"^\s*(?:[-*+>]|#+|\d+[.)])?\s*")
# Between an ID and its gloss: a closing backtick or bold mark, a Markdown link target.
GLOSS_GAP_RE = re.compile(r"(?:`|\*\*)?(?:\]\([^)]*\))?(?:\*\*)?[ \t　]*")
GLOSS_WORD_RE = re.compile(r"[㐀-鿿A-Za-z]")
# Looks like an ID but is not registered: BUG-123, Review-007, D3, P1-6, Q1.
# Common technical names (UTF-8, SHA-256, ISO-8601) are not IDs.
UNREGISTERED_RE = re.compile(
    r"\b(?!(?:UTF|SHA|ISO|HTTP|HTTPS|TLS|SSL|GB|MD|AES|RSA|CRC|IPV|UTC|GMT)-)[A-Z]{2,10}-\d{1,5}\b"
    r"|\b[A-Z][a-z]{3,9}-\d{1,4}\b|\b[A-Z]\d{1,3}(?:-\d{1,3})?\b",
    re.ASCII,
)
# ID rules keep inline code (backticked hashes are IDs) but skip link targets, URLs and comments.
ID_MASK_RE = re.compile(r"https?://\S+|\]\([^)]*\)|<!--.*?-->")

# --- sentence rules (adapted from ste-zh, MIT; see NOTICE.md) -------------

CJK_RE = re.compile(r"[㐀-䶿一-鿿豈-﫿]")
TOKEN_RE = re.compile(r"[A-Za-z0-9_]+")
SENTENCE_END_RE = re.compile(r"[。！？!?]+")
LIST_MARK_RE = re.compile(r"^(\s*(?:#{1,6}|[-*+]|\d{1,3}[.)]|>)\s+)")
MASK_RE = re.compile(r"`[^`\n]*`|https?://\S+|\]\([^)]*\)|<!--.*?-->")
SEMICOLON_RE = re.compile(r"[；;]")
NOMINALIZATION_RE = re.compile(
    r"(进行|作出|加以|予以|给予|开展)(一[下个次些])?[^，。！？；、\s]{0,6}?"
    r"(分析|检查|处理|优化|验证|评估|讨论|说明|调整|改造|升级|计算|统计|测试|"
    r"梳理|比对|排查|确认|审核|复盘|治理|维护|修复|部署|设计|规划|调研|探索|实践|尝试)"
)
# 被动 (passive), 被子 (quilt), 被告 (defendant) are nouns, not passive markers.
PASSIVE_RE = re.compile(r"被(?![动子告])[^，。！？；\s]{0,6}")
COMPOUND_ASPECT_RE = re.compile(r"(已经[^，。！？；]{0,10}[了过]|正在[^，。！？；]{0,8}[中着])")
VAGUE_RE = re.compile(r"(相关|有关|若干|一些|适当|酌情|必要时|等等|之类|大致|差不多|一定程度)")
HALFWIDTH_RE = re.compile(r"(?<=[一-鿿])[,;:!?](?=[一-鿿])")
DASH_JOIN_RE = re.compile(r"——")
MARKETING_WORDS = (
    "无缝", "强大", "赋能", "闭环", "极致", "丝滑", "一站式", "全方位", "颠覆",
    "领先", "顶级", "沉浸式", "智能化", "黑科技", "革命性", "独创", "完美",
    "极速", "超强", "降维打击",
)
EMPTY_PHRASES = (
    "需要注意的是", "值得一提的是", "众所周知", "不难看出", "不言而喻",
    "在一定程度上", "某种意义上", "从某种角度", "综上所述", "显而易见",
    "毋庸置疑", "总的来说",
)
SYNONYM_GROUPS: Tuple[Tuple[str, ...], ...] = (
    ("用户", "客户", "使用者", "终端用户"),
    ("删除", "移除", "清除", "删掉"),
    ("检查", "校验", "核对", "核查"),
    ("创建", "新建", "建立", "生成"),
    ("错误", "异常", "报错", "故障"),
    ("配置", "设置", "设定"),
    ("显示", "展示", "呈现"),
    ("运行", "执行"),
    ("保存", "存储"),
    ("修改", "更改", "变更"),
)
# Chinese has no word boundaries: 客户端 is not 客户, 检查点 is not 检查.
SYNONYM_BLOCKED_SUFFIX: Dict[str, Tuple[str, ...]] = {
    "用户": ("名",), "客户": ("端",), "检查": ("点",), "创建": ("时间",),
    "生成": ("式",), "显示": ("器",), "运行": ("时",), "错误": ("码",),
}

MESSAGES = {
    "bare-id-run": "连续堆叠的编号没有说明。给每个编号带一句说明。",
    "first-mention": "编号第一次出现，后面没有括号说明。按原始记录补一句说明。",
    "unregistered-id": "像编号，但不在配置的编号种类里。登记它，或改写成普通文字。",
    "semicolon": "分号把几件事串进一句。拆成几句。",
    "long-sentence": "句子 {n} 字，上限 {limit} 字。拆开，或删掉不必要的信息。",
    "nominalization": "虚动词加名词。直接用动词。",
    "marketing-adjective": "营销形容词。删掉，或换成能证明的说法。",
    "empty-phrase": "套话。删掉，直接说事。",
    "synonym-rotation": "同一概念换着说法：{found}。全篇用一个，建议「{keeper}」。",
    "passive-voice": "被动语态。说清施事并改用主动，施事未知或无关时可保留。",
    "compound-aspect": "复合体貌。简单说法够用就简化；表达当前状态时保留。",
    "vague-word": "含糊词。给出数量、范围或条件。",
    "halfwidth-punct": "中文句子里的半角标点。换成全角。",
    "dash-join": "破折号连接。通常说明这句话该拆。",
}


class ConfigError(Exception):
    """The project config cannot be used."""


@dataclass
class Finding:
    path: str
    line: int
    col: int
    rule: str
    level: str
    message: str
    match: str

    def as_dict(self) -> dict:
        return dict(self.__dict__)

    def render(self) -> str:
        return f"{self.path}:{self.line}:{self.col}: {self.level} {self.rule}: {self.message} [{self.match}]"


@dataclass
class Settings:
    levels: Dict[str, str]
    id_re: Optional["re.Pattern[str]"]
    evidence_re: Optional["re.Pattern[str]"]
    max_chars: int
    allow: Set[str]
    distinct: List[Set[str]]
    include: List["re.Pattern[str]"]
    exclude: List["re.Pattern[str]"]
    frozen: List["re.Pattern[str]"]


def ensure_utf8_stdio() -> None:
    """Force UTF-8 stdout/stderr so Chinese text survives a GBK console or pipe."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError, ValueError) as exc:
            print(f"WARNING: cannot switch output to UTF-8: {exc}", file=sys.stderr)


def glob_to_regex(pattern: str) -> "re.Pattern[str]":
    """Translate a path glob with ** into a regex over POSIX relative paths."""
    out, i = "", 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out, i = out + "(?:.*/)?", i + 3
        elif pattern.startswith("**", i):
            out, i = out + ".*", i + 2
        elif pattern[i] == "*":
            out, i = out + "[^/]*", i + 1
        elif pattern[i] == "?":
            out, i = out + "[^/]", i + 1
        else:
            out, i = out + re.escape(pattern[i]), i + 1
    return re.compile(out + r"\Z")


def matches_any(path: str, patterns: Sequence["re.Pattern[str]"]) -> bool:
    return any(p.match(path) for p in patterns)


def find_config(root: Path, explicit: Optional[str]) -> Optional[Path]:
    if explicit:
        path = Path(explicit)
        return path if path.is_absolute() else root / path
    for candidate in CONFIG_CANDIDATES:
        if (root / candidate).is_file():
            return root / candidate
    return None


def merge_config(data: object, source: str = "config") -> dict:
    """Defaults overlaid with a project config; rule levels merge key by key."""
    if not isinstance(data, dict) or data.get("schema_version") != CONFIG_SCHEMA:
        raise ConfigError(f"{source} must be an object with schema_version {CONFIG_SCHEMA}")
    merged = json.loads(json.dumps(DEFAULT_CONFIG))
    for key, value in data.items():
        if key == "rules" and isinstance(value, dict):
            merged["rules"].update(value)
        else:
            merged[key] = value
    return merged


def load_config(path: Optional[Path]) -> dict:
    if path is None:
        return json.loads(json.dumps(DEFAULT_CONFIG))
    try:
        data = json.loads(path.read_text(encoding=READ_ENCODING))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ConfigError(f"cannot read config {path}: {exc}") from exc
    return merge_config(data, f"config {path}")


def _strings(value: object, field: str) -> List[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ConfigError(f"{field} must be a list of strings")
    return value


def _mapping(value: object, field: str) -> dict:
    if not isinstance(value, dict):
        raise ConfigError(f"{field} must be an object")
    return value


def build_settings(config: dict) -> Settings:
    levels = _mapping(config.get("rules", {}), "rules")
    unknown = sorted(set(levels) - set(RULES))
    if unknown:
        raise ConfigError(f"unknown rules: {', '.join(unknown)}")
    bad = sorted(rule for rule, level in levels.items() if level not in LEVELS)
    if bad:
        raise ConfigError(f"rule levels must be warn, block or off: {', '.join(bad)}")
    terms = _mapping(config.get("terms") or {}, "terms")
    allow = _strings(terms.get("allow", []), "terms.allow")
    distinct_groups = terms.get("distinct", [])
    if not isinstance(distinct_groups, list):
        raise ConfigError("terms.distinct must be a list of string lists")
    distinct = [set(_strings(group, "terms.distinct[]")) for group in distinct_groups]
    human = _mapping(config.get("human_facing") or {}, "human_facing")
    include = _strings(human.get("include", ["**/*.md"]), "human_facing.include")
    exclude = _strings(human.get("exclude", []), "human_facing.exclude")
    frozen = _strings(config.get("frozen", []), "frozen")
    limit = _mapping(config.get("max_chars") or {}, "max_chars").get("explanation", 40)
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise ConfigError("max_chars.explanation must be a positive integer")
    kinds = config.get("id_kinds", [])
    if not isinstance(kinds, list):
        raise ConfigError("id_kinds must be a list")
    patterns: List[str] = []
    for kind in kinds:
        pattern = kind.get("pattern") if isinstance(kind, dict) else None
        if not isinstance(pattern, str) or not pattern:
            raise ConfigError(f"id kind without a pattern: {kind}")
        try:
            re.compile(pattern)
        except re.error as exc:
            raise ConfigError(f"bad pattern for id kind {kind.get('name')}: {exc}") from exc
        patterns.append(f"(?:{pattern})")
    id_pattern = "|".join(patterns)
    id_re = re.compile(id_pattern, re.ASCII) if id_pattern else None
    evidence_re = (
        re.compile(rf"{SEPARATORS}(?:(?:{id_pattern}){SEPARATORS})+", re.ASCII) if id_pattern else None
    )
    return Settings(
        levels={rule: levels.get(rule, WARN) for rule in RULES},
        id_re=id_re,
        evidence_re=evidence_re,
        max_chars=limit,
        allow=set(allow),
        distinct=distinct,
        include=[glob_to_regex(p) for p in include],
        exclude=[glob_to_regex(p) for p in exclude],
        frozen=[glob_to_regex(p) for p in frozen],
    )


# --- text walking -----------------------------------------------------------


def prose_lines(text: str) -> Iterable[Tuple[int, str]]:
    """(line number, line) outside front matter, fenced code, multi-line HTML comments
    and blocks between <!-- readable-docs:off --> and <!-- readable-docs:on -->."""
    lines = text.splitlines()
    start = 0
    if lines and lines[0].strip() == "---":
        for index in range(1, len(lines)):
            if lines[index].strip() in ("---", "..."):
                start = index + 1
                break
    fence: Optional[str] = None
    in_comment = False
    disabled = False
    for index in range(start, len(lines)):
        line = lines[index]
        stripped = line.lstrip()
        if stripped.startswith(OFF_MARKER):
            disabled = True
            continue
        if stripped.startswith(ON_MARKER):
            disabled = False
            continue
        if disabled:
            continue
        if fence:
            if stripped.startswith(fence):
                fence = None
            continue
        if stripped.startswith("```") or stripped.startswith("~~~"):
            fence = stripped[:3]
            continue
        if in_comment:
            if "-->" in line:
                in_comment = False
            continue
        if stripped.startswith("<!--") and "-->" not in stripped:
            in_comment = True
            continue
        yield index + 1, line


def mask(line: str, pattern: "re.Pattern[str]" = MASK_RE) -> str:
    """Blank inline code, URLs, link targets and comments so they are not read as prose."""
    chars = list(line)
    for match in pattern.finditer(line):
        for index in range(match.start(), match.end()):
            chars[index] = " "
    return "".join(chars)


def cells(line: str) -> List[Tuple[int, str]]:
    if not line.lstrip().startswith("|"):
        return [(0, line)]
    out, start = [], 0
    for index, char in enumerate(line):
        if char == "|":
            out.append((start, line[start:index]))
            start = index + 1
    out.append((start, line[start:]))
    return out


def sentences(line: str) -> Iterable[Tuple[int, str]]:
    for offset, cell in cells(line):
        mark = LIST_MARK_RE.match(cell)
        skip = mark.end() if mark else len(cell) - len(cell.lstrip())
        body = cell[skip:]
        base, start = offset + skip, 0
        for match in SENTENCE_END_RE.finditer(body):
            yield base + start, body[start:match.end()]
            start = match.end()
        if body[start:].strip():
            yield base + start, body[start:]


def count_chars(text: str) -> int:
    """One per CJK character, one per run of Latin letters or digits."""
    return len(CJK_RE.findall(text)) + len(TOKEN_RE.findall(text))


def member_positions(text: str, member: str) -> List[int]:
    blocked = SYNONYM_BLOCKED_SUFFIX.get(member, ())
    found, start = [], 0
    while True:
        index = text.find(member, start)
        if index < 0:
            return found
        if not any(text.startswith(suffix, index + len(member)) for suffix in blocked):
            found.append(index)
        start = index + len(member)


# --- per-file analysis ------------------------------------------------------


def evidence_spans(line: str, settings: Settings) -> List[Tuple[int, int]]:
    """Parentheticals holding only IDs that follow text: citations after a stated fact."""
    spans: List[Tuple[int, int]] = []
    if settings.evidence_re is None:
        return spans
    for match in PAREN_RE.finditer(line):
        before = LEADING_MARKER_RE.sub("", line[: match.start()], count=1).strip()
        if before and settings.evidence_re.fullmatch(match.group(1)):
            spans.append(match.span())
    return spans


def bare_id_runs(ids: List["re.Match[str]"], line: str) -> List[List["re.Match[str]"]]:
    runs, current = [], []
    for match in ids:
        if current and GAP_RE.fullmatch(line, current[-1].end(), match.start()):
            current.append(match)
            continue
        if len(current) >= 2:
            runs.append(current)
        current = [match]
    if len(current) >= 2:
        runs.append(current)
    return runs


def is_definition(line: str, match: "re.Match[str]") -> bool:
    """The ID names the thing being defined: a heading, a first table cell, a list label."""
    token = match.group(0)
    stripped = line.lstrip()
    if stripped.startswith("#"):
        head = re.sub(r"^#{1,6}\s*", "", stripped)
        return head.lstrip("*`").startswith(token)
    if stripped.startswith("|"):
        first = stripped[1:].split("|", 1)[0].strip().strip("*`")
        return first == token
    label = LEADING_MARKER_RE.sub("", line, count=1).lstrip("*`")
    if label.startswith(token):
        rest = label[len(token):].lstrip("*` ")
        return rest[:1] in ("：", ":", "|")
    return False


def has_gloss(line: str, match: "re.Match[str]", settings: Settings) -> bool:
    gap = GLOSS_GAP_RE.match(line, match.end())
    position = gap.end() if gap else match.end()
    if position >= len(line) or line[position] not in "（(":
        return False
    close = None
    for index in range(position + 1, len(line)):
        if line[index] in "）)":
            close = index
            break
    if close is None:
        return False
    inner = line[position + 1:close]
    if settings.id_re is not None:
        inner = settings.id_re.sub("", inner)
    return len(GLOSS_WORD_RE.findall(inner)) >= 2


def analyze(text: str, path: str, settings: Settings) -> List[Finding]:
    """Every finding in one file; the caller filters by changed lines and level."""
    findings: List[Finding] = []
    levels = settings.levels

    def add(rule: str, line_no: int, col: int, match_text: str, **fmt: object) -> None:
        if levels[rule] == OFF:
            return
        findings.append(Finding(path, line_no, col + 1, rule, levels[rule],
                                MESSAGES[rule].format(**fmt), match_text))

    seen_ids: Set[str] = set()
    seen_unregistered: Set[str] = set()
    rotation: Dict[str, List[Tuple[int, int]]] = {}

    for line_no, line in prose_lines(text):
        # ID rules keep inline code (hex IDs live inside backticks) but not link targets or comments.
        id_line = mask(line, ID_MASK_RE)
        registered: List[Tuple[int, int]] = []
        if settings.id_re is not None:
            exempt = evidence_spans(id_line, settings)
            all_ids = list(settings.id_re.finditer(id_line))
            registered = [m.span() for m in all_ids]
            ids = [m for m in all_ids if not any(lo <= m.start() < hi for lo, hi in exempt)]
            in_run: Set[int] = set()
            for run in bare_id_runs(ids, id_line):
                add("bare-id-run", line_no, run[0].start(), id_line[run[0].start():run[-1].end()])
                in_run.update(m.start() for m in run)
            for match in ids:
                token = match.group(0).strip("`")
                if token in seen_ids:
                    continue
                seen_ids.add(token)
                if match.start() in in_run or is_definition(id_line, match) or has_gloss(id_line, match, settings):
                    continue
                add("first-mention", line_no, match.start(), token)
        masked = mask(line)
        for match in UNREGISTERED_RE.finditer(masked):
            token = match.group(0)
            if token in seen_unregistered or any(lo <= match.start() < hi for lo, hi in registered):
                continue
            seen_unregistered.add(token)
            add("unregistered-id", line_no, match.start(), token)

        for offset, sentence in sentences(masked):
            if not CJK_RE.search(sentence):
                continue
            for match in SEMICOLON_RE.finditer(sentence):
                add("semicolon", line_no, offset + match.start(), match.group(0))
            length = count_chars(sentence)
            if length > settings.max_chars:
                add("long-sentence", line_no, offset, f"{length} 字", n=length, limit=settings.max_chars)
            for match in NOMINALIZATION_RE.finditer(sentence):
                add("nominalization", line_no, offset + match.start(), match.group(0))
            for word in MARKETING_WORDS:
                index = sentence.find(word)
                if index >= 0 and word not in settings.allow:
                    add("marketing-adjective", line_no, offset + index, word)
            for phrase in EMPTY_PHRASES:
                index = sentence.find(phrase)
                if index >= 0 and phrase not in settings.allow:
                    add("empty-phrase", line_no, offset + index, phrase)
            for rule, pattern in (("passive-voice", PASSIVE_RE), ("compound-aspect", COMPOUND_ASPECT_RE),
                                  ("vague-word", VAGUE_RE), ("halfwidth-punct", HALFWIDTH_RE),
                                  ("dash-join", DASH_JOIN_RE)):
                for match in pattern.finditer(sentence):
                    if match.group(0) in settings.allow:
                        continue
                    add(rule, line_no, offset + match.start(), match.group(0))
            for group in SYNONYM_GROUPS:
                for member in group:
                    for index in member_positions(sentence, member):
                        rotation.setdefault(member, []).append((line_no, offset + index))

    for group in SYNONYM_GROUPS:
        for component in synonym_components(group, rotation, settings.distinct):
            counts = {member: len(rotation[member]) for member in component}
            keeper = max(component, key=lambda m: (counts[m], -group.index(m)))
            found = "、".join(f"{m}×{counts[m]}" for m in sorted(component, key=group.index))
            for member in component:
                if member == keeper:
                    continue
                for line_no, col in rotation[member]:
                    add("synonym-rotation", line_no, col, member, found=found, keeper=keeper)
    findings.sort(key=lambda f: (f.line, f.col, RULES.index(f.rule)))
    return findings


def synonym_components(group: Tuple[str, ...], rotation: Dict[str, List[Tuple[int, int]]],
                       distinct: List[Set[str]]) -> List[List[str]]:
    """Groups of present members that count as one concept.

    A merge that would put two declared-distinct terms into one group is skipped,
    so a third word cannot bridge 用户 and 客户 back together.
    """
    present = [m for m in group if rotation.get(m)]
    components: List[Set[str]] = [{m} for m in present]

    def find(member: str) -> Set[str]:
        return next(c for c in components if member in c)

    for i, a in enumerate(present):
        for b in present[i + 1:]:
            ca, cb = find(a), find(b)
            if ca is cb:
                continue
            merged = ca | cb
            if any(len(d & merged) >= 2 for d in distinct):
                continue
            components.remove(ca)
            components.remove(cb)
            components.append(merged)
    return [sorted(c, key=group.index) for c in components if len(c) >= 2]


# --- file selection ---------------------------------------------------------


def git(root: Path, *args: str) -> subprocess.CompletedProcess:
    # Empty stdin: git never waits for input.
    return subprocess.run(["git", "-C", str(root), "-c", "core.quotepath=false", *args],
                          capture_output=True, input=b"")


def empty_tree(root: Path) -> str:
    """The empty tree id in this repository's object format (SHA-1 or SHA-256)."""
    result = git(root, "hash-object", "-t", "tree", "--stdin")
    value = result.stdout.decode("ascii", "replace").strip()
    return value if result.returncode == 0 and value else EMPTY_TREE


def in_git_work_tree(root: Path) -> bool:
    try:
        result = git(root, "rev-parse", "--is-inside-work-tree")
    except OSError:
        return False
    return result.returncode == 0 and result.stdout.strip() == b"true"


def changed_lines(root: Path) -> Dict[str, Optional[Set[int]]]:
    """Changed line numbers per file against HEAD; None means every line (untracked)."""
    base = "HEAD" if git(root, "rev-parse", "--verify", "-q", "HEAD").returncode == 0 else empty_tree(root)
    diff = git(root, "diff", "--no-color", "--no-ext-diff", "--relative", "-U0", base, "--")
    if diff.returncode != 0:
        raise ConfigError(diff.stderr.decode("utf-8", "replace").strip() or "git diff failed")
    result: Dict[str, Optional[Set[int]]] = {}
    current: Optional[str] = None
    for raw in diff.stdout.decode("utf-8", "replace").splitlines():
        if raw.startswith("+++ "):
            target = raw[4:]
            current = None if target == "/dev/null" else target[2:] if target.startswith("b/") else target
            if current is not None:
                result.setdefault(current, set())
        elif raw.startswith("@@") and current is not None:
            hunk = re.match(r"@@ -\S+ \+(\d+)(?:,(\d+))? @@", raw)
            if hunk:
                start, count = int(hunk.group(1)), int(hunk.group(2) or "1")
                lines = result[current]
                if lines is not None:
                    lines.update(range(start, start + count))
    untracked = git(root, "ls-files", "--others", "--exclude-standard", "-z")
    for name in untracked.stdout.decode("utf-8", "replace").split("\0"):
        if name:
            result[name] = None
    return result


def all_files(root: Path) -> List[str]:
    if in_git_work_tree(root):
        listed = git(root, "ls-files", "--cached", "--others", "--exclude-standard", "-z")
        return sorted({n for n in listed.stdout.decode("utf-8", "replace").split("\0") if n})
    names = []
    for folder, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in (".git", "node_modules")]
        for name in files:
            names.append(Path(folder, name).relative_to(root).as_posix())
    return sorted(names)


def human_facing(path: str, settings: Settings) -> bool:
    return (matches_any(path, settings.include) and not matches_any(path, settings.exclude)
            and not matches_any(path, settings.frozen))


# --- main -------------------------------------------------------------------


def run(root: Path, mode: str, files: Sequence[str], settings: Settings,
        config_path: Optional[Path]) -> Tuple[dict, int]:
    errors: List[dict] = []
    targets: Dict[str, Optional[Set[int]]] = {}
    if mode == "changed":
        if not in_git_work_tree(root):
            return {"errors": [{"file": str(root), "error": "not a Git work tree; use --files"}]}, EXIT_ERROR
        targets = {p: lines for p, lines in changed_lines(root).items() if human_facing(p, settings)}
    elif mode == "files":
        for name in files:
            path = Path(name)
            rel = path.resolve().relative_to(root).as_posix() if path.is_absolute() and \
                path.resolve().is_relative_to(root) else name.replace("\\", "/")
            targets[rel] = None
    else:
        targets = {p: None for p in all_files(root) if human_facing(p, settings)}

    findings: List[Finding] = []
    for rel, lines in sorted(targets.items()):
        try:
            text = (root / rel).read_text(encoding=READ_ENCODING)
        except FileNotFoundError:
            # Deleted in the work tree, or absent in a sparse checkout: nothing to read.
            if mode in ("changed", "report"):
                continue
            errors.append({"file": rel, "error": "FileNotFoundError"})
            continue
        except (OSError, UnicodeDecodeError) as exc:
            errors.append({"file": rel, "error": f"{type(exc).__name__}: {exc}"})
            continue
        for finding in analyze(text, rel, settings):
            if lines is None or finding.line in lines:
                findings.append(finding)

    counts: Dict[str, int] = {}
    for finding in findings:
        counts[finding.rule] = counts.get(finding.rule, 0) + 1
    blocked = sum(1 for f in findings if f.level == BLOCK)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "check_version": CHECK_VERSION,
        "root": str(root),
        "mode": mode,
        "config": str(config_path) if config_path else None,
        "files": sorted(targets),
        "findings": [f.as_dict() for f in findings],
        "counts": counts,
        "blocked": blocked if mode != "report" else 0,
        "errors": errors,
    }
    if errors:
        return payload, EXIT_ERROR
    if blocked and mode != "report":
        return payload, EXIT_BLOCK
    return payload, EXIT_OK


def parse_args(argv: Optional[Sequence[str]]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=".", help="project root (default: current directory)")
    parser.add_argument("--config", help="config path, relative to --root unless absolute")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--changed", action="store_true", help="changed lines against HEAD (default)")
    group.add_argument("--files", nargs="+", metavar="PATH", help="check whole files")
    group.add_argument("--report", action="store_true", help="every human-facing file, never blocks")
    parser.add_argument("--json", action="store_true", help="print the JSON payload only")
    parser.add_argument("--version", action="version", version=f"readable-docs check {CHECK_VERSION}")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    ensure_utf8_stdio()
    args = parse_args(argv)
    root = Path(args.root).expanduser().resolve()
    mode = "files" if args.files else "report" if args.report else "changed"
    try:
        config_path = find_config(root, args.config)
        settings = build_settings(load_config(config_path))
        payload, code = run(root, mode, args.files or [], settings, config_path)
    except ConfigError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_ERROR
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return code
    for finding in payload.get("findings", []):
        print(Finding(**finding).render())
    for error in payload.get("errors", []):
        print(f"ERROR: {error['file']}: {error['error']}", file=sys.stderr)
    if "findings" in payload:
        findings = payload["findings"]
        blocked = sum(1 for f in findings if f["level"] == BLOCK)
        note = "（report 模式不拦截）" if mode == "report" else ""
        print(f"共 {len(findings)} 处发现：拦截 {blocked}，告警 {len(findings) - blocked}{note}；"
              f"检查 {len(payload['files'])} 个文件。情态词永不标记。")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
