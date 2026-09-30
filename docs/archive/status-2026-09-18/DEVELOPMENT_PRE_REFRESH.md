# Historical copy captured 18 September 2026

> Privacy note: deployment identifiers and workstation paths below are sanitized examples. This is a historical record, not current deployment instructions.

This document preserves the pre-refresh text, including superseded status claims and historical development commands. It is not an operating guide. Use the [current documentation index](../../README.md) and [dated farm snapshot](../../implementation/CURRENT_STATE.md). Do not start the retired appliance or run its fixtures against the live farm.

# Building hearth

**Active deployment and runtime testing use the ESX VM at 10.20.30.10**, maintained through `operator` SSH and sudo in `/opt/hearth`. Follow [VM operations](../../operations/ESX_HEAD.md). The laptop remains the source/Git and browser/client workstation. Do not start its QEMU appliance, local head or hearth-managed providers. Preserve its old farm data. The appliance/startup commands below are historical reference and do not override this test-host decision. Offline source generation, lint and documentation checks remain available locally; runtime and integration checks must target the VM with live data protected.

For a standalone head reachable from other machines, use [head VM setup](../../operations/HEAD_VM_SETUP.md). For independent speech/transcription installation, model preparation and boot services, use [audio VM setup](../../operations/AUDIO_VM_SETUP.md).

The head now serves a [shared MCP gateway and capability-based client API](../../implementation/SHARED_TOOLS_AND_CLIENT_API.md). Compose includes an isolated reference MCP service. Register tools centrally and connect local agents with capability aliases. Managed tool packaging, filesystem sandboxes and full external harness qualification remain open.

The supplied product documents remain the baseline. Their immutable copy is in [docs/plan](../../plan/README.md). Read the current [implementation ledger](../../implementation/BUILD_STATUS.md) and [coverage audit](../../implementation/DESIGN_COVERAGE.md) for what actually works. The original planning ledger is `docs/plan/BUILD_STATUS.md`.

Run every command in this guide from the repository root, `C:\src\hearth` on the prepared machine, unless a command explicitly changes directory.

This checkout provides local chat, private side notes and steering, saved Read aloud recordings, reviewed microphone/WAV transcripts, joined channels and SDXL image generation inside chats and channels as well as the private gallery. A local prompt planner resolves contextual image requests and description-based variations. Owner setup, MFA, Member signup, separate admin/user sessions, the capability catalog and private drafts work against real services. Start with [TESTING.md](../../TESTING.md) on the prepared Windows machine. Existing local model registration, feature probes and private streamed chat are now testable. Signed managed runtimes, worker enrollment and the production installer remain unfinished. The optional experimental image process is documented in [runtimes/image](../../runtimes/IMAGE_PROVIDER.md). The separate CPU speech process reuses explicitly supplied model files and has its own locked environment; see [the speech runtime](../../runtimes/SPEECH_PROVIDER.md). The [CPU transcription provider](../../runtimes/TRANSCRIPTION_PROVIDER.md) has its own pinned model and dependency environment. The local launcher resumes each prepared provider when its private configuration exists. See [provider implementation notes](../../implementation/EXISTING_PROVIDER_CHAT.md).

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

`status` reports Docker and Compose when the guest is ready. The first boot needs network access and can take several minutes. It never falls back to CPU emulation. Build both browser bundles, then upload the sources, generate private development credentials, apply migrations and start PostgreSQL, Keycloak, Caddy, step-ca and the two API processes:

```powershell
pnpm build
uv run --group appliance python scripts/dev.py stack
```

On a new guest, this command first installs the CPU compatibility profile and asks for one normal shutdown/start cycle. Run `scripts/appliance.py down`, then `scripts/appliance.py up`, wait for SSH readiness, and repeat the stack command. The `clearcpuid=519` guest setting masks unsupported user shadow stacks; it does not change Windows security settings. See [ADR 0005](../../adr/0005-whpx-shadow-stack-compatibility.md).

The guest is reachable only through QEMU's host-loopback forwards. Development SSH is pinned to the seeded host key. It is a developer maintenance channel, not the member enrollment or central management protocol. Credentials are generated locally and are never production bootstrap accounts.

## Browser applications

On the prepared stack:

```powershell
.\Start-Hearth.ps1
```

The launcher configures the fixed Keycloak realm and clients, builds the native local setup tool and opens its console-bound browser session. It does not import the local CA automatically. The explicit trust button and first Owner creation are described in [TESTING.md](../../TESTING.md).

