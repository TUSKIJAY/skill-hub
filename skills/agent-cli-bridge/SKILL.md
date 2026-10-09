---
name: agent-cli-bridge
description: Delegate bounded tasks to local agent CLIs (agy/Antigravity "anti", grok, kimi, codex, claude) as external subagents and relay results back. Use when the user asks to call AGY, anti, grok, kimi, codex, or claude as another model, wants multimodal analysis (image/file/folder inspection) through another CLI, wants a second opinion or cross-model comparison (e.g. "ask grok too", "compare with codex"), lists models/plugins of another CLI, or wants proof that a CLI was really invoked. Also trigger on shorthand/typos such as AGVCI, agycli, antigravity, and on Chinese phrases like anti看图, anti分析文件, 让grok看一下, 用kimi问一下, 叫codex分析, 问claude.
---

# Agent CLI Bridge

Use the local agent CLIs as external model bridges — for multimodal file inspection, second-opinion analysis, and cross-model comparison. Supported CLIs: `agy` (Antigravity, the user often calls it `anti`), `grok`, `kimi`, `codex`, `claude`. Treat each CLI's output as another model's answer: quote or summarize it clearly, labeled with the CLI's name, then add your own interpretation separately only when useful.

## Common Names

Recognize requests naming any of these as bridge tasks: `anti`, `AGY`, `agy cli`, `Antigravity CLI`, `AGVCI`, `grok`, `kimi`, `codex`, `claude`, plus Chinese phrases such as `anti看图`, `anti分析文件`, `anti分析文件夹`, `用anti问一下`, `让grok看一下`, `用kimi问一下`, `叫codex分析`, `问一下claude`.

## Preconditions

Verify the target binary before relying on it:

```bash
command -v agy grok kimi codex claude   # check the one you need
agy --version                           # or: grok/kimi/codex/claude --version
```

If a binary is missing, report that CLI as unavailable and do not invent results.

## Helper Script (preferred)

`scripts/agent_print.sh` (in the directory containing this SKILL.md) runs a bounded single-prompt call against any supported CLI and prints the response on stdout:

```bash
<skill-dir>/scripts/agent_print.sh --cli agy --prompt "Reply with exactly: AGY_OK"

<skill-dir>/scripts/agent_print.sh \
  --cli claude \
  --dir /absolute/path/to/folder \
  --prompt "Inspect /absolute/path/to/image.png and describe it."
```

Key options: `--dir` (repeatable, smallest necessary folder), `--model`, `--format text|json`, `--schema '<json-schema>'`, `--effort low|medium|high`, `--image FILE` (codex only), `--continue` (follow up the most recent session), `--timeout` (enforced for agy only), and `--` to pass raw args through to the CLI. Run with `--help` for details. Failures report the CLI's exit code plus a tail of its stderr/stdout.

`scripts/agy_print.sh` is a backward-compatible wrapper equivalent to `agent_print.sh --cli agy`.

## Per-CLI Notes (verified against installed versions)

| CLI | Print mode | Directory scope | Machine-readable | Notes |
|---|---|---|---|---|
| agy 1.1.22 | `agy --print "..." --print-timeout 120s` | `--add-dir` (repeatable) | `--output-format json` → single object, answer at `.response` | `--json-schema`, `--effort`, `-c` continue, `--conversation ID`, `--sandbox`, `--mode plan`; list models with `agy models`, plugins with `agy plugin list` |
| grok 1.0.13 | `grok -p "..."` (`-p` is now an alias of `--single`) | `--cwd DIR` (single dir only) | `--output-format json` → single object, answer at `.text` (also has `.thought`) | `--json-schema`, `--effort`, `-c`/`--resume`, `--permission-mode plan`, `--sandbox PROFILE` |
| kimi 0.39.1 | `kimi -p "..."` | `--add-dir` (repeatable) | `--output-format stream-json` → JSONL, answer lines are `{"role":"assistant","content":...}`; a `session.resume_hint` meta line follows | no plain-JSON mode, no `--json-schema`, no effort flag; `-c` continue, `--plan`; 0.39 also adds `--agent`/`--agent-file`, `--skills-dir`, `--session`, `--auto`, `--yolo` |
| codex 0.151.0 | `codex exec "..."` (positional prompt) | `--cd DIR` + `--add-dir` | `--json` → JSONL events; final answer in `{"type":"item.completed","item":{"type":"agent_message","text":...}}` | script adds `--skip-git-repo-check -s read-only` and relays the final message via `-o`; attach images with `-i FILE`; structured output via `--output-schema FILE`; follow up with `codex exec resume --last "..."` |
| claude 2.1.251 | `claude --print "..."` | `--add-dir d1 d2` (variadic) | `--output-format json` → single object, answer at `.result` | `--json-schema`, `--effort`, `-c`/`--resume`, `--permission-mode plan` |

