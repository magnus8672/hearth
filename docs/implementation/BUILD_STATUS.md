# Hearth implementation ledger

Updated 13 September 2026. Baseline: engineering specification 1.2 and visual identity 1.0. The supplied 119 design/brand files remain unchanged and are also preserved under `docs/plan/`.

**Current milestone: first local accounts-and-workspaces test build, spanning P0 and P1.** Real Owner setup, MFA, Member registration, separate application sessions and private drafts are ready for user testing on the prepared Windows machine. Follow [TESTING.md](../../TESTING.md). Assistant replies and provider setup remain unfinished; neither P0 nor P1 exit is complete.

The user has now imported the local certificate, enrolled an authenticator and reached Administration. Zen initially reported an unknown issuer but accepted trust on a subsequent page load. Setup now distinguishes Windows root installation from three actual browser HTTPS checks, retries initial failures, and supplies browser-specific help. Its Windows status check uses the certificate-store API directly because the PowerShell `Cert:` provider was sometimes absent in Python-launched helper processes.

The running identity service now uses Hearth branding for sign-in, registration, authenticator and recovery screens. A resource-only theme JAR is available through `scripts/package_identity_theme.py`. Five appearance/flow checks and three setup-UI regressions pass. The appearance suite uses anonymous real HTTPS plus a disposable identity realm for OTP/recovery and PKCE checks; existing user accounts and credential identities were preserved. See [theme evidence](../../evidence/identity-theme/2026-09-13/theme-browser.json).

## Implemented

| Area | Concrete result | Evidence |
|---|---|---|
| Repository and dependencies | Python/Go/TypeScript workspace, dependency locks, pinned container/action revisions, generated contracts and development commands | [Development guide](../../DEVELOPMENT.md), `uv.lock`, `pnpm-lock.yaml`, `worker/go.sum` |
| Control stack | WHPX Ubuntu development appliance; PostgreSQL 18, Keycloak, FastAPI, Caddy and step-ca | [Stack evidence](../../evidence/foundation/2026-09-12/stack.json) |
| Database | Migrations 0001 and 0002, 14 capability definitions, separate database roles, forced personal-scope RLS, encrypted BFF credentials and Member-only provisioning | `tests/integration/test_postgres.py`, `tests/integration/test_identity.py` |
| Wire contracts | 29 models, 30 definitions, 116 common shape/security fixtures, generated Go/TS/OpenAPI | `packages/contracts`, `tests/fixtures/contracts.json` |
| Enrollment cryptography | Fixed-algorithm JWE, fresh IVs, binding/tamper rejection and Go/Python round trips | `tests/security/test_enrollment.py`, `tests/integration/test_shared_contracts.py` |
| Signed content | Exact JWS profile, trusted signer/revocation checks, content type binding, file digest and byte-count verification | `tests/security/test_supply_chain.py` |
| Policy | Default local-only propagation, cloud preconditions, current permissions, exact approval hash, grant scope/expiry/revocation and revision checks | `tests/security/test_contracts_and_policy.py`, `tests/security/test_admin_approval.py` |
| API boundary | Separate liveness/readiness, fail-closed configuration, trusted hosts, redacted errors, bounded chunked bodies, no header-based identity | `tests/integration/test_api.py`, `tests/security/test_request_limits.py` |
| Native entry point | Go host probes and local setup server; expiring console-bound proof, exact Host/Origin checks, fixed helper actions, explicit per-user certificate trust and one-use Owner bootstrap | `worker/cmd/hearth-setup`, [ADR 0004](../adr/0004-first-testable-identity-slice.md) |
| Browser identity | Confidential OIDC clients, exact HTTPS origins, PKCE/state/nonce, encrypted server credentials, separate secure session cookies, CSRF, revocation and local logout during IdP outage | [Real browser checks](../../evidence/identity/2026-09-12/identity-browser.json), `tests/integration/test_identity.py` |
| Accounts | Real Owner and Member sign-in, authenticator and recovery-code enrollment; absent second factor blocks session creation until enrollment; registration only grants Member | [Enrollment fallback check](../../evidence/identity/2026-09-12/credential-loss.json) |
| Browser applications | Separate bundles, original branding, three appearance choices, real farm/people overview, 14 Unassigned capabilities and responsive private draft editor | [Administration](../../evidence/identity/2026-09-12/admin-overview.png), [workspace](../../evidence/identity/2026-09-12/user-drafts.png), [mobile](../../evidence/identity/2026-09-12/user-mobile.png) |
| Private drafts | Persistent creation, editing, archiving, revision conflicts, dirty-edit protection and guessed-ID isolation across real accounts | `services/api/src/hearth/workspace.py`, [browser checks](../../evidence/identity/2026-09-12/identity-browser.json) |
| Adapter probes | Real Switchyard selection and Graphify AST extraction pass on Windows and the source-built Linux reference environment | [ADR 0001](../adr/0001-foundation-and-upstream-adapters.md) |

## Current validation

