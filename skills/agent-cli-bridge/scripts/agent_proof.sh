#!/usr/bin/env bash
# agent_proof.sh — produce a timestamped proof file that a local agent CLI was
# really invoked: a random nonce is sent and the CLI must echo it back.
#
# Part of the agent-cli-bridge skill. Keep bash 3.2 compatible (macOS).
set -euo pipefail

cli=""
timeout="60s"
out_dir="${AGENT_PROOF_DIR:-$HOME/.agent-proofs}"

usage() {
  cat <<'USAGE'
Usage:
  agent_proof.sh --cli <agy|grok|kimi|codex|claude> [--timeout 60s] [--out-dir PATH]

Runs a nonce-echo prompt through agent_print.sh and records the command,
stdout and exit code in a proof file. Prints the proof file path.

Proof directory: --out-dir, else $AGENT_PROOF_DIR, else ~/.agent-proofs.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --cli)     [[ $# -ge 2 ]] || { echo "--cli requires a value" >&2; exit 2; }; cli="$2"; shift 2 ;;
    --timeout) [[ $# -ge 2 ]] || { echo "--timeout requires a value" >&2; exit 2; }; timeout="$2"; shift 2 ;;
    --out-dir) [[ $# -ge 2 ]] || { echo "--out-dir requires a path" >&2; exit 2; }; out_dir="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *)         echo "unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

if [[ -z "$cli" ]]; then
  echo "--cli is required" >&2
  usage >&2
  exit 2
fi

if ! command -v "$cli" >/dev/null 2>&1; then
  printf 'agent_proof: error: %s is not available on PATH\n' "$cli" >&2
  exit 127
fi

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
mkdir -p "$out_dir"

nonce="$(uuidgen)"
proof="$out_dir/agent-proof-$cli-$(date '+%Y%m%d-%H%M%S').txt"

rc=0
{
  printf 'timestamp: %s\n' "$(date '+%Y-%m-%d %H:%M:%S %Z')"
  printf 'cli: %s\n' "$cli"
  printf 'nonce: %s\n' "$nonce"
  printf 'which %s: ' "$cli"
  command -v "$cli"
  printf '%s version: ' "$cli"
  "$cli" --version </dev/null 2>&1 | head -n 1
  printf '\nstdout:\n'
  "$script_dir/agent_print.sh" --cli "$cli" --timeout "$timeout" \
    --prompt "Return exactly this line and nothing else: BRIDGE_PROOF $nonce"
} > "$proof" 2>&1 || rc=$?

printf 'exit_code: %s\n' "$rc" >> "$proof"

if (( rc != 0 )); then
  printf 'agent_proof: %s call failed (exit %s); details in %s\n' "$cli" "$rc" "$proof" >&2
  exit "$rc"
fi

if ! grep -q "BRIDGE_PROOF $nonce" "$proof"; then
  printf 'agent_proof: warning: nonce not echoed verbatim; inspect %s\n' "$proof" >&2
fi

printf '%s\n' "$proof"
