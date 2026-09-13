# Hearth implementation ledger

Updated 12 September 2026. Baseline: engineering specification 1.2 and visual identity 1.0. The supplied 119 design/brand files remain unchanged and are also preserved under `docs/plan/`.

**Current milestone: P0 development foundation implemented in part; P0 exit remains open.** The real reference appliance and control services run. Early browser shells are present. This is not a usable assistant or a completed identity phase.

## Implemented

| Area | Concrete result | Evidence |
|---|---|---|
| Repository and dependencies | Python/Go/TypeScript workspace, dependency locks, pinned container/action revisions, generated contracts and development commands | [Development guide](../../DEVELOPMENT.md), `uv.lock`, `pnpm-lock.yaml`, `worker/go.sum` |
| Control stack | WHPX Ubuntu development appliance; PostgreSQL 18, Keycloak, FastAPI, Caddy and step-ca | [Stack evidence](../../evidence/foundation/2026-09-12/stack.json) |
| Database | Migration 0001, 14 capability definitions, built-in permissions, separate database roles and forced personal-scope RLS | `tests/integration/test_postgres.py` |
| Wire contracts | 29 models, 30 definitions, 116 common shape/security fixtures, generated Go/TS/OpenAPI | `packages/contracts`, `tests/fixtures/contracts.json` |
| Enrollment cryptography | Fixed-algorithm JWE, fresh IVs, binding/tamper rejection and Go/Python round trips | `tests/security/test_enrollment.py`, `tests/integration/test_shared_contracts.py` |
| Signed content | Exact JWS profile, trusted signer/revocation checks, content type binding, file digest and byte-count verification | `tests/security/test_supply_chain.py` |
| Policy | Default local-only propagation, cloud preconditions, current permissions, exact approval hash, grant scope/expiry/revocation and revision checks | `tests/security/test_contracts_and_policy.py`, `tests/security/test_admin_approval.py` |
| API boundary | Separate liveness/readiness, fail-closed configuration, trusted hosts, redacted errors, bounded chunked bodies, no header-based identity | `tests/integration/test_api.py`, `tests/security/test_request_limits.py` |
| Native entry point | Go `doctor` and version commands, WHPX/KVM/HVF prerequisite probes | `worker/cmd/hearth-worker`, `worker/internal/host` |
| Browser entry shells | Separate admin/user bundles, original artwork and tokens, system/daylight/firelight persistence, mobile layout and actual database status | [Admin daylight](../../evidence/foundation/2026-09-12/admin-daylight.png), [firelight](../../evidence/foundation/2026-09-12/admin-firelight.png), [user mobile](../../evidence/foundation/2026-09-12/user-mobile.png) |
| Adapter probes | Real Switchyard selection and Graphify AST extraction pass on Windows and the source-built Linux reference environment | [ADR 0001](../adr/0001-foundation-and-upstream-adapters.md) |

## Current validation

- Windows and Linux: 36 Python tests pass, including the real PostgreSQL integration case, signed-recipe interoperability and the 116 shared fixtures within the cross-language test.
- Go: common schema fixtures pass and Go/Python JWE exchanges pass. The Windows native doctor confirms WHPX availability.
- TypeScript: 116 common fixture tests, type checking and both Vite production builds pass.
- Browser: four Playwright checks pass, covering failure recovery, persisted themes, both mobile bundles and live appliance connectivity. Desktop and mobile screenshots were visually inspected.
- TLS: certificate-chain and hostname validation pass using the explicitly retrieved development root. A forged identity header still receives 401.
- Identity and PKI: Keycloak discovery advertises S256 PKCE; step-ca health validates against its own root. Neither is a claim of working Hearth login or enrolled-worker issuance.
- GitHub Actions is configured but has not run remotely.

## Findings and remaining P0 work

1. The default virtual CPU did not satisfy Keycloak's x86-64-v2 requirement. A broad `max` profile stalled in firmware. An explicit feature profile booted and restored the real services.
2. The official Switchyard Linux x86-64 wheel stopped with SIGILL on the WHPX guest. Explicit AVX requests still produced a kernel XSAVE consistency failure, so simply adding flags is insufficient. Resolved by compiling the same hash-pinned release for x86-64-v2 with pinned Rust and maturin versions. The real Linux suite passes, without changing upstream source or substituting a fixture.
3. The production native installer/supervisor, fixed privileged-helper IPC, signed appliance distribution, watchdog and lifecycle failure recovery are not implemented by the Python development helper.
4. Go verification of the selected signed-recipe JWS profile passes against Python signatures and negative cases. Additional adversarial wire semantics and explicit version normalization need completion before accepting executable plans.
5. The exact-origin BFF design is documented, but trusted browser Owner/signup, cookie swapping, CSRF, MFA and callback replay tests are pending. The shells explicitly disclose that sign-in is unavailable.
6. An empty PostgreSQL database was migrated successfully. A future nonempty schema upgrade/restore fixture needs a meaningful prior application revision.
7. Other host/guest architectures remain unqualified. OS floors and release constraints are recorded in [ADR 0002](../adr/0002-installation-trust-and-native-boundaries.md).
8. The required local geometry pipeline has a selected qualification candidate in [ADR 0003](../adr/0003-local-geometry-pipeline.md). No 3D model has been installed or run.

## Phase status

| Phase | Status |
|---|---|
| P0 foundation | In progress; implemented and verified areas listed above |
| P1 identity and separate shells | Entry shells started; authentication and acceptance gates not complete |
| P2 discovery and enrollment | Wire and cryptographic primitives only |
| P3 storage and catalog | Capability definitions and interface only |
| P4 first provider, local inference and admin agent | Provider/grant contracts and policy primitives only |
| P5 routing and cloud | Adapter probe and policy primitives only |
| P6 shared tools | Interface only |
| P7 knowledge | AST feasibility probe only |
| P8 collaboration and media | Geometry request contract and qualification decision only |
| P9 release and operations | Not started |

All [61 release gates](RELEASE_GATES.md) remain open. Partial foundation evidence is recorded without promoting it to a complete product acceptance result. A12's media subcases remain required for P8.

## Next implementation slice

Close the remaining P0 trust/installer contracts, then implement local one-use Owner bootstrap and separate OIDC BFF sessions. Make signup, private workspaces, real capability cards and role enforcement work over trusted HTTPS before exposing enrollment or first-provider actions. P4 must support local-head, joined-member and OpenAI-first paths without mandatory NAS, MCP or Graphify setup.
