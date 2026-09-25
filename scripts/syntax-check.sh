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

for manifest in packages/*/package.yml; do
  skill_path="$({
    awk '
      /^skills:[[:space:]]*$/ { in_skills = 1; next }
      in_skills && /^  path:[[:space:]]+/ { print $2; exit }
      in_skills && /^[^[:space:]]/ { exit }
    ' "$manifest"
  } || true)"
  [ -n "$skill_path" ] || continue
  skill_path="${skill_path#\"}"
  skill_path="${skill_path%\"}"
  root="$(dirname "$manifest")/$skill_path"
  if [ ! -d "$root" ]; then
    echo "$manifest: skills.path $skill_path is not a directory" >&2
    exit 1
  fi
  found=false
  for skill in "$root"/*/; do
    [ -d "$skill" ] || continue
    found=true
    if [ ! -f "${skill}SKILL.md" ]; then
      echo "${skill}SKILL.md is missing" >&2
      exit 1
    fi
  done
  if [ "$found" = false ]; then
    echo "$manifest: skills.path $skill_path contains no skills" >&2
    exit 1
  fi
done
