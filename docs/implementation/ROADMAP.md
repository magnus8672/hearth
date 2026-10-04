# hearth active roadmap and remaining work

Reconciled 4 October 2026 with current `main`, including the privacy cleanup, MIT license, uploaded-image variation and [P5A routing and decision services](P5A_ROUTING_AND_DECISIONS.md). The September continuity design remains applicable. The [original plan](../plan/README.md), with its explicitly approved privacy redactions, remains the baseline; [coverage](DESIGN_COVERAGE.md) records delivered behavior and [build status](BUILD_STATUS.md) records evidence. The P5A implementation is available for an operator sweep; semantic quality and latency promotion remain open. See the [testing guide](../operations/DECISIONS_SETUP_AND_TESTING.md) and [ledger](BUILD_STATUS.md).

The scope is a farm of resident specialists on separate machines, with optional explicitly shared resources. Existing LM Studio and other compatible providers remain supported. A managed text runtime adds an easier first-party deployment path. Compaction belongs in the head and does not depend on that runtime.

## How context continuity fits the existing plan

| Work | Existing ownership | Integration and consequence |
|---|---|---|
| Effective context limits and token budgets | P4 measured context/concurrency; P5 eligible routing; P7 cited context packages | Replace the current byte window with selected-target budgeting before or between model calls. Account for tools, replies and smaller target windows. |
| Durable summaries and full-history preservation | P7 original records, source lineage, corrections, deletion and Obsidian projections | Make compaction an explicit deliverable, with visible progress, source-linked snapshots, recent turns and atomic invalidation. Preserve full originals. |
| Compaction jobs and failure recovery | P4 leased tasks; P6 tool waits; P8 parent/child slot release | Give compaction bounded durable execution without holding an answering slot or database transaction while it waits. Reuse scoped authority and no-replay behavior. |
| External-client continuity | P5 client API; P7 private history | Add an explicit opt-in compaction/session contract. Existing Chat Completions remains caller-owned and stateless by default. |
| Managed text runtime | P0 native boundaries; P2 membership; P3 packages/models; P4 pinned llama.cpp inference | Deliver an engine supervisor and measured settings, including KV format, Flash Attention, speculative decoding and context. This is already planned runtime ownership, not a new inference engine. |
| Resident deployment and compatibility | ADR 0006; P4/P5/P8 resource scheduling | Keep LM Studio interoperability and independent resident specialists. Compaction must not silently load or swap a model. |
| Full product acceptance | P7/E12-E15 lineage; P4/P8/A12 setup and growth; P9 release | Add focused compaction tests without claiming that existing full release gates have passed. |

The [context continuity design](CONTEXT_CONTINUITY_PLAN.md) supplies the detailed contract. Its portable summaries do not implement OpenAI's opaque encrypted representation. Prompt compaction and runtime KV allocation remain separate controls.

## Build order

These are useful delivery slices across the original phases, not declarations that earlier phase exits are complete. P5A is the latest selected local-routing phase. Context budgeting/compaction remains an independent ready-to-build slice; neither requires the other or a managed text runtime. This replaces the September roadmap's single total order. Run targeted acceptance alongside each slice; later acceptance work does not defer its security checks.

