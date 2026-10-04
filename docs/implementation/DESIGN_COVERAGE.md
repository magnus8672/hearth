# hearth design coverage

Reconciled 4 October 2026 with the [active roadmap](ROADMAP.md), context-continuity design and P5A plan; implemented media scope includes uploaded-image Fooocus variations, provider-specific geometry tuning and the Hunyuan3D 2.0 alternative, three-backend scheduling and geometry catalog names/thumbnails, the responsive workspace and conversation GPU queue fixes in the [implementation ledger](BUILD_STATUS.md). The [capability overview](CURRENT_STATE.md) describes roles; current farm configuration belongs in private operator records. All fourteen capability profiles have bounded executable implementations. **The local application is operational; the full distributed-farm and release requirements remain incomplete.** No P0–P9 phase exit is declared complete. The [61-gate ledger](RELEASE_GATES.md) remains 20 partial, 41 not run and zero fully passed.

This document describes implementation coverage. The public capability overview is not a live inventory. Browser fixtures, real provider calls, source builds and live authenticated acceptance are distinct evidence.

## Current coverage

| Area | Implemented and recorded evidence | Remaining scope |
|---|---|---|
| Control head and contracts | Python/FastAPI, PostgreSQL, separate admin/user BFFs and React bundles, generated Python/Go/TS contracts; migrations through `0028`; running ESXi head | Production service separation, full protocol compatibility and clean-host release matrix |
| Signup and access | Console Owner bootstrap, Keycloak MFA, pending signup with zero grants, People approval/suspension/roles, individual capability grants, protected Owners and authorization-version fences | Invitations/email verification, custom/group/workspace roles, recovery administration, account erasure and full RBAC acceptance |
| Sessions and trust | Separate BFF audiences/cookies, PKCE/state/nonce, CSRF, MFA SSO between applications, HTTPS and public certificate onboarding | Sensitive-action step-up, wider OS/browser trust and recovery/session lifecycle qualification |
| Private data | Forced owner/farm/joined-channel RLS; separate application and migration roles; private credentials and artifacts | Comprehensive deletion/backup retention, storage encryption posture and complete cross-service adversarial matrix |
| External providers | Multiple connections of each type, several models per server, many-to-many capability bindings, explicit resource groups, per-connection HTTPS trust or approved private HTTP, native loaded-instance preflight for LM Studio | Broad provider/context/quality attestation, remote no-auto-load enforcement and full physical-host loss/recovery qualification |
| Capability routing | Seven text profiles, private vision, image, geometry, speech, transcription and two built-in memory profiles; ordered eligible targets and immutable route receipts | P5A live Switchyard and typed decision service, quality-ranked placement, semantic/multilingual classification, general scheduling/affinity |
| Native managed services | Go worker adopts already installed Linux systemd services through signed recipes; outbound verified HTTPS, scoped poll credential, leases/revisions, file checks, stop/cgroup confirmation and health readiness; media-worker controls Fooocus/TRELLIS/Hunyuan3D 2.0 | Address-only enrollment, CSR/mTLS/rotation/revocation lifecycle, installers, arbitrary supported package provisioning, multiple physical managed workers and power-loss recovery |
| GPU admission and queues | Shared resource reservations, unknown-execution fences, persistent image/geometry gallery queue shared with private chat and channel images, planned batches, owner fairness, quotas, queued/running cancellation and approved service switching | Universal queues for text/audio/client API, authenticated hardware fit/placement and sustained multi-user mixed live load |
| Model storage and distribution | Signed-manifest/digest primitives and pinned runtime/model inventories; explicit prepared installs | NAS/local catalog UI, secure storage gateway, scoped resumable transfers, quarantine/license approval, cache management and complete NodePlan staging |
| Private chat | Durable idempotent turns, streaming, model identity, bounded reasoning preview, side notes, stop/drain/steer, explicit continuation and private native tool loop | General leased job/task-tree recovery, model-aware context budgets, source-linked compaction and broad provider-format quality |
| Channels | Explicit joining, separate shared history, new human mention dispatch, text/generated images, private upload drafts published to joined members without Vision dispatch, geometry reference handoff and model attribution | Full workspace ACL/moderation, shared tool/memory workflows and shared 3D artifacts |
| Images | Direct/contextual chat and channel generation, batches up to four, description-based variations, private gallery, Fooocus options and AI-upscaled 4K, uploaded-image pixel variations with strength control through the fair media queue, PNG validation, cancellation and head-side deletion | Masked inpainting/outpainting, chat attachment editing, natural-language advanced-option planning, broader model selection/quality and provider/backup erasure |
| Geometry | TRELLIS.2 Q8 at 512/1024 and Hunyuan3D 2.0 at 128–512, 30 typed tuning controls with defaults and saved settings, typed HTTPS image-to-3D jobs, shared GPU queue, private validated textured GLBs, required names/rename, static reference thumbnails, interactive preview with directional lighting, GLB/OBJ ZIP export/delete/cancel; gallery/chat/channel image handoff | Natural-language text/chat-to-3D chaining, independent editor import, broader quality/physical scale, rigging/animation/editing and sustained mixed load |
| Vision | Private still-image upload/paste/drop, normalized pixels, actual pixel-reading probe and image-context routing; historical real Qwen evidence | Current farm's saved Qwen vision qualification and document ingestion; gallery image editing uses Fooocus independently |
| Speech and transcription | Private saved Kokoro Read aloud and reviewed English microphone/PCM-WAV Whisper transcripts, typed authenticated jobs and real historical CPU evidence | Active-farm provider installation/registration, physical microphone/listening quality, more languages/formats/voices and managed release packages |
| Memory | PostgreSQL full-text private recall, editable notes/preferences and message corrections, source revisions/lineage, export/import, durable vault projection and offline explicit-link Graphify export | Semantic extraction/embeddings/topic assertions, durable summary compaction, external knowledge placement, continuous Obsidian sync and complete deletion |
| Shared tools | Streamable HTTP MCP gateway with three discovery/execution facade tools, reviewed schemas, per-user credentials, one-time write approvals and no-replay receipts; real Qwen/tool evidence | Managed stdio/packages, per-task filesystem/shell sandboxes, remote toolbox placement, OAuth and general crash recovery |
| Client API | Scoped/revocable user keys, ready capability aliases, text Chat Completions streaming and caller-owned function round trips; actual Hermes discovery and small real client calls | Complete Hermes/OpenClaw/Continue workflows, Responses/embeddings/media APIs and JSON-schema structured output |
| Protected admin agent | Contract/policy primitives for reviewed changes, grants, scope/hash/revision checks | Usable agent UI and runtime, fixed management executor, secure-input/approval flows and durable management operations |
| First-provider/cloud paths | Useful existing-service path from ADR 0006; local-only policy and zero cloud budget | Original managed head/member and OpenAI-first setup paths, cloud gateway, budget reservation/accounting and authorized paid acceptance |
| Head operations | Fresh-farm Linux package, running ESXi head, hostname migration preserving farm identity/trust, certificate export and bounded rollback | Signed/offline distribution, guided Move hearth, full backup/restore/upgrade, watchdog and host-loss qualification |
| Observability and release | Health endpoints, scoped operational metadata/audit writes, dated evidence and pinned CI configuration | Audit/support UI, complete metrics/alerts/retention, remote CI verification, accessibility/load/hardware matrix, SBOM/signing and release acceptance |

