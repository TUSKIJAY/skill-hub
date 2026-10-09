#!/usr/bin/env bash
# agent_print.sh — run a bounded single-prompt call against a local agent CLI
# (agy, grok, kimi, codex, claude) and print the response on stdout.
#
# Part of the agent-cli-bridge skill. Keep bash 3.2 compatible (macOS).
set -euo pipefail

cli=""
prompt=""
model=""
timeout="120s"
timeout_set=0
format="text"
effort=""
schema=""
continue_prev=0
dirs=()
images=()
extra=()

usage() {
  cat <<'USAGE'
Usage:
  agent_print.sh --cli <agy|grok|kimi|codex|claude> --prompt "..." [options] [-- extra CLI args]

Options:
  --cli NAME        Target CLI: agy | grok | kimi | codex | claude (required)
  --prompt TEXT     The prompt to run (required)
  --dir PATH        Grant/focus a workspace directory (repeatable).
                    agy/kimi/claude: --add-dir; grok/codex: first dir becomes --cwd/--cd
  --model NAME      Model to use. agy: run `agy models` for exact labels
  --timeout 120s    agy: maps to --print-timeout. Other CLIs: accepted but NOT
                    enforced (no timeout/gtimeout on this system)
  --format text|json
                    Machine-readable output. agy/grok/claude: single JSON object.
                    kimi: stream-json JSONL. codex: JSONL event stream.
  --schema 'JSON'   Enforce structured output (JSON Schema string). Implies
                    --format json. Not supported by kimi.
  --effort LEVEL    Reasoning effort. Supported: agy, grok, claude.
                    Ignored (with warning) for kimi and codex.
  --image FILE      Attach an image (repeatable). Only supported by codex (-i).
                    For other CLIs: reference the absolute path in --prompt and
                    grant access with --dir instead.
  --continue        Follow up on the most recent session of the current
                    directory. codex: `codex exec resume --last`.
  --                Everything after `--` is passed to the CLI verbatim.

Exit codes: the CLI's own exit code on failure (stderr shows a tail of its
output); 2 for usage errors; 127 when the CLI binary is missing.
USAGE
}