Use [Administration](https://localhost:8443) and [Workspace](https://localhost:8444) after setup. Caddy serves the separate production bundles and proxies each to its fixed-audience BFF. The identity origin is `https://localhost:8445`. Rebuild with `pnpm build` and run the stack command after changing frontend or server code.

Identity screens use the hearth theme described in [deploy/identity](../../operations/IDENTITY.md). The theme can also be packaged as a resource-only JAR. The setup tool verifies all three origins in the user's browser independently of the Windows root-store check. Browser-probe endpoints return only a static service label, accept no credentials and grant no authority.

For frontend fixture development only, use separate terminals:

```powershell
pnpm dev:admin
pnpm dev:user
```

- Admin: [localhost:5173](http://127.0.0.1:5173)
- User: [localhost:5174](http://127.0.0.1:5174)

The Vite development servers bind to loopback and proxy only the readiness endpoint. These HTTP origins do not support real sign-in. Use the HTTPS applications for account and workspace tests.

## Verification

After moving or editing documentation, check local links, code fences, document placement and the immutable design snapshot:

```powershell
uv run python scripts/check_docs.py
```

This check does not fetch external URLs, validate heading anchors or run product acceptance tests.

Regenerate all wire artifacts after changing a contract:

```powershell
uv run --group knowledge python scripts/dev.py generate
```

Run Go validation, Go/Python encryption interoperability, Python policy tests, the real database isolation tests, TypeScript validation and both production frontend builds:

```powershell
uv run --group knowledge python scripts/dev.py check
```

`check` fails if a required integration is unavailable. The Python suite includes real PostgreSQL RLS and BFF lifecycle tests. Current counts and evidence are in the implementation ledger. OIDC responses in those API unit/integration cases are explicit fixtures; the separate live-browser suite below tests actual Keycloak. `check-offline` excludes selected database modules, but its exclusion list does not cover all newer integration modules. It is not a complete no-database check and does not qualify appliance startup, identity or TLS.

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

The browser suite covers entry/setup, providers, chat, notes/steering, channels and images. Interaction data and identity are explicit fixtures. One case uses real appliance readiness when `HEARTH_LIVE_UI=1`; its identity/setup responses remain fixtures.

The real HTTPS identity acceptance suite runs Chromium inside the Linux guest. It imports the Caddy root into an isolated browser NSS store, with certificate validation enabled. It does not change Windows trust. On an **empty, disposable test farm only**, run:

```powershell
uv run --group appliance python scripts/configure_identity.py configure
uv run --group appliance python scripts/identity_qa.py prepare
uv run --group appliance python scripts/browser_appliance.py install
uv run --group appliance python scripts/browser_appliance.py run
uv run --group appliance python scripts/identity_qa.py clean
```

`prepare` refuses a farm that already has an Owner. `clean` only removes recorded synthetic identities and stops if it finds any unrecorded real user in that farm. Credentials and authenticator material stay under ignored `.hearth/`. Never run this synthetic setup against your own established hearth. After an interrupted test, retain its QA record so cleanup remains bounded.

Current evidence is in [evidence/identity/2026-09-12](../../../evidence/identity/2026-09-12). It includes real Owner/MFA/signup, session isolation, private drafts, a missing-second-factor enrollment check and persistence across a normal guest restart. `scripts/record_evidence.py` is the historical P0 collector; its login qualification fields describe that earlier foundation scope.

For CI or another developer database, set `HEARTH_TEST_APP_DATABASE_URL` and `HEARTH_TEST_MIGRATION_DATABASE_URL`. Roles must be initialized with `deploy/compose/init-databases.sh` and migrated with `HEARTH_MIGRATION_DATABASE_URL` using `uv run alembic upgrade head`. The application role must not be a superuser, table owner or RLS-bypass role.

## Stop and resume

Stop the guest through its authenticated shutdown path:

```powershell
uv run --group appliance python scripts/appliance.py down
```

Wait for the recorded QEMU process to exit before restarting. The system disk and generated credentials persist. A failed launch does not create another farm. Never delete `.hearth/` to fix an existing farm or discard its database without an explicit recovery plan.

For service recovery, inspect status and recent logs first:

```powershell
uv run --group appliance python scripts/appliance.py status
uv run --group appliance python scripts/development_stack.py status
uv run --group appliance python scripts/appliance.py ssh 'cd /opt/hearth/deploy/compose && docker compose -f development.yaml logs --tail 60'
```

Do not publish raw service logs or private configuration. If SSH works but a service is absent, rerun the stack command. If the guest itself is unresponsive, inspect `.hearth/appliance/serial.log` before taking process action. The helper deliberately preserves the process record when it cannot confirm a normal exit.

## Repository map

Configurable capability assignments, text specialist dispatch and the optional native external-service TLS connector are described in [capability routing](../../implementation/CAPABILITY_ROUTING.md). Build portable connector packages with `uv run python scripts/build_connectors.py`; qualify its Linux loopback tests with `uv run --group appliance python scripts/qualify_connector.py`. These packages do not enroll a managed worker. See the [LAN test guide](../../implementation/LAN_PROVIDER_TESTING.md) for invocation limits and setup.

| Path | Responsibility |
|---|---|
| `services/api/src/hearth` | Closed contracts, policy, adapters, cryptographic verification, API and database access |
| `services/api/migrations` | Restricted-role PostgreSQL schema and frozen initial catalog seeds |
| `worker` | Native local setup, worker entry point, host probes, shared schema validation and enrollment cryptography |
| `apps/admin-web`, `apps/user-web` | Separate React/Vite application bundles |
| `packages/ui` | Shared components using original brand sources |
| `packages/contracts` | Generated JSON Schema, OpenAPI and TypeScript artifacts |
| `deploy` | Pinned development containers, appliance and toolchain dependencies |
| `scripts` | Bootstrap, generation, supervisor, stack and evidence commands |
| `tests` | Security, shared wire, real database, adapter and browser regressions |
| `docs/adr` | Explicit implementation decisions and qualification limits |
| `docs/implementation` | Current build and release-gate ledgers |

GitHub Actions is configured with pinned action revisions. A remote CI run has not yet been observed.
