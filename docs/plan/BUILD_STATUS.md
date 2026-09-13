# Build status ledger

Last updated: 12 September 2026.

**The specification is complete as a planning deliverable. Application implementation has not started.** No machine has been enrolled, no NAS mounted, no model downloaded/loaded, and no cloud provider configured by this planning task.

| Phase | Implementation | Verification | Evidence |
|---|---|---|---|
| P0 | Not started | Not run | None |
| P1 | Not started | Not run | None |
| P2 | Not started | Not run | None |
| P3 | Not started | Not run | None |
| P4 | Not started | Not run | None |
| P5 | Not started | Not run | None |
| P6 | Not started | Not run | None |
| P7 | Not started | Not run | None |
| P8 | Not started | Not run | None |
| P9 | Not started | Not run | None |

## Next concrete task

Read [BUILD_HANDOFF.md](BUILD_HANDOFF.md), the binding [installation contract](11-INSTALLATION-AND-CENTRAL-MANAGEMENT.md) and [first-provider/admin-agent contract](12-ADMIN-AGENT-AND-FIRST-PROVIDER.md). Inspect the target repository and implement P0, including portable installer/appliance, provisioning, wizard/provider and admin-management contracts. Preserve this ledger as the implementation proceeds.

## Environment values still to be supplied through setup

- Controller host/domain and allowed LAN ranges.
- NAS host/share/subdirectory and secure dedicated credentials.
- Exact worker hardware inventory and pairing proofs.
- Approved model files, source/license records and compatible runtime packages.
- Optional OpenAI API key, model IDs and authorized spending limit.

These are deployment inputs, not unanswered architecture choices. Independent software construction and fixture-backed tests can proceed before they are available.

## Session handoff template

```text
Date / repository revision:
Current phase and last passed gate:
Implemented behavior:
Verification commands and evidence paths:
Known failures / externally blocked gates:
New ADRs and rationale:
Next concrete runnable task:
```

## Specification revision 1.2

Current package revision is 1.2. It adds a deterministic first-provider wizard and a protected admin agent that can perform real setup operations after local-head, member or OpenAI readiness. The minimum safe cloud adapter and useful admin tooling move into P4, independent of NAS/MCP/knowledge availability. A01-A12 are required release gates. No provider connection, paid call, admin agent or application has been executed by this planning update.

The setup and central-management contract is binding: first installer creates the Hearth Node, members supply address/port only, proof approval and all service configuration occur in Hearth. Host packaging targets include Windows/Linux and Intel/Apple Silicon macOS, subject to real validation. No installer, hypervisor image, runtime recipe or application has been implemented or executed by this documentation update.