| Order | Deliverable | Dependencies and limits |
|---|---|---|
| 1A | P5A routing and decision services, R10/R35 | Implemented service, selection, semantic/shadow controls and direct UI/API. Complete the operator sweep and independent model-quality/performance qualification before semantic promotion; Legacy/Ordered remain defaults. |
| 1B | Private-chat context budgets and automatic compaction, R01-R02 | Independent of 1A; use a compatible provider and qualify corrections, route changes, cancellation, restart and full-history preservation. No managed runtime prerequisite. |
| 2 | External-client continuity and interoperability, R03 plus relevant X01 | Define opt-in behavior first; prove a real client uses it. Ordinary Continue/Hermes traffic keeps its current semantics. This slice can proceed independently of managed provisioning. |
| 3 | Managed text-runtime pilot, R04 | Extend approved native-worker control around a pinned engine on a supported host. A pilot using approved prepared assets is not clean-machine installation. |
| 4 | Complete fleet enrollment and deployment, R05-R09, R31, R34 | Address-only member joining, PKI, typed NodePlans and local/NAS model delivery make the runtime a complete product deployment path. Scope the actual host matrix explicitly. |
| 5 | Protected administration and original bootstrap paths, R14-R16 | Agent read/planning work can start earlier; mutation tools require their actual domain services. The OpenAI-first path requires its complete cloud boundary before any real paid call. |
| 6 | Universal scheduling, specialist collaboration and later routing policy, R10-R13 | Extend P5A with measured quality policies and general orchestration. Preserve scope, context budgets and safe release while waiting for children or tools. |
| 7 | Managed tools, semantic knowledge and complete media workflows, R17-R25 | Extend existing working slices; independent items can advance earlier when their prerequisites exist. |
| 8 | Account/security/retention and operational product completion, R26-R30, R32-R33 | Build these alongside their dependent features, then qualify complete recovery and distribution. |
| 9 | Full release qualification, Q01-Q08 | Close the remaining evidence gaps across all supported configurations; do not substitute fixtures for hardware or user-flow acceptance. |

## Missing or incomplete product implementation

Each item names the remaining portion. It does not mean its entire subsystem is absent. The references below establish its original scope and current delivered boundary.

### Context and clients

- **R01. Model-aware context budgeting:** effective loaded limits, tokenizer/template provenance, conservative estimates where needed, configurable working limits, reply/tool reservations and recalculation on specialist changes. Current private-chat context uses a bounded recent byte/message window.
- **R02. Automatic compaction:** durable jobs and versioned source-linked summaries, recent-turn retention, visible progress/inspection, source correction/deletion invalidation, restart/cancellation handling, loop prevention and full-history exports.
- **R03. Opt-in client continuity:** portable compaction requests and optional scoped sessions/revisions for external agents, including explicit retention and concurrency semantics. Existing client histories are not automatically stored or compacted.

Sources: [P4](../plan/phases/P4-LOCAL-INFERENCE.md), [P7](../plan/phases/P7-CONVERSATION-MEMORY.md), [memory](PRIVATE_MEMORY.md), [client API](SHARED_TOOLS_AND_CLIENT_API.md), [continuity design](CONTEXT_CONTINUITY_PLAN.md).

### Managed workers, runtimes and storage

- **R04. Managed text runtime:** pinned engine packaging, backend/hardware probes, measured residency and memory admission, authenticated generation/control, drain/reload/crash handling, and central context/cache/Flash Attention/MTP/concurrency settings. Existing signed media-service adoption is a foundation.
- **R05. Member discovery and enrollment:** join with only the head address/port, pending-node UI, proof approval, durable one-use enrollment, CSR identity binding, reconnect/DHCP handling, offline edits and supported native service startup. Optional DNS-SD remains a discovery hint.
- **R06. Complete worker trust lifecycle:** mutually authenticated control/inference, issuance policy, rotation, renewal, revocation of existing activity and safe re-enrollment. Existing outbound HTTPS adoption and external HTTP consent are not that complete lifecycle.
- **R07. Central NodePlan provisioning:** assignment installs approved runtime/model/tool/media dependencies, applies typed settings, reports observed state and safely updates or rolls back. Include platform compatibility, dependency deduplication, secret references and stale-command fencing. Members should not need manual Python/container setup.
- **R08. Model/package library:** head-local and NAS catalog UI, imports/downloads, quarantine, license/source review, approved immutable manifests, dependency selection and compatibility filtering. Existing manifest/signature primitives do not provide this user workflow.
- **R09. NAS gateway and caches:** registered read-only shares, credential isolation, assignment-scoped authenticated resumable transfers, digest verification, atomic cache promotion, pin-aware eviction, disk quotas, transfer throttling/progress and outage behavior.

