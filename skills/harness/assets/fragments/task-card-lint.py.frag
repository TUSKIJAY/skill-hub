def is_blank(value: str) -> bool:
    """Empty, a dash/N-A marker, or an unfilled <placeholder> all count as not recorded."""
    text = value.strip().strip("`").strip()
    return text.lower() in BLANK_VALUES or re.fullmatch(r"<[^<>]*>", text) is not None


def split_row(line: str) -> list[str]:
    cells = re.split(r"(?<!\\)\|", line.strip())
    if cells and not cells[0].strip():
        cells = cells[1:]
    if cells and not cells[-1].strip():
        cells = cells[:-1]
    return [cell.replace("\\|", "|").strip() for cell in cells]


def card_field(text: str, name: str) -> str | None:
    """Value of a `name: value` line in the card header (the part before the first `## ` heading)."""
    header = re.split(r"(?m)^##\s", text, maxsplit=1)[0]
    match = re.search(rf"(?m)^{name}:[ \t]*(.*?)[ \t]*$", header)
    return match.group(1) if match else None


def acceptance_rows(text: str) -> tuple[list[dict[str, str]], str | None]:
    """Rows of the first table under `## 验收项`, keyed by column name, plus a structural problem if any."""
    lines = text.splitlines()
    start = next((i for i, line in enumerate(lines) if re.match(r"##\s+验收项", line)), None)
    if start is None:
        return [], None
    table: list[str] = []
    for line in lines[start + 1:]:
        stripped = line.strip()
        if line.startswith("## "):
            break
        if stripped.startswith("|"):
            table.append(stripped)
        elif table:
            break
    if not table:
        return [], None
    header = split_row(table[0])
    missing = [name for name in ACCEPTANCE_REQUIRED_COLUMNS if name not in header]
    if missing:
        return [], "acceptance table is missing column(s): " + ", ".join(missing)
    rows: list[dict[str, str]] = []
    for line in table[1:]:
        cells = split_row(line)
        if all(not cell or re.fullmatch(r":?-{3,}:?", cell) for cell in cells):
            continue
        rows.append({name: (cells[i] if i < len(cells) else "") for i, name in enumerate(header)})
    return rows, None


def card_problems(status: str | None, rows: list[dict[str, str]]) -> list[str]:
    problems: list[str] = []
    for index, row in enumerate(rows, 1):
        name = row.get("ID") or f"row {index}"
        method = row.get("方式", "").strip().strip("`").lower()
        state = row.get("状态", "").strip()
        if method not in ACCEPTANCE_METHODS:
            problems.append(f"acceptance {name}: 方式 {method!r} is not script or human")
        if state not in ACCEPTANCE_STATES:
            problems.append(f"acceptance {name}: 状态 {state!r} is not one of {ACCEPTANCE_STATES_TEXT}")
        if method == "human" and state in ("已通过", "未通过"):
            if is_blank(row.get("记录人", "")):
                problems.append(f"acceptance {name} (human) is {state} but 记录人 is empty")
            if is_blank(row.get("证据位置", "")):
                problems.append(f"acceptance {name} (human) is {state} but 证据位置 is empty")
        if method == "script" and state in ("已执行", "已通过") and is_blank(row.get("证据位置", "")):
            problems.append(f"acceptance {name} (script) is {state} but 证据位置 is empty")
    if status == "已完成":
        if not rows:
            problems.append("card is 已完成 but has no acceptance items")
        for index, row in enumerate(rows, 1):
            actual = row.get("状态", "").strip()
            if actual != "已通过":
                name = row.get("ID") or f"row {index}"
                problems.append(f"card is 已完成 but acceptance {name} is {actual or '(empty)'}")
    return problems


def lint_task_cards(root: Path) -> list[dict[str, object]]:
    """Consistency lint for the optional task cards.

    It checks field values and cross-field rules only. It cannot prove that a recorded
    result is true or who really wrote it; that depends on the project's own permissions or hooks.
    """
    root = root.resolve()
    try:
        config = json.loads((root / ".harness/config.json").read_text(encoding=READ_ENCODING))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return []
    spec = config.get("task_cards") if isinstance(config, dict) else None
    if spec is None:
        return []
    lint: list[dict[str, object]] = []

    def add(label: str, path: str, passed: bool) -> None:
        lint.append({"label": label, "path": path, "passed": bool(passed)})

    if not isinstance(spec, dict):
        add("task_cards config is an object with `dir` and `max_active`", ".harness/config.json", False)
        return lint
    directory = spec.get("dir")
    base = (root / directory).resolve() if isinstance(directory, str) and directory.strip() else None
    inside = base is not None and (base == root or root in base.parents)
    add("task_cards.dir is a directory inside the project", ".harness/config.json", inside)
    if not inside:
        return lint
    limit = spec.get("max_active", 1)
    valid_limit = isinstance(limit, int) and not isinstance(limit, bool) and limit >= 1
    add("task_cards.max_active is a positive integer", ".harness/config.json", valid_limit)
    if not valid_limit:
        limit = 1
    if not base.is_dir():
        return lint

    active: list[str] = []
    for path in sorted(base.iterdir()):
        if not (path.is_file() and path.name.startswith("TASK-") and path.suffix == ".md"):
            continue
        rel = path.relative_to(root).as_posix()
        try:
            text = path.read_text(encoding=READ_ENCODING).replace("\r\n", "\n").replace("\r", "\n")
        except (OSError, UnicodeDecodeError):
            add(f"{rel}: card is readable UTF-8 text", rel, False)
            continue
        status = card_field(text, "status")
        add(f"{rel}: status {status!r} is one of {CARD_STATES_TEXT}", rel, status in CARD_STATES)
        if status == "实施中":
            active.append(path.name)
        rows, structure_problem = acceptance_rows(text)
        problems = ([structure_problem] if structure_problem else []) + card_problems(status, rows)
        for problem in problems:
            add(f"{rel}: {problem}", rel, False)
        if not problems:
            add(f"{rel}: acceptance items are consistent", rel, True)
    names = ", ".join(active) or "none"
    add(
        f"at most {limit} task card(s) are 实施中 (found {len(active)}: {names})",
        base.relative_to(root).as_posix(),
        len(active) <= limit,
    )
    return lint