Extract the answer text from JSON output:

```bash
# agy / grok / claude (single JSON object)
... --format json | jq -r .response   # agy
... --format json | jq -r .text       # grok
... --format json | jq -r .result     # claude
# codex / kimi (JSONL)
... --format json | jq -rj 'select(.type=="item.completed" and .item.type=="agent_message") | .item.text + "\n"'
... --format json | jq -rj 'select(.role=="assistant") | .content + "\n"'
```

The helper closes stdin (`</dev/null`) for every CLI call. Prompts always travel as positional args or
`--prompt`, so no CLI needs stdin, and leaving it open makes `codex exec` block forever in
`resolve_root_prompt` waiting for input that never arrives. Keep that redirect if you edit the script.

## Portability

The helpers require Bash 3.2+ and POSIX utilities (`mktemp`, `cat`, `tail`, `head`, `grep`, `date`); the proof helper also requires `uuidgen`. Install and authenticate the requested agent CLI separately. On Windows use a compatible Bash environment (for example WSL); native PowerShell execution is not supported. Version numbers above record historical checks, not a guarantee about the currently installed CLI; inspect its `--help` when compatibility is uncertain. `--timeout` is enforced only for agy; use the calling tool to bound other CLIs when needed.

## Workflow

1. Clarify the task boundary: which CLI, file/folder path, question, desired model if any, and whether the CLI should only inspect or may modify files.
2. Use absolute paths. Add the smallest necessary folder with `--dir`.
3. Prefer `--format json` when the result feeds further processing; quote `.response`/`.text`/`.result` (or the JSONL selectors above) rather than parsing free text.
4. Model selection: only when the user asks or the task benefits. Do not trust remembered model names — check the CLI's own listing/config first (`agy models`; others use their config aliases).
5. For images: codex takes `--image FILE` directly; other CLIs take the absolute path in the prompt plus `--dir` on the folder. If the source is SVG or another format a CLI may not inspect reliably, render or convert it to PNG first when practical.
6. Cross-model comparison: run the same prompt through several `--cli` targets, label each output with its CLI name, then synthesize the comparison yourself.
7. If a CLI errors, relay the exit code and the important stderr detail, and suggest the next minimal retry. Server-side errors (e.g. HTTP 529) warrant a plain retry after a short wait.
8. Follow-up questions: use `--continue` (or the CLI's resume command) instead of re-sending full context.

## Safety And Scope

- The helper script runs codex with `-s read-only`; analysis tasks for all CLIs should be prompted to inspect and answer only. Do not let a bridge call modify user files unless the user asked for modifications.
- Prefer each CLI's safer autonomy modes (`--mode plan`, `--permission-mode plan`, `--sandbox`) over bypass flags (`--dangerously-skip-permissions`, `--dangerously-bypass-approvals-and-sandbox`, `--always-approve`). Use bypass flags only when the user explicitly asks for an autonomous run and the task is safe.
- Do not give a CLI broad filesystem access when a smaller `--dir` works.
- Do not pass secrets, API keys, private tokens, or unrelated personal files to any CLI.
- Treat every bridge answer as model output, not ground truth. For high-stakes or current facts, verify independently.

## Proof Pattern

When the user asks whether a CLI was really invoked, run `scripts/agent_proof.sh`:

```bash
<skill-dir>/scripts/agent_proof.sh --cli grok
```

It sends a random nonce that the CLI must echo back, and records timestamp, binary path, version, stdout and exit code in a proof file (printed on stdout). Proof directory: `--out-dir`, else `$AGENT_PROOF_DIR`, else `~/.agent-proofs`.
