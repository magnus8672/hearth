# hearth design coverage

Updated 18 September 2026, including geometry catalog names/thumbnails, the responsive workspace and conversation GPU queue fixes in the [implementation ledger](BUILD_STATUS.md). Farm configuration is recorded separately in the [dated snapshot](CURRENT_STATE.md). All fourteen capability profiles have bounded executable implementations. **The local application is operational; the full distributed-farm and release requirements remain incomplete.** No P0–P9 phase exit is declared complete. The [61-gate ledger](RELEASE_GATES.md) remains 20 partial, 41 not run and zero fully passed.

This document describes implementation coverage. The snapshot describes which providers and routes are actually configured on the user's farm. Browser fixtures, real provider calls, source builds and live authenticated acceptance are distinct evidence.

## Current coverage

| Area | Implemented and recorded evidence | Remaining scope |
|---|---|---|
| Control head and contracts | Python/FastAPI, PostgreSQL, separate admin/user BFFs and React bundles, generated Python/Go/TS contracts; migrations through `0026`; running ESXi head | Production service separation, full protocol compatibility and clean-host release matrix |
| Signup and access | Console Owner bootstrap, Keycloak MFA, pending signup with zero grants, People approval/suspension/roles, individual capability grants, protected Owners and authorization-version fences | Invitations/email verification, custom/group/workspace roles, recovery administration, account erasure and full RBAC acceptance |
| Sessions and trust | Separate BFF audiences/cookies, PKCE/state/nonce, CSRF, MFA SSO between applications, HTTPS and public certificate onboarding | Sensitive-action step-up, wider OS/browser trust and recovery/session lifecycle qualification |
| Private data | Forced owner/farm/joined-channel RLS; separate application and migration roles; private credentials and artifacts | Comprehensive deletion/backup retention, storage encryption posture and complete cross-service adversarial matrix |
| External providers | Multiple connections of each type, several models per server, many-to-many capability bindings, explicit resource groups, per-connection HTTPS trust or approved private HTTP, native loaded-instance preflight for LM Studio | Broad provider/context/quality attestation, remote no-auto-load enforcement and full physical-host loss/recovery qualification |
| Capability routing | Seven text profiles, private vision, image, geometry, speech, transcription and two built-in memory profiles; ordered eligible targets and immutable route receipts | Live Switchyard integration, quality-ranked placement, semantic/multilingual classification, general scheduling/affinity |
| Native managed services | Go worker adopts already installed Linux systemd services through signed recipes; outbound verified HTTPS, scoped poll credential, leases/revisions, file checks, stop/cgroup confirmation and health readiness; media-worker controls Fooocus/TRELLIS | Address-only enrollment, CSR/mTLS/rotation/revocation lifecycle, installers, arbitrary supported package provisioning, multiple physical managed workers and power-loss recovery |
| GPU admission and queues | Shared resource reservations, unknown-execution fences, persistent image/geometry gallery queue shared with private chat and channel images, planned batches, owner fairness, quotas, queued/running cancellation and approved service switching | Universal queues for text/audio/client API, authenticated hardware fit/placement and sustained multi-user mixed live load |
| Model storage and distribution | Signed-manifest/digest primitives and pinned runtime/model inventories; explicit prepared installs | NAS/local catalog UI, secure storage gateway, scoped resumable transfers, quarantine/license approval, cache management and complete NodePlan staging |
| Private chat | Durable idempotent turns, streaming, model identity, bounded reasoning preview, side notes, stop/drain/steer, explicit continuation and private native tool loop | General leased job/task-tree recovery, long-context negotiation, summary compaction and broad provider-format quality |
| Channels | Explicit joining, separate shared history, new human mention dispatch, text/images and model attribution | Full workspace ACL/moderation, shared tool/memory workflows and shared 3D artifacts |
| Images | Direct/contextual chat and channel generation, batches up to four, description-based variations, private gallery, Fooocus options and AI-upscaled 4K, PNG validation, cancellation and head-side deletion | Pixel editing/inpainting, natural-language advanced-option planning, broader model selection/quality and provider/backup erasure |
| Geometry | TRELLIS.2 Q8 image-to-3D at 512/1024, typed HTTPS jobs, shared GPU queue, private validated textured GLBs, required names/rename, static reference thumbnails, interactive preview/export/delete/cancel; gallery/chat/channel image handoff | Natural-language text/chat-to-3D chaining, independent editor import, broader quality/physical scale, rigging/animation/editing and sustained mixed load |
| Vision | Private still-image upload/paste/drop, normalized pixels, actual pixel-reading probe and image-context routing; historical real Qwen evidence | Current farm's saved Qwen vision qualification, channel uploads, document ingestion and image editing |
| Speech and transcription | Private saved Kokoro Read aloud and reviewed English microphone/PCM-WAV Whisper transcripts, typed authenticated jobs and real historical CPU evidence | Active-farm provider installation/registration, physical microphone/listening quality, more languages/formats/voices and managed release packages |
| Memory | PostgreSQL full-text private recall, editable notes/preferences and message corrections, source revisions/lineage, export/import, durable vault projection and offline explicit-link Graphify export | Semantic extraction/embeddings/topic assertions, summary compaction, external knowledge placement, continuous Obsidian sync and complete deletion |
| Shared tools | Streamable HTTP MCP gateway with three discovery/execution facade tools, reviewed schemas, per-user credentials, one-time write approvals and no-replay receipts; real Qwen/tool evidence | Managed stdio/packages, per-task filesystem/shell sandboxes, remote toolbox placement, OAuth and general crash recovery |
| Client API | Scoped/revocable user keys, ready capability aliases, text Chat Completions streaming and caller-owned function round trips; actual Hermes discovery and small real client calls | Complete Hermes/OpenClaw/Continue workflows, Responses/embeddings/media APIs and JSON-schema structured output |
| Protected admin agent | Contract/policy primitives for reviewed changes, grants, scope/hash/revision checks | Usable agent UI and runtime, fixed management executor, secure-input/approval flows and durable management operations |
| First-provider/cloud paths | Useful existing-service path from ADR 0006; local-only policy and zero cloud budget | Original managed head/member and OpenAI-first setup paths, cloud gateway, budget reservation/accounting and authorized paid acceptance |
| Head operations | Fresh-farm Linux package, running ESXi head, hostname migration preserving farm identity/trust, certificate export and bounded rollback | Signed/offline distribution, guided Move hearth, full backup/restore/upgrade, watchdog and host-loss qualification |
| Observability and release | Health endpoints, scoped operational metadata/audit writes, dated evidence and pinned CI configuration | Audit/support UI, complete metrics/alerts/retention, remote CI verification, accessibility/load/hardware matrix, SBOM/signing and release acceptance |

