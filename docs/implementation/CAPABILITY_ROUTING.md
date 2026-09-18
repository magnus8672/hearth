# Capability routing and external LAN providers

> Current status, 18 September: all fourteen bounded profiles are implemented. The initial assignment matrix below records the 13 September milestone, not the active farm. Live dispatch remains deterministic; Switchyard is not on its request path. See [the dated farm snapshot](CURRENT_STATE.md) and [current coverage](DESIGN_COVERAGE.md).

Implemented 13 September 2026. This slice separates the fourteen capability assignments from provider registration and makes the existing text and image transports usable through those assignments. It preserves the fixed control-plane, identity, privacy and resource-pool boundaries in ADR 0006.

## Available behavior

Administration has a revisioned assignment editor for every capability, including the profiles that were assignment-only at this milestone. All fourteen profiles now have bounded implementations. An assignment contains up to eight distinct targets in explicit order. An empty saved assignment stays disconnected after provider verification. Concurrent edits return a conflict. Mutations require current admin-audience authorization and CSRF protection, and farm RLS protects the underlying records.

Conversation and the six text specialists use verified OpenAI-compatible chat targets. Direct English requests select planning, code explanation, coding, writing, summarization or extraction. The workspace also has an explicit text-specialist selector, preserved through durable steering. Only the current human request selects an intent; quoted conversation history and model output cannot select a server or authority. A legacy farm with no specialist assignment retains general chat. Once a specialist is assigned, an unavailable route fails closed instead of silently switching to general chat.

Channel mentions use the same text routes and channel-only context. Image planning uses the planning assignment, then releases the text resource before admitting the image assignment. Existing batch bounds, scoped artifacts, cancellation and uncertain-execution fencing remain intact.

Before dispatch, targets must match the adapter, verified features, evidence lifetime and current resource admission. Locked or occupied resource pools are skipped without blocking competing admissions. Priority only chooses among candidates before a new execution. A partial response, failed request or missing completion receipt never causes a second generation on another target.

Editing a connection preserves its target ID and capability assignments while invalidating previous evidence. It can change the server URL, model, protocol, resource group, key and per-connection certificate trust. Busy/uncertain groups cannot be moved. Shared credentials and trust cannot be silently replaced through one of several models. New executions record the capability, route revision, target revision, provider and model identity. Later connection edits do not rewrite that receipt. Legacy receipts are explicitly labeled as values copied from the current target during migration, because historical revisions cannot be reconstructed.

## Historical initial assignment matrix

| Capabilities | Initial provider | Executable scope |
|---|---|---|
| Conversation, planning, code explanation, coding, writing, summarization, extraction | Existing LM Studio / GPT-OSS target | Text input and text replies; no file attachment, command execution or admin tools |
| Image generation | Existing hearth SDXL target | Text-to-image jobs, including contextual planning and batches |
| Vision, transcription, speech, memory retrieval, memory indexing | Intended LM Studio target | Assignment only; required adapters/probes pending |
| 3D generation | Intended image target | Assignment only; geometry adapter and mesh qualification pending |

At that milestone the last two rows were deliberately not ready; the current adapters and availability are documented in the snapshot above. Text transport evidence is not vision, speech, retrieval or mesh evidence. Specialist task quality also remains separate from a successful text transport probe. Required local 3D and P8/A12 have not been removed from scope.

## Native connector

The portable Go connector wraps one fixed loopback inference service with authenticated TLS. The head trusts a supplied public CA only for the registered provider connection; hostname validation, private-address restrictions, DNS pinning and redirect rejection remain enabled. No operating-system CA installation or insecure TLS option is added.

The connector's fixed operation allowlist covers chat, model discovery, current hearth image jobs and reserved compatible embedding/audio endpoints. This does not enable their missing head-side adapters. It strips browser cookies and controller credentials, uses a separate optional upstream key, bounds requests before forwarding, rejects browser Origin requests and avoids request-content logs. It exposes no shell, filesystem, model installation or general HTTP proxy.

Windows AMD64, Linux AMD64/ARM64 and macOS Intel/Apple Silicon development packages are built. They are not signed worker packages or enrolled workers. The Windows and Linux AMD64 loopback TLS tests execute on their respective reference environments; other architectures are cross-compiled only. Automatic approval review rejected the combined command to initialize and launch the real LAN listeners with the generic reason `blocked by policy`. No LAN listener was started by that command and multi-host qualification remains open. Use the [LAN testing guide](LAN_PROVIDER_TESTING.md) to start a connector on another machine.

## Verification

- Migration 0010 adds route revisions and connection trust; migration 0011 preserves execution identity. A private database backup preceded the migrations. Existing Owner, MFA, conversations and artifacts remain in place.
- Windows and reference Linux each pass 183 Python tests with six opt-in live tests skipped. The new coverage includes route order, locked-pool admission, no replay after unknown outcomes, stale edits, explicit disconnect, unsupported profiles, tenant isolation, retargeting, steering and connection-specific TLS trust.
- All 156 shared contract fixtures pass, as do TypeScript validation, production builds and Go tests. OpenAPI includes the closed assignment and connection-edit request models.
- Nineteen browser regressions pass, including saved route ordering, correct capability destinations, mobile overflow, retargeting and explicit verification.
- A separate opt-in test exercised all six text specialists against real LM Studio and an actual contextual planning-to-SDXL handoff. Its target records use the same physical GPU; it uses synthetic OIDC in a disposable farm. [Live evidence](../../evidence/routing/2026-09-13/live-routing.json) and the saved PNG are synthetic test content, not personal conversations.
- Both native reference platforms pass connector allowlist/authentication tests and real loopback TLS tests rejecting wrong CAs and hostnames. Python separately tests the head's connection-specific trust and hostname validation over a real loopback TLS socket.

The [deployment verification](../../evidence/routing/2026-09-13/validation.json) records served asset hashes, loaded backend source hashes, database revision and actual farm assignment readiness. The immutable 119-file input snapshot is preserved. All 61 release gates remain unpassed and paid provider calls remain zero.