- Windows and Linux: 41 Python tests pass, including real PostgreSQL RLS, OIDC callback binding, JWT validation, session/CSRF enforcement, authorization-version revocation, draft conflicts and logout during an identity outage. API identity tests use explicit provider fixtures; they do not substitute for the live browser suite.
- Go: setup proof/Origin/Host rejection and one-use bootstrap tests pass, alongside common schema fixtures and Go/Python JWE exchanges. The Windows native setup executable builds.
- TypeScript: 116 common fixture tests, type checking and both Vite production builds pass.
- Browser: eight real-Keycloak acceptance checks pass in Chromium 153, covering Owner/MFA/recovery enrollment, real self-registration, separate sessions, private drafts, two-Member isolation, CSRF, cookie substitution and copied-session rejection after logout. The additional missing-second-factor check passes. Desktop and mobile screenshots were visually inspected.
- Welcome screens: four Playwright cases pass, including live appliance readiness; setup/session responses in these four cases remain fixtures.
- TLS: automated browser certificate validation stays enabled using an isolated Linux NSS store and a root obtained over pinned SSH. The user subsequently completed Windows trust and reached Administration in Zen. Automated theme work made no additional OS or browser trust changes.
- Persistence: one normal guest shutdown/start preserved all four synthetic accounts, draft contents/revisions and the Caddy root. Both HTTPS apps and identity returned healthy. See [restart evidence](../../evidence/identity/2026-09-12/restart.json).
- Identity and PKI: Keycloak S256 login and MFA work. Recovery-code generation was exercised; consuming/replaying recovery codes and enrolled-worker issuance are not yet acceptance-qualified.
- Initial handoff: recorded synthetic accounts and draft data were removed before user testing. The user has since created the real Owner and completed MFA. That account is preserved. No models were downloaded and no paid inference calls were made.
- GitHub Actions is configured but has not run remotely.

## Findings and remaining P0 work

1. The default virtual CPU did not satisfy Keycloak's x86-64-v2 requirement. A broad `max` profile stalled in firmware. An explicit feature profile booted and restored the real services.
2. The official Switchyard Linux x86-64 wheel stopped with SIGILL on the WHPX guest. Explicit AVX requests still produced a kernel XSAVE consistency failure, so simply adding flags is insufficient. Resolved by compiling the same hash-pinned release for x86-64-v2 with pinned Rust and maturin versions. The real Linux suite passes, without changing upstream source or substituting a fixture.
3. The production native installer/supervisor, fixed privileged-helper IPC, signed appliance distribution, watchdog and lifecycle failure recovery are not implemented by the Python development helper.
4. Go verification of the selected signed-recipe JWS profile passes against Python signatures and negative cases. Additional adversarial wire semantics and explicit version normalization need completion before accepting executable plans.
5. Trusted HTTPS BFF login and private workspaces are implemented and tested, and the user has completed Windows trust and Owner/MFA setup. The signed production installer, wider browser-trust qualification, role-management UI, broader recovery/step-up scenarios, SSE lifecycle and LAN browser trust remain open.
6. The database was upgraded to migration 0002. A complete nonempty upgrade/backup/restore acceptance fixture remains pending; a normal restart is narrower evidence.
7. Other host/guest architectures remain unqualified. OS floors and release constraints are recorded in [ADR 0002](../adr/0002-installation-trust-and-native-boundaries.md).
8. The required local geometry pipeline has a selected qualification candidate in [ADR 0003](../adr/0003-local-geometry-pipeline.md). No 3D model has been installed or run.
9. The guest later panicked while running systemd with unsupported user shadow-stack exposure. The reference now masks that guest CPU feature with `clearcpuid=519`, retaining the original QEMU 11.1 UEFI/WHPX configuration. Post-change Python, real-browser and normal-restart checks pass. Root-cause confirmation and a long-duration soak remain open; see [ADR 0005](../adr/0005-whpx-shadow-stack-compatibility.md).

## Phase status

| Phase | Status |
|---|---|
| P0 foundation | In progress; implemented and verified areas listed above |
| P1 identity and separate shells | Local Owner/MFA/signup, separate sessions and private drafts testable; phase gates remain open |
| P2 discovery and enrollment | Wire and cryptographic primitives only |
| P3 storage and catalog | Capability definitions and interface only |
| P4 first provider, local inference and admin agent | Provider/grant contracts and policy primitives only |
| P5 routing and cloud | Adapter probe and policy primitives only |
| P6 shared tools | Interface only |
| P7 knowledge | AST feasibility probe only |
| P8 collaboration and media | Geometry request contract and qualification decision only |
| P9 release and operations | Not started |

All [61 release gates](RELEASE_GATES.md) remain open. Foundation and local identity evidence cover only parts of the binding scenarios. A12's media subcases remain required for P8.

## Next implementation slice

Collect the user's local setup/workspace results, continue native appliance reliability and trust qualification, then connect durable enrollment and a first real provider. Close remaining P1 role/session/recovery acceptance alongside that work. P4 must support local-head, joined-member and OpenAI-first paths without mandatory NAS, MCP or Graphify setup. Preserve the current explicit Unassigned states until a provider produces verified readiness and a real response.