Use the feature guides in [the index](../README.md) for actual bounds, tests and operational instructions. The [archived audit](../archive/status-2026-09-18/DESIGN_COVERAGE_PRE_REFRESH.md) retains the original 45-row sweep and intermediate statements; its old missing-feature lists are historical.

## Capability profiles and the running farm

Seven text profiles share the compatible chat transport: conversation, planning, code explanation, coding, writing, summarization and extraction. A text transport probe does not demonstrate code execution, specialist quality or vision. Tools require their own native call/result probe; caller-owned tools execute in the external client.

The active farm has three provider targets: model-host Qwen, media-worker Fooocus and media-worker TRELLIS. Chat, Coding, Images and Geometry have compatible saved assignments. Vision is assigned but its saved target features currently omit `vision`. The other five text specialists have no dedicated bindings; automatic routing may use general chat for an unassigned specialist. Audio has no registered providers. Memory executes inside the head and does not require a model assignment. See [exact endpoints and observed settings](CURRENT_STATE.md).

A saved ready media target need not have its service running: media-worker explicitly shares one GPU and selects Fooocus or TRELLIS for gallery work. This qualified exception does not change the default architecture of resident specialists on independently resourced machines. Desired service, observed process state and verified capability readiness remain separate.

## Same-type provider registration and resident models

Multiple instances of every provider family remain a core requirement. Connections are keyed by farm/address; targets by connection/model. The current farm limit is 32 targets, and a capability supports up to eight ordered choices. A repeated model identifier on different machines is valid. Multiple URLs on one physical GPU must not multiply its capacity.

Explicit Add server/Add model flows, preserved assignments, deliberate resource groups and LM Studio loaded-instance checks have browser and concurrent loopback-server coverage. Historical real GPT-OSS/Qwen streams overlapped on independent physical hosts. These do not establish the complete multi-server UI, residency/no-auto-load, failure/recovery and sustained-load acceptance matrix. The active farm now runs one Qwen LLM target, so that historical two-LLM topology is not today's inventory.

The normal external-provider request path does not load, unload or swap models. Loaded-instance preflight observes state; it is not an atomic reservation or proof of the server's JIT policy. See [residency](MULTI_PROVIDER_RESIDENCY.md), [provider lifecycle](PROVIDER_LIFECYCLE.md) and [ADR 0006](../adr/0006-managed-and-external-providers.md).

## Phase exits still open

| Phase | Delivered portion | Exit work |
|---|---|---|
| P0 foundation | Stack, contracts, crypto and upstream probes | Production supervisor/helper and platform/protocol qualification |
| P1 identity | MFA/SSO, pending signup, grants and private content | Full roles, recovery, step-up, LAN/browser policy and acceptance |
| P2 discovery/enrollment | Crypto foundations plus bounded signed service adoption | Actual address-only join, pairing/mTLS, identity lifecycle and returning-node recovery |
| P3 storage/catalog | Inventories, signatures/digests and prepared runtimes | Catalog/gateway/NAS, authorized staging and cache lifecycle |
| P4 inference/admin | Existing-service inference and manual admin controls | Three original bootstrap paths and useful protected admin-agent operations |
| P5 routing/cloud | Ordered local routing and client API | Live Switchyard, broader scheduling and complete cloud boundary |
| P6 tools | Working shared HTTP gateway and native model loop | Managed packages, sandboxes, remote placement and restart recovery |
| P7 knowledge | Private recall, revisions and vaults | Semantic graph/topic work, placement and complete deletion |
| P8 media/collaboration | Channels, image planning, vision/audio implementations and real private GLBs | General specialist task trees, full media workflow/quality/editor import and A12 expansion |
| P9 release | Fresh-head package and substantial bounded evidence | Remaining gates, signed installers, restore, hardware/load/accessibility acceptance |

## Next work and non-goals

1. Qualify the active configuration: vision verification, intentional specialist assignments, full client workflows, and provider busy/loss/recovery behavior. Audio installation is a separate deployment task.
2. Complete managed membership and provisioning, preserving signed typed operations and existing-service ownership.
3. Implement the protected admin agent and original bootstrap paths, including cloud boundaries before any paid test.
4. Extend scheduling/specialist cooperation, managed tool isolation and semantic knowledge on the existing working slices.
5. Qualify geometry import/quality and sustained mixed media work, then complete recovery and release acceptance.

Hybrid expert caches, shared-model role warming and planner/executor/reviewer experiments remain proposals. Distributed VRAM pooling, Kubernetes and a compulsory vector database remain outside the baseline. Required local 3D and the P8 parts of A12 stay binding. The static website deliberately presents the finished-product vision; its marketing copy is not engineering readiness evidence.
