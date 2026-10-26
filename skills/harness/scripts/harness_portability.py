#!/usr/bin/env python3
"""Portable layer shared by the skill's own scripts.

UTF-8 console output, BOM-tolerant reads of user-maintained files, and the
interpreter command written into generated files. Standard library only.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

# Reads accept an optional UTF-8 BOM; generated files are still written as UTF-8 without BOM.
READ_ENCODING = "utf-8-sig"
OUTPUT_ENCODING = "utf-8"
WINDOWS_PYTHON_COMMAND = "python"
POSIX_PYTHON_COMMAND = "python3"
INFERRED_PYTHON_PREFIX = "python "


def ensure_utf8_stdio() -> None:
    """Force UTF-8 stdout/stderr so Chinese text survives a GBK console or pipe."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding=OUTPUT_ENCODING, errors="replace")
        except (AttributeError, OSError, ValueError) as exc:
            print(f"WARNING: cannot switch output to UTF-8: {exc}", file=sys.stderr)


def read_text_or_empty(path: Path) -> str:
    """Text of a UTF-8 file (BOM allowed); "" when absent. Other read failures warn on stderr."""
    try:
        return path.read_text(encoding=READ_ENCODING)
    except FileNotFoundError:
        return ""
    except (OSError, UnicodeDecodeError) as exc:
        print(f"WARNING: cannot read {path}: {exc}", file=sys.stderr)
        return ""


def read_json_file(path: Path) -> Any:
    """Parse a UTF-8 JSON file that may start with a BOM.

    Raises OSError, UnicodeDecodeError or json.JSONDecodeError; the caller reports them.
    """
    return json.loads(path.read_text(encoding=READ_ENCODING))


def default_python_command() -> str:
    """`python` on Windows, `python3` elsewhere; `--python-command` overrides it."""
    return WINDOWS_PYTHON_COMMAND if os.name == "nt" else POSIX_PYTHON_COMMAND


def checked_python_command(value: str | None) -> str:
    """The interpreter command to record; ValueError unless it is one nonempty line."""
    command = default_python_command() if value is None else value.strip()
    if not command or "\r" in command or "\n" in command:
        raise ValueError("--python-command must be one nonempty shell command line")
    return command


def with_python_command(command: str, python_command: str) -> str:
    """Rewrite an inferred `python ...` command to start with the recorded interpreter."""
    if command.startswith(INFERRED_PYTHON_PREFIX):
        return f"{python_command} {command[len(INFERRED_PYTHON_PREFIX):]}"
    return command