Use the feature guides in [the index](../README.md) for actual bounds, tests and operational instructions. The [archived audit](../archive/status-2026-09-18/DESIGN_COVERAGE_PRE_REFRESH.md) retains the original 45-row sweep and intermediate statements; its old missing-feature lists are historical.

## Capability profiles and the running farm

Seven text profiles share the compatible chat transport: conversation, planning, code explanation, coding, writing, summarization and extraction. A text transport probe does not demonstrate code execution, specialist quality or vision. Tools require their own native call/result probe; caller-owned tools execute in the external client.

Capability availability depends on each deployment's registered targets, saved verification and resource groups. The [capability overview](CURRENT_STATE.md) describes those requirements without publishing a private farm inventory.

A saved ready media target need not have its service running: explicit shared-GPU mode selects Fooocus, TRELLIS or Hunyuan for the scheduled media job. This qualified exception does not change the default architecture of resident specialists on independently resourced machines. Desired service, observed process state and verified capability readiness remain separate.

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
| P4 inference/admin | Existing-service inference and manual admin controls | Managed text runtime, measured context profiles, three original bootstrap paths and useful protected admin-agent operations |
| P5 routing/cloud | Ordered local routing and client API | P5A decision/selection integration, opt-in client continuity, broader scheduling and complete cloud boundary |
| P6 tools | Working shared HTTP gateway and native model loop | Managed packages, sandboxes, remote placement and restart recovery |
| P7 knowledge | Private recall, revisions and vaults | Token budgets, durable compaction, semantic graph/topic work, placement and complete deletion |
| P8 media/collaboration | Channels, image planning, vision/audio implementations and real private GLBs | General specialist task trees, full media workflow/quality/editor import and A12 expansion |
| P9 release | Fresh-head package and substantial bounded evidence | Remaining gates, signed installers, restore, hardware/load/accessibility acceptance |

## Next work and non-goals

The [P5A routing and decision-services design](P5A_ROUTING_AND_DECISIONS.md), dated 4 October, carves out the next local-routing phase and a new typed decision capability. The selected architecture starts with built-in Laya on the head, with a configurable dedicated decision binding and independent member assignments for simultaneous experiments. Checkpoint qualification and implementation remain pending; the fourteen implemented profiles and release-gate counts above are unchanged.

The [active roadmap](ROADMAP.md) consolidates 35 missing/incomplete items, 10 separately prioritized extension groups and 8 qualification groups. It retains the newer P5A direction and the earlier [continuity design](CONTEXT_CONTINUITY_PLAN.md), with stable R01-R34 identifiers and R35 for the typed decision service.

1. Advance P5A's benchmark/service/selection/classification/direct-use slices and private-chat budgeting/compaction as independent workstreams, each with its own acceptance checks.
2. Define opt-in external-client continuity; preserve ordinary stateless Chat Completions and qualify real clients.
3. Deliver a managed text-runtime pilot, then complete enrollment, worker trust, provisioning and model/NAS delivery.
4. Complete protected administration and original bootstrap paths, including cloud boundaries before paid tests.
5. Extend general scheduling, specialist consultation, managed tools, semantic knowledge and remaining media workflows. Uploaded-image variation is already delivered; masks and instruction-exact editing remain open.
6. Complete identity, privacy, retention, host operations and release packaging alongside their dependent features, then close full recovery, client, hardware and quality acceptance.

Hybrid expert caches, shared-model role warming and planner/executor/reviewer experiments remain proposals. Distributed VRAM pooling, Kubernetes and a compulsory vector database remain outside the baseline. Required local 3D and the P8 parts of A12 stay binding. The static website deliberately presents the finished-product vision; its marketing copy is not engineering readiness evidence.
