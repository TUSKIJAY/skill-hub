#!/usr/bin/env bash
# Backward-compatible wrapper for the original single-CLI helper.
# New code should call agent_print.sh directly.
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$script_dir/agent_print.sh" --cli agy "$@"
