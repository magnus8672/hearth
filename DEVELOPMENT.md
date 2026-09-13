# Building Hearth

The supplied product documents remain the baseline. Their immutable copy is in [docs/plan](docs/plan/README.md). Read the current [implementation ledger](docs/implementation/BUILD_STATUS.md) for what actually works. The root `BUILD_STATUS.md` is part of the original design package.

This checkout currently provides a development foundation, with a real Linux control stack and separate browser entry shells. It does not yet provide account setup, enrollment, inference, or a production installer.

## Reference environment

Windows 11 x86-64 with Windows Hypervisor Platform enabled, Python 3.12, uv 0.12.5, Node 24.14.0, pnpm 11.19.0, OpenSSH and 7-Zip. The development guest reserves 4 virtual CPUs, 8 GiB RAM and a sparse 48 GiB disk. Downloads and private runtime state stay in ignored `.hearth/`. No models are downloaded by these commands.

Install dependencies and the pinned portable toolchains:

```powershell
uv sync --locked --group appliance --group knowledge
pnpm install --frozen-lockfile
uv run python scripts/bootstrap.py
```

Start the accelerated guest, then wait for its first cloud-init package installation to finish:

```powershell
uv run --group appliance python scripts/appliance.py up
uv run --group appliance python scripts/appliance.py status
```

`status` reports Docker and Compose when the guest is ready. The first boot needs network access and can take several minutes. It never falls back to CPU emulation. Once ready, a single command uploads the current sources, generates private development credentials, applies migrations and starts PostgreSQL, Keycloak, Caddy, step-ca and the API:

```powershell
uv run --group appliance python scripts/dev.py stack
```

The guest is reachable only through QEMU's host-loopback forwards. Development SSH is pinned to the seeded host key. It is a developer maintenance channel, not the member enrollment or central management protocol. Credentials are generated locally and are never production bootstrap accounts.

## Browser shells

In separate terminals:

```powershell
pnpm dev:admin
pnpm dev:user
```

- Admin: [localhost:5173](http://127.0.0.1:5173)
- User: [localhost:5174](http://127.0.0.1:5174)

The Vite development servers bind to loopback and proxy only the readiness endpoint. They show actual database connectivity and explicitly state that sign-in is unfinished. These HTTP development origins are not the release BFF origins.

## Verification

Regenerate all wire artifacts after changing a contract:

```powershell
uv run --group knowledge python scripts/dev.py generate
```

Run Go validation, Go/Python encryption interoperability, Python policy tests, the real database isolation tests, TypeScript validation and both production frontend builds:

```powershell
uv run --group knowledge python scripts/dev.py check
```

`check` fails if a required integration is unavailable. `check-offline` explicitly excludes PostgreSQL and does not qualify appliance startup, identity or TLS.

Run the same Python integration suite inside the appliance, with a Linux Go interoperability binary and Switchyard compiled from its pinned source release for x86-64-v2:

```powershell
uv run --group appliance python scripts/development_stack.py qualify-linux
```

The first Linux build includes a Rust compiler stage and takes several minutes. Compilers are excluded from the final runtime image. The published Linux Switchyard wheel requires AVX2, which the reference WHPX guest does not provide correctly; the source build is an explicit compatibility requirement.

Run browser regressions and capture live screenshots:

```powershell
pnpm exec playwright install chromium
$env:HEARTH_LIVE_UI = '1'
pnpm test:e2e
```

Three browser tests use isolated response fixtures to exercise failure recovery, themes and mobile layout. The fourth uses the real appliance and is enabled by `HEARTH_LIVE_UI=1`.

Collect TLS, identity discovery, CA health and source-preservation evidence:

```powershell
uv run --group appliance --group knowledge python scripts/record_evidence.py
```

The evidence command obtains Caddy's development root over the authenticated SSH channel and verifies HTTPS with an application-scoped trust context. It does not change the operating system certificate store or bypass browser certificate warnings.

For CI or another developer database, set `HEARTH_TEST_APP_DATABASE_URL` and `HEARTH_TEST_MIGRATION_DATABASE_URL`. Roles must be initialized with `deploy/compose/init-databases.sh` and migrated with `HEARTH_MIGRATION_DATABASE_URL` using `uv run alembic upgrade head`. The application role must not be a superuser, table owner or RLS-bypass role.

## Stop and resume

Stop the guest through its authenticated shutdown path:

```powershell
uv run --group appliance python scripts/appliance.py down
```

Wait for the recorded QEMU process to exit before restarting. The system disk and generated credentials persist. A failed launch does not create another farm. Never delete `.hearth/` to fix an existing farm or discard its database without an explicit recovery plan.

## Repository map

| Path | Responsibility |
|---|---|
| `services/api/src/hearth` | Closed contracts, policy, adapters, cryptographic verification, API and database access |
| `services/api/migrations` | Restricted-role PostgreSQL schema and frozen initial catalog seeds |
| `worker` | Native Go entry point, host probes, shared schema validation and enrollment cryptography |
| `apps/admin-web`, `apps/user-web` | Separate React/Vite application bundles |
| `packages/ui` | Shared components using original brand sources |
| `packages/contracts` | Generated JSON Schema, OpenAPI and TypeScript artifacts |
| `deploy` | Pinned development containers, appliance and toolchain dependencies |
| `scripts` | Bootstrap, generation, supervisor, stack and evidence commands |
| `tests` | Security, shared wire, real database, adapter and browser regressions |
| `docs/adr` | Explicit implementation decisions and qualification limits |
| `docs/implementation` | Current build and release-gate ledgers |

GitHub Actions is configured with pinned action revisions. A remote CI run has not yet been observed.
