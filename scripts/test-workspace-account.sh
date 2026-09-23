#!/usr/bin/env bash
set -euo pipefail

root=$(cd "$(dirname "$0")/.." && pwd)
helper="$root/packages/workspace/files/devmachine-create-workspace"
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

cat > "$tmp/getent" <<'SH'
#!/usr/bin/env bash
test "${DEVMACHINE_TEST_ACCOUNT_EXISTS:-0}" = 1
SH

cat > "$tmp/useradd" <<'SH'
#!/usr/bin/env bash
printf '%s\n' "$@" > "$DEVMACHINE_USERADD_LOG"
SH

chmod +x "$tmp/getent" "$tmp/useradd"

DEVMACHINE_GETENT="$tmp/getent" \
DEVMACHINE_USERADD="$tmp/useradd" \
DEVMACHINE_USERADD_LOG="$tmp/useradd.log" \
  "$helper" alice /home/alice

cat > "$tmp/want" <<'EOF'
-K
SUB_UID_COUNT=0
-K
SUB_GID_COUNT=0
--create-home
--home-dir
/home/alice
alice
EOF

diff -u "$tmp/want" "$tmp/useradd.log"

: > "$tmp/useradd.log"
DEVMACHINE_TEST_ACCOUNT_EXISTS=1 \
DEVMACHINE_GETENT="$tmp/getent" \
DEVMACHINE_USERADD="$tmp/useradd" \
DEVMACHINE_USERADD_LOG="$tmp/useradd.log" \
  "$helper" alice /home/alice

test ! -s "$tmp/useradd.log"
echo "workspace account helper is fine"
