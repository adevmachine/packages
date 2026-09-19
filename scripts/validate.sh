#!/usr/bin/env bash
# Every recipe here has to pass the CLI's own validator. The validator is the
# format; this script is how the repository stays inside it.
set -euo pipefail
cd "$(dirname "$0")/.."

if ! command -v devmachine >/dev/null 2>&1; then
  echo "devmachine is not on PATH. Install it with: brew install adevmachine/tap/devmachine" >&2
  exit 1
fi

status=0
for dir in packages/*/; do
  devmachine packages validate "$dir" || status=1
done
exit $status
