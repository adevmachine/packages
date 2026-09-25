---
name: use-devmachine
description: Use when configuring, inspecting, troubleshooting, or operating a machine or workspace managed by the Devmachine CLI.
---

# Use Devmachine

Use the CLI as the source of truth. Do not replace a missing CLI operation with
ad-hoc SSH or an old Ansible repository without first identifying the missing
capability.

## Start here

Always begin with these local, read-only commands:

```bash
devmachine config path
devmachine help --json
```

Then run `devmachine <command> --help` for the selected operation and read the
relevant page in the [CLI documentation](https://github.com/adevmachine/cli/tree/main/docs):

| Need | Documentation |
| --- | --- |
| First setup | `getting-started.md` |
| Machines and workspaces | `concepts/machines-and-workspaces.md` |
| Configuration and settings | `concepts/configuration.md` |
| Packages | `concepts/packages.md` and `reference/package-format.md` |
| DNS and public sites | `concepts/dns.md` and `concepts/publishing.md` |
| Credentials | `concepts/credentials.md` |
| Exact command behavior | `reference/commands.md` |
| Failures | `troubleshooting.md` |

Prefer checked-in copies of those pages when working inside the CLI repository.

## Safety boundary

- Configuration edits such as `packages add`, `workspaces edit`, and
  `workspaces defaults` are local until `sync`.
- Commands such as `doctor`, `run`, `stats`, `sync --check`, DNS, and `expose`
  may contact a configured machine.
- A machine appearing in `config.yml` is not permission to contact it. Obtain
  explicit approval for the exact command before touching a real machine.
- Use a disposable local machine for development and acceptance. Reuse one
  fake machine for related checks.
- Public writes require the command's explicit consent boundary; for example,
  unattended `expose add` uses `--publish`, not `--yes`.

## Persistent versus volatile state

Leave deliberately volatile software unmanaged. For state that must converge,
reuse a published package or create a local package; do not silently install it
with `run`. Use `run` to invoke a package entrypoint or for an explicitly
temporary operation.

## Before reporting completion

Run the command's dry-run mode when available, inspect the target named by the
effective configuration, apply only with the required approval, and verify the
result through a Devmachine command.
