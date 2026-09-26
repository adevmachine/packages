# packages

The recipes the [devmachine CLI](https://github.com/adevmachine/cli) applies to a
machine. Nothing here is built into the binary: the CLI fetches a release of this
repository, checks it against the checksum published beside it, and runs what it
finds.

## What a package is

An Ansible role, with one extra file beside it:

```
packages/<name>/
  package.yml        what this is, what it needs, what it offers
  tasks/main.yml     required
  skills/*/SKILL.md  optional Agent Skills contributed by this package
  defaults/, vars/, files/, templates/, handlers/
```

Nothing is translated. What is written here is what runs on the machine, so a
failure points at a line somebody wrote rather than at generated YAML they have
never seen.

## What is in this release

| Package | Scope | What it does |
| --- | --- | --- |
| `base` | machine | The base tools, a shared tmux config, and the `resume` session picker. |
| `git` | machine | Installs git. |
| `docker` | machine | Docker Engine and the Compose plugin, from Docker's own repository. |
| `caddy` | machine | A reverse proxy that gets its own certificates. |
| `firewall` | machine | ufw, with SSH open and HTTP optional. |
| `fail2ban` | machine | fail2ban, with a jail for sshd. |
| `ssh_hardening` | machine | Password authentication off, for good. |
| `mac-brew` | machine | Installs Homebrew taps, formulae and casks from lists. |
| `mac-mise` | machine | Installs mise's global tools from a list. |
| `devmachine-skills` | workspace | Teaches supported agents to operate Devmachine and create packages. |

## A pin is a tag, never a branch

The CLI is pointed at a release (`packages: v0.0.1`), not at `main`. A branch
would mean the set changes under you because somebody pushed an hour ago.
Upgrading is meant to be a deliberate act with a diff to read.

Releases are semver from `v0.0.1`. A tag is never moved: a fix ships as a new
tag, so a checksum recorded in somebody's lock file stays true.

The release is a tarball built with `tar --sort --owner=0 --group=0
--numeric-owner --mtime`, so the same tree always gives the same checksum. The
checksum goes in the CLI's lock file: content that changes after the fact is
refused and named.

## Rules a recipe keeps

- **No `apt`, `apt_key` or `apt_repository`.** `package:` is what installs
  things. Whatever differs between families — package names, a repository path,
  a service name — lives in `vars/<family>.yml`, loaded with
  `include_vars: "{{ ansible_os_family }}.yml"`.
- **`name:` is the directory name.** A package is found by its directory.
- **`needs:` is written down.** Ordering is declared, never implied by the order
  of a list.
- **Nothing personal.** This repository is public and holds no real hostname,
  domain, address, account or token. Examples use `example.com` and
  `203.0.113.x`.
- **English, everywhere.**

## Extension points

A package can declare a place other packages may write into:

```yaml
provides:
  sites.d: /etc/caddy/sites.d
```

and another package contributes to it:

```yaml
extends:
  caddy.sites.d: files/my-site.caddy
```

It is a contribution, not a patch, and it cannot reach anywhere else. `caddy`
therefore serves nothing by itself — every site is a file some other package
drops into that directory.

## Adding a recipe

```bash
devmachine packages new <name>
# write it
devmachine packages validate packages/<name>
./scripts/syntax-check.sh
```

`scripts/validate.sh` runs the validator over every recipe, and CI runs both.

## Releasing

```bash
./scripts/validate.sh
git tag -s v2 -m "..."
git push origin v2
```

The `release` workflow builds the tarball and the checksums and attaches both to
the release.

## Licence

MIT. See [LICENSE](LICENSE).
