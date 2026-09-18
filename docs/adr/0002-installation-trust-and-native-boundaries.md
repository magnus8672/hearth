# ADR 0002: appliance, trust and native execution boundaries

> Status reconciliation, 18 September 2026: Architecture decision with historical foundation evidence. The active head now runs on ESXi, with MFA/SSO, pending signup and per-user grants. The full installer/helper, managed enrollment and release host matrix remain open. Use [current coverage](../implementation/DESIGN_COVERAGE.md) and [the farm snapshot](../implementation/CURRENT_STATE.md) for present status.

> Historical foundation decisions and then-current qualification are retained below. Real local BFF/Owner/MFA setup subsequently shipped; production supervisor, managed enrollment and the wider host/trust matrix remain open. See [current coverage](../implementation/DESIGN_COVERAGE.md).

Status: accepted architecture; development qualification is partial, 12 September 2026.

The first native installer explicitly creates the only control head. A restart, missing head or join failure must never create another farm. QEMU runs a same-architecture Linux appliance with hardware acceleration. Inference runs on native workers when the approved recipe supports that host; the appliance does not imply GPU passthrough.

## Target OS floor and qualification

These floors are hearth packaging decisions, not claims that every target has passed testing.

| Target | Minimum packaging target | Accelerator | Current evidence |
|---|---|---|---|
| Windows x86-64 | Windows 11 24H2, build 26100 | WHPX | Native probe and Ubuntu x86-64 guest boot passed |
| Linux x86-64 | Ubuntu 24.04 LTS | KVM | Go build target and access probe implemented; clean-host boot pending |
| Linux arm64 | Ubuntu 24.04 LTS | KVM | Go build target and access probe implemented; guest lock and boot pending |
| macOS Intel | macOS 15 | HVF | Go build target and host probe implemented; packaging and boot pending |
| macOS Apple Silicon | macOS 15 | HVF | Go build target and host probe implemented; guest lock and boot pending |

The native `doctor` command is read-only. It reports whether a host accelerator is available without claiming a farm, model or guest is ready. Linux `/dev/kvm` access is a prerequisite check, not proof that VM creation works.

The development reference uses the hash-verified Windows QEMU package dated 20260811, reporting `11.1.0 (v11.1.0-12130-ge470268ff4)`. This distribution is a development probe, not the eventual signed release bundle. Ubuntu 24.04 image build 20260911 is pinned by digest. Host and container locks are under `deploy/`.

QEMU's default CPU lacked x86-64-v2 features required by the chosen Keycloak image. `-cpu max` then caused a firmware exception on this WHPX host. The qualified profile is `qemu64,+ssse3,+sse4.1,+sse4.2,+popcnt,+cx16,+lahf-lm`. UEFI uses separate code and variable pflash drives. A later vector-feature probe still caused Linux to disable XSAVE and AVX after an XSAVE consistency failure. The guest cannot be treated as AVX2 capable. Qualify the source-built Switchyard baseline instead of assuming CPU flags took effect. Do not substitute emulation or weaken host mitigations. [QEMU WHPX documentation](https://www.qemu.org/docs/master/system/whpx.html).

## Supervisor and helper contract

The production native supervisor must persist the host identity, farm choice, appliance image digest, controller generation, disk ownership and last healthy release. Fixed operations are `inspect_host`, `create_appliance`, `start_appliance`, `stop_appliance`, `update_appliance`, `collect_sanitized_diagnostics` and `remove_installation`. Only a locally authenticated installer/service may request privileged operations. Each mutating operation needs an idempotency key, expected installed revision, immutable package reference and bounded resource allocation.

The privileged helper cannot accept shell text, executable paths, environment variables, arbitrary download URLs, unbounded mounts or arbitrary filesystem targets. It resolves approved package/entrypoint IDs internally, verifies signatures and digests, and restricts staging to service-owned directories. Rollback must respect database and recipe compatibility. Removing software must preserve farm state unless a separate explicit data-removal decision is made.

`scripts/appliance.py` is a reference development supervisor. Its pinned SSH maintenance channel, sudo account and source synchronization must not ship as the production member-management interface. Service registration, watchdog recovery, installer IPC and signed release image assembly are outstanding implementation work.

## Cryptographic profile

Pairing uses a local 256-bit proof and standard JWE with exactly `alg=dir`, `enc=A256GCM`. Both maintained Go and Python JOSE libraries pass bidirectional fixtures. Bindings include attempt, node, nonce, public-key fingerprint, origin and expiry. Header extensions, tampering and unexpected algorithms fail. Durable one-use consumption, central approval, TLS transition, CSR issuance and revocation are P2 integration work.

Package/recipe/plan signatures use JWS with exact `alg=Ed25519`, approved `kid`, and a fixed content type. Verification uses a local public-key allowlist and revocation set. This uses the fully specified identifier registered by RFC 9864; the earlier polymorphic `EdDSA` identifier is deprecated. Python signing and Go verification pass shared positive and negative cases. Go uses go-jose's opaque-verifier extension with the standard library's Ed25519 operation. [RFC 9864](https://www.rfc-editor.org/rfc/rfc9864.html).

The development stack starts both Caddy's isolated development CA and step-ca. Caddy's root is retrieved over pinned SSH and used in an application-scoped TLS verifier; hostname and chain checks remain enabled. step-ca health is verified against its own root. Production offline root custody, restricted issuance templates and browser trust bootstrap remain outstanding. [Smallstep container setup](https://smallstep.com/docs/tutorials/docker-tls-certificate-authority/).

## BFF design to implement before P1 qualification

Release IP mode uses admin `https://<head>:8443`, user `https://<head>:8444`, and identity `https://<head>:8445`. Cookies are not isolated by port. Use distinct host-only, Secure, HttpOnly session-cookie names; store sessions server-side with an application audience and exact origin. Never accept an admin cookie on the user BFF or a user cookie on admin routes.

OIDC must use authorization code, S256 PKCE, nonce, one-use state, exact redirect URI and issuer/audience checks. Require exact `Origin` and session-bound CSRF for state changes, and independently authorize SSE/history access. Trusted proxy information must be constrained to the edge. Owner bootstrap is a local console-bound one-use proof; a remote LAN visitor cannot claim it.

This design is locked for implementation. Working browser signup, MFA, step-up, callback replay rejection, cookie swapping and browser trust are not proven by the P0 shells or by the Keycloak discovery probe.