Sources: [P2](../plan/phases/P2-DISCOVERY-AND-ENROLLMENT.md), [P3](../plan/phases/P3-NAS-AND-CATALOG.md), [P4](../plan/phases/P4-LOCAL-INFERENCE.md), [central management](../plan/11-INSTALLATION-AND-CENTRAL-MANAGEMENT.md), [current worker boundary](MANAGED_WORKERS.md).

### Routing and agent orchestration

- **R10. Live routing integration:** deliver [P5A](P5A_ROUTING_AND_DECISIONS.md): bounded semantic intent proposals, permission/eligibility checks and [NVIDIA NeMo Switchyard](https://github.com/NVIDIA-NeMo/Switchyard) selection over approved candidates, retaining ordered compatibility and opt-in balanced routing. Preserve explicit-action bypass, scoped affinity, admission rechecks, fallback and route provenance. Built-in Laya or a configured dedicated decision source supplies intent, not authority. Measured-quality policy and wider media selection remain later work. Implemented: selection-only pinned Switchyard balancing, scoped affinity, strict admission checks and opt-in semantic/shadow classification. Remaining: semantic quality/latency promotion, independent evaluation and wider measured-quality policy. See the [P5A test guide](../operations/DECISIONS_SETUP_AND_TESTING.md).
- **R11. Universal admission and queues:** extend fair durable scheduling to text, audio and client API work, with configurable per-account limits, background-job priorities, memory/slot reservations and explicit overload behavior. Media queues and independent resource pools already exist.
- **R12. General task recovery:** durable task/event trees, leased executors, attempt fencing, in-flight controller/worker-loss reconciliation, bounded result spooling, safe cancellation and resumable tool conversations. Existing per-feature receipts do not complete the general scheduler.
- **R13. Specialist consultation:** a real `ask_specialist` workflow with bounded children, cycle/depth guards, inherited scope/locality/budget, parent-slot release, cited results and visible activity. Qualify writer/coder/reviewer and illustrated/narrated workflows against a single-model baseline.
- **R35. Typed decision service and workspace:** implement P5A's isolated resident CPU Laya service and qualified dedicated-provider adapter, versioned Choice/Score/Boolean results, bounded capacity, independent internal/member assignments, explicit fallback and no recursive routing. Add `decision.evaluate` permissions/verification, private results, a Decisions page, scoped client access, target comparison and farm-map status. Implemented as the fifteenth bounded profile, including pinned CPU Laya, real typed transport, private UI/API, fallback and independent assignments. Remaining: operator acceptance, independent checkpoint evaluation and a larger dedicated challenger. The initial English benchmark misses semantic promotion targets. IDs R01-R34 remain stable.

Sources: [runtime contract](../plan/05-RUNTIME-ROUTING-AND-TOOLS.md), [P5](../plan/phases/P5-ROUTING-AND-CLOUD.md), [P8](../plan/phases/P8-COLLABORATION-AND-MEDIA.md), [residency limits](MULTI_PROVIDER_RESIDENCY.md).

### Administration and cloud

- **R14. Useful protected admin agent:** isolated admin conversations/UI, live inspection, fixed typed management tools, concrete change previews, scoped routine grants, secure input/pairing cards, durable apply/status/cancel and auditable results. Existing policy/schema primitives are not a working administrative agent.
- **R15. Complete first-provider wizard:** managed local-head, managed joined-member and explicit OpenAI-first paths, real non-mutating tool verification and useful admin-agent enablement. Existing external-server onboarding remains a supported additional path; NAS/MCP/memory must not become bootstrap prerequisites.
- **R16. Cloud gateway and accounting:** isolated provider secrets/egress, per-user and source locality consent, allowed models, versioned prices, transactional budget reservation/reconciliation, uncertain paid-call handling, usage display and supported text/tool/media adapters. Default remains local-only; real paid tests need an authorized key and budget.

Sources: [first provider/admin agent](../plan/12-ADMIN-AGENT-AND-FIRST-PROVIDER.md), [P4](../plan/phases/P4-LOCAL-INFERENCE.md), [P5](../plan/phases/P5-ROUTING-AND-CLOUD.md), [A01-A12](RELEASE_GATES.md).

### Tools, knowledge and media

- **R17. Managed toolbox packages:** approved stdio MCP launchers, isolated server processes, signed package installation, designated toolbox-worker placement and restart reconciliation. The existing three-tool HTTP proxy remains the public discovery/execution path.
- **R18. Sandboxed execution tools:** scoped file/repository operations and test execution, isolated filesystems/processes/network, bounded output artifacts and runtime support qualification. External clients already execute their own local tools; this item is hearth-managed execution.
- **R19. Broader tool authorization:** OAuth-based MCP credentials and complete workspace/task/channel policy and grants, with live revocation and uncertain side-effect recovery. Existing private per-user credentials and one-time write approvals remain implemented.
- **R20. Semantic knowledge:** local model-based entity/relation extraction, topic assertions, evidence labels, temporal supersession, semantic Graphify processing and source-grounded traversal. The current graph export follows explicit links; it is not semantic extraction.
- **R21. Deployable knowledge role:** separately placed managed knowledge services, partition isolation, NAS vault spooling, incremental/background consolidation and visible indexing/projection lag. Current private memory and vault projection run on the head.
- **R22. General artifact/document handling:** scoped reusable artifact storage/delivery, document ingestion with source references, safe previews, complete attachment exports and configurable quotas. Current image/audio/geometry stores are bounded modality-specific implementations.
- **R23. Shared workspace workflows:** audience-scoped shared memory, tool execution and context compaction, shared 3D artifacts and complete workspace ACL behavior. Channel membership, human chat, explicit `@hearth`, image sharing and private image-to-model handoff already work. Do not restore automatic channel Vision dispatch, which was deliberately removed.
- **R24. Image workflows:** masked editing/inpainting, outpainting, instruction-exact editing and conversational reference-image/advanced-setting planning remain open. Uploaded-image whole-picture Fooocus variation is implemented with edit strength and the existing private queue; it does not guarantee literal instruction adherence. Text-based variations, batches, gallery controls and AI-upscaled 4K also work. See [the delivered scope](IMAGE_OPTIONS.md#modify-an-uploaded-image--30-september-2026).
- **R25. Conversational 3D workflows:** text/chat requests that orchestrate image generation and geometry, return the result in context, and retain provenance through the chain. The current Make a model handoff and private TRELLIS/Hunyuan gallery are implemented.

Sources: [P6](../plan/phases/P6-SHARED-TOOLS.md), [P7](../plan/phases/P7-CONVERSATION-MEMORY.md), [P8](../plan/phases/P8-COLLABORATION-AND-MEDIA.md), [tools](SHARED_TOOLS_AND_CLIENT_API.md), [memory](PRIVATE_MEMORY.md), [channels](NOTES_CHANNELS_IMAGES.md), [vision](VISION_AND_CONCURRENT_FARM.md), [image options](IMAGE_OPTIONS.md), [geometry](LOCAL_GEOMETRY.md).

### Identity, privacy and operations

- **R26. Full role/group/workspace administration:** custom role composition, group policies and workspace-scoped grants. Pending signup, account approval, built-in admin/operator/auditor roles, capability grants and suspension already exist.
- **R27. Recovery and sensitive actions:** password/MFA recovery administration, Owner recovery workflows, step-up authentication for sensitive changes and complete account-erasure handling. Ordinary SSO and initial MFA/recovery-code enrollment are implemented.
- **R28. Complete conversation lifecycle, retention and deletion:** archive reopening, conversation deletion and dependent summaries/graph/cache/artifact invalidation, provider-side cleanup, configurable retention/quotas and backup deletion-ledger enforcement on restore. Archived history remains inspectable through Memory; head-side generated-image/model deletion and note tombstones are only part of this work.
- **R29. Storage and key protection:** complete encryption-at-rest and encrypted-backup posture, recovery-key handling, CA/secret rotation and coordinated restoration. Existing encrypted application secrets and HTTPS do not establish the full storage/backup requirement.
- **R30. Head operations:** guided Move/Restore hearth, consistent backup/restore across identity/database/configuration/content, fenced single-head recovery, upgrade/migration recovery, watchdogs and safe rollback. Fresh-farm ZIP setup and bounded hostname rollback already exist.
- **R31. Production host/service packaging:** signed Create/Join installers and native supervisors for the advertised host matrix, managed control appliance preparation, privileged-helper boundaries, separately deployable tool/cloud/knowledge boundaries and unattended boot/logout persistence. The live ESXi deployment remains the development/test head.
- **R32. Operational visibility:** useful audit/history/export UI, correlated task/route/child/tool traces, queue/context/VRAM/latency/throughput/storage/spend metrics, local alerts and redacted support bundles. Existing readiness endpoints and audit writes remain foundations.
- **R33. Release distribution and lifecycle:** reproducible signed/offline packages, package/update delivery, SBOM and license notices, compatibility reporting, tested rollback/uninstall, release notes and a complete evidence/support index.
- **R34. Complete network setup policy:** selectable trusted LANs/interfaces, centrally enforced listener/registration policy and integrated native application trust bootstrap across supported hosts. Existing IPv4 head URLs, root-certificate downloads/installers and hostname changes remain implemented.

Sources: [security/RBAC](../plan/04-SECURITY-AND-RBAC.md), [interfaces](../plan/07-INTERFACES.md), [operations](../plan/10-OPERATIONS.md), [central management](../plan/11-INSTALLATION-AND-CENTRAL-MANAGEMENT.md), [P9](../plan/phases/P9-HARDENING-AND-RELEASE.md), [accounts](ACCOUNT_APPROVAL.md), [head settings](HEAD_ADDRESS_SETTINGS.md).

## Documented extensions requiring separate prioritization

These are absent or incomplete, but their appearance in a feature report does not make every extension a first-release requirement. Preserve the explicitly bounded first profiles unless their scope is deliberately expanded.

- **X01. Wider client API:** JSON-schema structured output, Responses-style APIs, embeddings, legacy completions and image/audio endpoints. Chat Completions and native hearth media endpoints already exist. Structured output is a practical compatibility gap for Hermes auxiliary requests.
- **X02. Continuous Obsidian synchronization:** automatic bidirectional synchronization or a dedicated plugin. Reviewed Markdown import and full text/history export are implemented; continuous sync was explicitly deferred in the baseline.
- **X03. Optional embeddings and richer retrieval UI:** evaluate whether semantic embeddings improve recall, add richer graph navigation, and expand document formats. A compulsory vector database is not required by the design.
- **X04. Channel controls:** private/invite-only rooms, moderation and deletion controls for saved shared image attachments. Ordinary join/leave membership and attachment authorization already exist.
- **X05. Signup options:** invitations and verified-email registration, beyond the implemented approval-only signup flow.
- **X06. Extended transcription:** additional languages, MP3/M4A/WebM/FLAC input, longer recordings, streaming partial transcripts and speaker diarization. The current English PCM-WAV/review flow is implemented.
- **X07. Extended speech:** streaming audio, shared-channel speech, selectable voices, Markdown-aware spoken output and any separately scoped voice-cloning capability. Private saved Read aloud already exists.
- **X08. Advanced image controls:** reviewed checkpoint/LoRA/refiner/sampler/scheduler selection and arbitrary dimension profiles where a backend supports them. Existing styles, guidance, sharpness, steps, aspect ratios and upscaling must not be relisted as missing.
- **X09. Advanced geometry editing:** rigging, animation, interactive mesh/material editing and calibrated physical scale. Geometry/texture generation controls, previews, GLB and OBJ exports already exist; game-ready topology is not a qualified promise.
- **X10. Additional network/platform modes:** IPv6/custom public-CA/NAT address workflows and extra GPU/OS profiles beyond the tested matrix. Do not assume a backend option establishes support.

Research-only hybrid expert caching and role-warming experiments stay separate. Distributed VRAM pooling, Kubernetes, active multi-head operation and a compulsory vector database are not added to the release scope by this reconciliation.

## Implemented foundations awaiting broader qualification

These are evidence gaps, not a claim that their underlying feature is wholly unimplemented. They also include end-to-end gates that can run only after the missing portions above land.

- **Q01. External-client workflows:** full Continue/Hermes/OpenClaw agent sessions with local tools, shared MCP, long context and retries. The [19 September recovery evidence](../../evidence/client-api/2026-09-19/continue-timeout.json) records Continue connection and short streamed generation, including user confirmation; it is historical evidence, not a current end-to-end qualification.
- **Q02. Real distributed load and recovery:** independent resident LLM machines, several managed workers, sustained multi-user text/media load, fairness, busy/OOM/sleep/network loss and uncertain-cancellation recovery. Historical two-host inference and actual shared-media switching are narrower evidence.
- **Q03. Capability quality:** representative held-out text/coding/extraction/retrieval tasks, vision correctness, physical microphone/listening checks, multilingual/voice scope as advertised, and prompt-adherence media review. Passing transport or file decoding is insufficient.
- **Q04. Geometry/media workflow acceptance:** independent Blender/editor import, diverse inputs and settings, memory fit, complete illustrated/narrated and image-to-3D chains. Real textured meshes, browser preview and export fixtures already pass.
- **Q05. Cross-platform setup and trust:** fresh-head/member installations, native startup/update/uninstall, browsers and certificate installers, GPU/driver/backend profiles, package/provisioning tamper cases and real runtime residency. Cross-compilation is not OS qualification.
- **Q06. Full security and lifecycle matrix:** cross-user/workspace isolation across every path, prompt/tool injection, replay/revocation, hostile discovery/package/NAS content, local-only egress, concurrent deletion/indexing and backup restoration with deletion enforcement.
- **Q07. Operational recovery:** abrupt head/worker power loss, database/NAS/tool/knowledge outages, upgrade/migration rollback, disaster restore and single-head fencing. Bounded normal restart and hostname rollback evidence do not complete this.
- **Q08. Release quality:** accessibility, responsive/offline/error flows, secret/dependency scans, actual remote CI runs, advertised hardware matrix and the documented 10-node/20-session reference load. Finish all required release outputs and unresolved acceptance gates.

The [61-gate ledger](RELEASE_GATES.md) remains **20 partial, 41 not run, zero fully passed**. A Not run gate is a scenario status, not a standalone missing feature. No gate changes status from this documentation reconciliation. Required local 3D and the P4/P8 portions of A12 remain in scope.

## Farm configuration is a separate checklist

The [capability overview](CURRENT_STATE.md) describes implementation rather than a current deployment inventory. Read actual assignments and readiness from private operator configuration and the farm map. Speech/transcription adapters and text profiles already exist; installing/registering providers or choosing dedicated machines is configuration work. Historical provider evidence does not establish current health. Do not restore private machine inventories or addresses from older notes.

The remaining work list deliberately excludes already delivered signup approval, SSO, scoped API keys, multiple same-type servers, HTTP risk acceptance, capability bindings, Enter-to-send, side notes/steering, thinking previews, per-reply model identity, image batches/deletion/options/uploaded-image variation, private memory exports and image-to-3D handoff. MIT licensing is delivered; third-party redistribution notices and the release SBOM remain part of R33.
