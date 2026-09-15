# P2: discovery, secure pairing, and node lifecycle

Dependency: P1. Outcome: starting a worker produces an admin discovery card and a verified, manageable node.

## Build

1. Implement the minimal native installer/service, persistent identity, outbound pending registration to the supplied address/port, and optional bounded DNS-SD assistance.
2. Build pending-node cards, installer-proof approval solely in the Hearth admin UI, authenticated encrypted enrollment envelopes, automatic application trust, CSR enrollment, mutual TLS and certificate renewal. No bundle is copied back to a member.
3. Add authenticated inventory, heartbeat leases, outbound command polling, node epochs, command idempotency, and explicit revocation.
4. Build central role/settings selection, NodePlan revisions, observed service state and offline Pending delivery UI. Persist assignments while clearly showing model loading is not available until subsequent phases.
5. Joining works with multicast blocked and requires only Hearth address/port on the member. Add Windows/Linux/macOS background service startup, logout/reboot persistence and local recovery commands. An unreachable head never triggers farm creation or member promotion.

## Prove

E02 and E04; S01-S03, S09 and S14. At least two independent worker processes discover and enroll. On real LAN hardware, record time from worker start to pending card, pair, reconnect, and revoke. Test duplicate identities, expired tokens, other-key CSRs, changed DHCP address, unsupported protocol version, and multicast absence.

Add C02's enrollment portion, C03's persistence/conflicting revision cases, and C05-C06 from [validation](../../../plan/09-VALIDATION-AND-RELEASE.md). Supply no member settings beyond address/port. A forged encrypted envelope, wrong installer proof, substituted CA, replay, or bootstrap redirect cannot obtain configuration authority.

Revocation blocks existing downloads/control activity as well as new connections. An unenrolled agent has no model, prompt, or tool access. A node claiming an impossible memory value is not trusted to establish deployment readiness.

## Exit gate

Secure pairing and returning-node recovery work end to end, with spoofing and replay tests passing. Runtime load remains visibly pending until P3-P4. Package builds can be tested independently, but actual OS support is recorded only when run.

Next: [P3](../../../plan/phases/P3-NAS-AND-CATALOG.md).
