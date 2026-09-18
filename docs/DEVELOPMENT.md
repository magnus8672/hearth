# Developing hearth

Updated 18 September 2026. Start with [repository guidance](AGENT_GUIDANCE.md), [current farm state](implementation/CURRENT_STATE.md), [coverage](implementation/DESIGN_COVERAGE.md) and [build status](implementation/BUILD_STATUS.md).

## Active environment

Edit source and use Git on this workstation. Run head/application integration work on the existing ESXi VM at `10.20.30.10`, SSH user `operator`, checkout `/opt/hearth`, Compose project `hearth-head`. media-worker (`10.20.30.20`, also `operator`) hosts the approved Fooocus and TRELLIS services. The workstation's independent LM Studio at `10.20.30.30:1234` supplies Qwen inference.

Do not start `Start-Hearth.ps1`, `scripts/start_local.py`, the retired QEMU appliance, or local hearth-managed providers. Preserve the old farm data. Existing accounts, MFA, certificates, configuration and user content on the live farm must survive maintenance. Do not create an additional farm for tests.

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

It checks local links, fences, placement and all 119 immutable snapshot hashes. It does not validate external URLs, heading anchors or product behavior.

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

Use [the active testing guide](TESTING.md). Inspect fixtures before execution: some reset storage, and older scripts assume a disposable developer appliance. `scripts/dev.py check`, `check-offline`, `scripts/development_stack.py qualify-linux`, `scripts/qualify_connector.py` and the old live identity/browser helpers are not turnkey live-farm commands. The offline exclusion list does not cover every newer database test.

Run backend checks against isolated storage on the existing VM. Configure `HEARTH_TEST_APP_DATABASE_URL` and `HEARTH_TEST_MIGRATION_DATABASE_URL` privately for that storage with separate roles and current migrations. The application role must not own tables, be a superuser or bypass RLS. Never target the production database or identity realm with reset/first-Owner fixtures.

Keep TLS validation enabled. Distinguish browser fixtures from real authenticated workflows and real inference from transport fixtures. Use tests appropriate to the change, record limitations, and do not add overlapping focused-run totals together. Update the [ledger](implementation/BUILD_STATUS.md) and feature evidence. Builds and heartbeats do not close release gates.

## Deployment and worker maintenance

Read-only status:

```powershell
ssh operator@10.20.30.10 "cd /opt/hearth && sudo python3 scripts/head.py status"
```

Follow [ESXi operations](operations/ESX_HEAD.md). On the VM, `sudo python3 scripts/head.py up` rebuilds services and applies migrations; it is a maintenance operation. Preserve private configuration, encryption keys, trust and named volumes, with a backup before migration work. The [fresh-head](operations/HEAD_VM_SETUP.md) and [ZIP](operations/VM_PACKAGE.md) guides do not describe resetting or restoring this farm.

Worker updates require pause/drain, reviewed inventories and signed recipes; see [workers](implementation/MANAGED_WORKERS.md) and [geometry](implementation/LOCAL_GEOMETRY.md). Do not independently start Fooocus and TRELLIS on their shared GPU. External LM Studio loading policy stays under the user's control.

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
| `services/api/migrations` | PostgreSQL schema, restricted roles, RLS; migrations through `0025` |
| `apps/admin-web`, `apps/user-web` | Separate React/Vite entry points |
| `packages/ui`, `packages/contracts` | Shared UI and generated contracts |
| `worker` | Native Go manager, connector, setup, host probes and cryptographic foundations |
| `runtimes` | Separate image, geometry, speech and transcription adapters |
| `deploy`, `scripts` | Deployment assets, builds and operator tooling |
| `tests`, `evidence` | Checks and dated observations with explicit fixture boundaries |
| `docs/plan`, `docs/adr`, `docs/implementation` | Immutable baseline, decisions and current records |
| `brand`, `website` | Active identity assets and static marketing site |

GitHub Actions is configured. Remote CI status was not verified in the 18 September review because GitHub SSH authentication failed. Old laptop commands remain in the [archived guide](archive/status-2026-09-18/DEVELOPMENT_PRE_REFRESH.md) solely to explain historical evidence.
