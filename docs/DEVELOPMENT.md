# Developing hearth

Updated 18 September 2026. Start with [repository guidance](AGENT_GUIDANCE.md), [current farm state](implementation/CURRENT_STATE.md), [coverage](implementation/DESIGN_COVERAGE.md) and [build status](implementation/BUILD_STATUS.md).

## Development and runtime targets

Use your checkout for source edits, Git and static checks. Obtain runtime hosts, SSH accounts and deployment paths from private operator configuration. They are intentionally absent from this repository. The [capability overview](implementation/CURRENT_STATE.md) describes roles, not a live inventory.

Do not start a local head, QEMU appliance, provider or additional farm without an explicit request. Preserve accounts, MFA, certificates, configuration and content during maintenance. Automated database fixtures require isolated storage on the operator-designated runtime host.

## Source checks

Run commands from the repository root with the required toolchains installed. The project targets Python 3.12 and uses locked uv/pnpm dependencies; JavaScript and portable toolchain pins live in `package.json` and `deploy/bootstrap`. Historical tool availability is not a guarantee for a fresh checkout.

```powershell
uv sync --locked --group appliance --group knowledge
pnpm install --frozen-lockfile
```

The standard-library documentation check needs no application environment:

```powershell
python scripts/check_docs.py
git diff --check
```

It checks local links, fences, placement and all 119 baseline files against original hashes or explicitly documented privacy-redaction hashes. It does not validate external URLs, heading anchors or product behavior.

After contract changes, regenerate shared artifacts:

```powershell
uv run --group knowledge python scripts/dev.py generate
```

For frontend changes:

```powershell
pnpm typecheck
pnpm build
```

These are source checks, not deployment. Keep generated contracts in Git; keep toolchains, builds, certificates and weights out. See [Git rules](operations/GIT_REPOSITORY.md).

## Runtime verification

Use [the testing guide](TESTING.md). Inspect fixtures before execution: some reset storage, and older scripts assume a disposable developer appliance. `scripts/dev.py check`, `check-offline`, `scripts/development_stack.py qualify-linux`, `scripts/qualify_connector.py` and the old live identity/browser helpers are not turnkey live-farm commands. The offline exclusion list does not cover every newer database test.

Run backend checks against isolated storage on the authorized runtime host. Configure `HEARTH_TEST_APP_DATABASE_URL` and `HEARTH_TEST_MIGRATION_DATABASE_URL` privately for that storage with separate roles and current migrations. The application role must not own tables, be a superuser or bypass RLS. Never target the production database or identity realm with reset/first-Owner fixtures.

Keep TLS validation enabled. Distinguish browser fixtures from real authenticated workflows and real inference from transport fixtures. Use tests appropriate to the change, record limitations, and do not add overlapping focused-run totals together. Update the [ledger](implementation/BUILD_STATUS.md) and feature evidence. Builds and heartbeats do not close release gates.

## Deployment and worker maintenance

Set `HEARTH_SSH_TARGET` privately to the authorized maintenance account and host before running this read-only status command. `/opt/hearth` is the documented default package path; use your actual installation path if different:

```powershell
ssh "$env:HEARTH_SSH_TARGET" "cd /opt/hearth && sudo python3 scripts/head.py status"
```

Follow [VM operations](operations/ESX_HEAD.md). On the VM, `sudo python3 scripts/head.py up` rebuilds services and applies migrations; it is a maintenance operation. Preserve private configuration, encryption keys, trust and named volumes, with a backup before migration work. The [fresh-head](operations/HEAD_VM_SETUP.md) and [ZIP](operations/VM_PACKAGE.md) guides do not describe resetting or restoring this farm.

Worker updates require pause/drain, reviewed inventories and signed recipes; see [workers](implementation/MANAGED_WORKERS.md) and [geometry](implementation/LOCAL_GEOMETRY.md). Do not independently start services that share a worker-managed GPU. External LM Studio loading policy stays under the user's control.

## Optional connector packages

Connector ZIPs are generated, ignored build outputs, absent from a fresh source checkout. With Go available to `scripts/dev.py`, run:

```powershell
python scripts/build_connectors.py
```

This produces unsigned Windows AMD64, Linux AMD64/ARM64 and macOS AMD64/ARM64 ZIPs plus `dist/connectors/manifest.json`. It does not start listeners or enroll workers. Cross-compilation is not hardware qualification. See [LAN setup](implementation/LAN_PROVIDER_TESTING.md); approved private HTTP remains an alternative for existing providers.

## Repository map

| Path | Responsibility |
|---|---|
| `services/api/src/hearth` | FastAPI BFFs, identity/policy, routing, providers, content, MCP/client API and queues |
| `services/api/migrations` | PostgreSQL schema, restricted roles, RLS; migrations through `0027` |
| `apps/admin-web`, `apps/user-web` | Separate React/Vite entry points |
| `packages/ui`, `packages/contracts` | Shared UI and generated contracts |
| `worker` | Native Go manager, connector, setup, host probes and cryptographic foundations |
| `runtimes` | Separate image, geometry, speech and transcription adapters |
| `deploy`, `scripts` | Deployment assets, builds and operator tooling |
| `tests`, `evidence` | Checks and dated observations with explicit fixture boundaries |
| `docs/plan`, `docs/adr`, `docs/implementation` | Immutable baseline, decisions and current records |
| `brand`, `website` | Active identity assets and static marketing site |

GitHub Actions is configured. Historical qualification records do not establish current remote CI status. Keep deployment-specific commands and runtime evidence in ignored `.hearth/` files; publish sanitized summaries as described in [repository privacy](operations/REPOSITORY_PRIVACY.md).
