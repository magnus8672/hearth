# Git repository

The shared repository is [magnus8672/hearth](https://github.com/magnus8672/hearth), with SSH remote `git@github.com:magnus8672/hearth.git` and primary branch `main`.

## Current verification

The 18 September review found a clean local tree at `d9ce334` and matching cached `origin/main`. A read-only `git ls-remote origin HEAD` failed with `Permission denied (publickey)`. Remote branch freshness and current CI results were not verified. Existing SSH configuration was not changed; a later authenticated remote check is needed before claiming synchronization. See [the dated farm/source snapshot](../implementation/CURRENT_STATE.md).

## What belongs in Git

Keep application and runtime source, scripts, migrations, generated API contracts, dependency lockfiles, branding assets, documentation and deliberately selected validation evidence. The original design snapshot under `docs/plan/` remains immutable. Small screenshots and synthetic media used as evidence are intentional repository inputs.

[The ignore rules](../../.gitignore) exclude farm state under `.hearth/`, dependency environments, build/package outputs, tool caches, transient browser reports and authentication state, model weights, VM disks, local databases, credentials and certificate exports. Keep private runtime configuration in `.hearth/` even when its filename would otherwise be eligible for Git. A JSON filename alone does not make its contents safe to publish. Only sanitized environment examples belong in source control.

Release ZIPs and native binaries belong in release attachments, not Git history. A clean source checkout builds its browser bundles with `pnpm build` before running `python scripts/package_head.py`. Models remain separately provisioned on their provider machines.

## Before committing

```bash
git status --short
git ls-files -ci --exclude-standard
git diff --check
git diff --cached --stat
git diff --cached --check
```

`git ls-files -ci --exclude-standard` should print nothing: ignore rules do not remove files already tracked by Git. Inspect the staged content before publishing; never use `git add -f` for runtime state, credentials or model weights. Use `git check-ignore -v --no-index -- path/to/file` to explain an exclusion. If a deliberately maintained fixture needs an otherwise ignored suffix, add a narrow, documented exception.

[Repository attributes](../../.gitattributes) normalize source text to LF for Linux/container compatibility and preserve binary assets. Do not normalize or regenerate the immutable design snapshot as a cleanup operation.

## Initial publication audit

The [15 September audit](../../evidence/repository/2026-09-15/git-hygiene.json) checks candidate file sizes, all locally referenced history blobs, common literal credential patterns and selected JSON credential fields. It also checks representative ignored artifacts and retained source paths. Git object integrity passes. No tracked files match the ignore rules. This bounded scan does not prove the absence of every possible secret or private detail in screenshots.

The approximately 44 MB source/evidence payload is separate from the more than 60 GB development folder. Local VM data and model files are retained on disk and excluded from Git. No data cleanup or history rewriting was performed.
