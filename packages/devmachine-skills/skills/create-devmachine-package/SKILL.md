---
name: create-devmachine-package
description: Use when desired persistent machine or workspace state has no suitable Devmachine package, or when converting repeatable custom setup into a package.
---

# Create a Devmachine Package

A package is an ordinary Ansible role plus `package.yml`. Use the CLI to create
and validate it instead of inventing the layout.

## Decide first

1. If the software is intentionally volatile, leave it unmanaged.
2. If a published package already fits, select it.
3. Otherwise create a local package under the effective configuration's
   `packages/` directory.

Choose `machine` scope for shared host state and `workspace` for state owned by
one account. Workspace names and package names do not imply routing; explicit
package membership does.

## Build from the live contract

```bash
devmachine config path
devmachine packages schema --json
devmachine packages new <name> --scope machine|workspace --into <config-dir>/packages
devmachine packages validate <config-dir>/packages/<name>
```

Read the current
[`reference/package-format.md`](https://github.com/adevmachine/cli/blob/main/docs/reference/package-format.md)
and the generated skeleton before editing. Keep tasks idempotent and portable:
use Ansible modules, declare `needs`, avoid direct `apt`, and put defaults in
the role. A package may also contribute complete Agent Skill directories with
`skills.path`; the CLI owns canonical installation and harness adapters.

## Prove it on a fake target

Add the package with `devmachine packages add` or `devmachine workspaces edit`.
Use a disposable local machine, run `devmachine sync --check --tags <name>`,
apply once, verify the intended state, then apply the same sync again. The
second run must report `changed=0`. Preserve unrelated files and unmanaged
software.

Do not develop or test a package against a real machine. Before any real
`doctor`, `sync --check`, `sync`, `run`, SSH, DNS, or publication command,
show the exact command and obtain explicit approval for that target.

## Completion checklist

- `packages validate` passes.
- Repository syntax and data-leak checks pass when contributing publicly.
- Fake-target behavior and second-run idempotence pass.
- Package membership is limited to the intended workspaces.
- No real machine was contacted without exact-command approval.
