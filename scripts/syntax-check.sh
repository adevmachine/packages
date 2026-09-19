#!/usr/bin/env bash
# Runs every recipe through `ansible-playbook --syntax-check`, as the role it
# is. It catches what the validator cannot: a recipe that does not parse as a
# play at all.
set -euo pipefail
cd "$(dirname "$0")/.."

playbook="$(mktemp -t syntax-check-XXXXXX).yml"
trap 'rm -f "$playbook"' EXIT

{
  echo '---'
  echo '- name: Syntax check every package'
  echo '  hosts: localhost'
  echo '  gather_facts: false'
  echo '  roles:'
  for dir in packages/*/; do
    echo "    - $(basename "$dir")"
  done
} > "$playbook"

ANSIBLE_ROLES_PATH=packages ansible-playbook --syntax-check "$playbook"