warn() { printf 'agent_print: warning: %s\n' "$*" >&2; }
die()  { printf 'agent_print: error: %s\n' "$*" >&2; exit 2; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --cli)      [[ $# -ge 2 ]] || die "--cli requires a value"; cli="$2"; shift 2 ;;
    --prompt)   [[ $# -ge 2 ]] || die "--prompt requires text"; prompt="$2"; shift 2 ;;
    --dir)      [[ $# -ge 2 ]] || die "--dir requires a path"; dirs+=("$2"); shift 2 ;;
    --model)    [[ $# -ge 2 ]] || die "--model requires a value"; model="$2"; shift 2 ;;
    --timeout)  [[ $# -ge 2 ]] || die "--timeout requires a value"; timeout="$2"; timeout_set=1; shift 2 ;;
    --format)   [[ $# -ge 2 ]] || die "--format requires a value"; format="$2"; shift 2 ;;
    --schema)   [[ $# -ge 2 ]] || die "--schema requires a value"; schema="$2"; shift 2 ;;
    --effort)   [[ $# -ge 2 ]] || die "--effort requires a value"; effort="$2"; shift 2 ;;
    --image)    [[ $# -ge 2 ]] || die "--image requires a path"; images+=("$2"); shift 2 ;;
    --continue) continue_prev=1; shift ;;
    -h|--help)  usage; exit 0 ;;
    --)         shift; while [[ $# -gt 0 ]]; do extra+=("$1"); shift; done ;;
    *)          die "unknown argument: $1 (see --help)" ;;
  esac
done

[[ -n "$cli" ]]    || die "--cli is required"
[[ -n "$prompt" ]] || die "--prompt is required"
case "$format" in text|json) ;; *) die "--format must be text or json" ;; esac

case "$cli" in
  agy|grok|kimi|codex|claude) ;;
  *) die "unsupported --cli '$cli' (expected agy, grok, kimi, codex or claude)" ;;
esac

if ! command -v "$cli" >/dev/null 2>&1; then
  printf 'agent_print: error: %s is not available on PATH\n' "$cli" >&2
  exit 127
fi

if ((${#images[@]})) && [[ "$cli" != codex ]]; then
  die "--image is only supported for codex; for $cli, reference the absolute path in --prompt and use --dir"
fi
if [[ -n "$schema" && "$cli" == kimi ]]; then
  die "--schema is not supported by kimi"
fi
if [[ -n "$effort" && ( "$cli" == kimi || "$cli" == codex ) ]]; then
  warn "--effort is not supported by $cli; ignoring"
  effort=""
fi
if (( timeout_set )) && [[ "$cli" != agy ]]; then
  warn "--timeout is only enforced for agy (--print-timeout); $cli has no wrapper timeout here"
fi
if [[ "$format" == json && "$cli" == kimi ]]; then
  warn "kimi has no plain JSON mode; using stream-json (JSONL events)"
fi
if ((${#dirs[@]} > 1)) && [[ "$cli" == grok ]]; then
  warn "grok supports a single --cwd; using ${dirs[0]} and ignoring the rest"
fi

# --- build the per-CLI command ---------------------------------------------

cmd=()
last_msg=""
schema_file=""

want_json=0
if [[ "$format" == json || -n "$schema" ]]; then
  want_json=1
fi

case "$cli" in
  agy)
    cmd=(agy --print-timeout "$timeout")
    if ((${#dirs[@]})); then
      for d in ${dirs[@]+"${dirs[@]}"}; do cmd+=(--add-dir "$d"); done
    fi
    [[ -n "$model" ]]  && cmd+=(--model "$model")
    (( want_json ))    && cmd+=(--output-format json)
    [[ -n "$schema" ]] && cmd+=(--json-schema "$schema")
    [[ -n "$effort" ]] && cmd+=(--effort "$effort")
    (( continue_prev )) && cmd+=(--continue)
    if ((${#extra[@]})); then cmd+=(${extra[@]+"${extra[@]}"}); fi
    cmd+=(--print "$prompt")
    ;;

  grok)
    cmd=(grok)
    ((${#dirs[@]}))    && cmd+=(--cwd "${dirs[0]}")
    [[ -n "$model" ]]  && cmd+=(-m "$model")
    (( want_json ))    && cmd+=(--output-format json)
    [[ -n "$schema" ]] && cmd+=(--json-schema "$schema")
    [[ -n "$effort" ]] && cmd+=(--effort "$effort")
    (( continue_prev )) && cmd+=(-c)
    if ((${#extra[@]})); then cmd+=(${extra[@]+"${extra[@]}"}); fi
    cmd+=(-p "$prompt")
    ;;

  kimi)
    cmd=(kimi)
    if ((${#dirs[@]})); then
      for d in ${dirs[@]+"${dirs[@]}"}; do cmd+=(--add-dir "$d"); done
    fi
    [[ -n "$model" ]] && cmd+=(-m "$model")
    if (( want_json )); then cmd+=(--output-format stream-json); fi
    (( continue_prev )) && cmd+=(-c)
    if ((${#extra[@]})); then cmd+=(${extra[@]+"${extra[@]}"}); fi
    cmd+=(-p "$prompt")
    ;;

  codex)
    if (( continue_prev )); then
      cmd=(codex exec resume --last)
    else
      cmd=(codex exec --skip-git-repo-check -s read-only)
    fi
    if ((${#dirs[@]})); then
      cmd+=(--cd "${dirs[0]}")
      if ((${#dirs[@]} > 1)); then
        for d in "${dirs[@]:1}"; do cmd+=(--add-dir "$d"); done
      fi
    fi
    [[ -n "$model" ]] && cmd+=(-m "$model")
    if ((${#images[@]})); then
      for img in ${images[@]+"${images[@]}"}; do cmd+=(-i "$img"); done
    fi
    if [[ -n "$schema" ]]; then
      schema_file="$(mktemp "${TMPDIR:-/tmp}/agent_print_schema.XXXXXX")"
      printf '%s' "$schema" > "$schema_file"
      cmd+=(--output-schema "$schema_file")
    fi
    if (( want_json )); then
      cmd+=(--json)
    else
      # capture just the final agent message for a clean relay
      last_msg="$(mktemp "${TMPDIR:-/tmp}/agent_print_last.XXXXXX")"
      cmd+=(-o "$last_msg")
    fi
    if ((${#extra[@]})); then cmd+=(${extra[@]+"${extra[@]}"}); fi
    cmd+=("$prompt")
    ;;

  claude)
    cmd=(claude --print "$prompt")
    [[ -n "$model" ]]  && cmd+=(--model "$model")
    (( want_json ))    && cmd+=(--output-format json)
    [[ -n "$schema" ]] && cmd+=(--json-schema "$schema")
    [[ -n "$effort" ]] && cmd+=(--effort "$effort")
    (( continue_prev )) && cmd+=(-c)
    if ((${#extra[@]})); then cmd+=(${extra[@]+"${extra[@]}"}); fi
    # variadic option: keep it last so it cannot swallow other arguments
    if ((${#dirs[@]})); then cmd+=(--add-dir ${dirs[@]+"${dirs[@]}"}); fi
    ;;
esac

# --- run, capture, relay ----------------------------------------------------

out="$(mktemp "${TMPDIR:-/tmp}/agent_print_out.XXXXXX")"
err="$(mktemp "${TMPDIR:-/tmp}/agent_print_err.XXXXXX")"
cleanup() {
  rm -f "$out" "$err"
  if [[ -n "$last_msg" ]]; then rm -f "$last_msg"; fi
  if [[ -n "$schema_file" ]]; then rm -f "$schema_file"; fi
  return 0
}
trap cleanup EXIT

rc=0
# Prompts always arrive as positional args, never on stdin. Leaving stdin open makes
# codex exec block forever in resolve_root_prompt waiting for input it will never get.
"${cmd[@]}" </dev/null >"$out" 2>"$err" || rc=$?

if (( rc != 0 )); then
  printf 'agent_print: %s exited with code %s\n' "$cli" "$rc" >&2
  if [[ -s "$err" ]]; then
    printf '%s\n' '--- stderr (tail) ---' >&2
    tail -n 20 "$err" >&2
  fi
  if [[ -s "$out" ]]; then
    printf '%s\n' '--- stdout (tail) ---' >&2
    tail -n 20 "$out" >&2
  fi
  exit "$rc"
fi

if [[ -n "$last_msg" ]]; then
  if [[ -s "$last_msg" ]]; then
    cat "$last_msg"
  else
    # fall back to the CLI's own stdout when no final message was captured
    cat "$out"
  fi
else
  cat "$out"
fi
