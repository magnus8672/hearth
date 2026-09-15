# Documentation inventory

Reviewed 13 September 2026. The pre-move inventory contained 84 Markdown paths representing 55 distinct file contents. All 55 documents were reviewed; 29 redundant paths matched existing baseline documents. The source package includes 30 Markdown files and 89 supporting assets, preserved unchanged under `plan/`.

The [coverage audit](implementation/DESIGN_COVERAGE.md) maps these requirements to code and recorded evidence. Older milestone reports retain their historical scope with pointers to the current state. External source URLs were not re-researched during this repository audit.

## Original specification and reference package (30)

| Document | Role in this audit |
|---|---|
| [Architecture and decisions](plan/01-ARCHITECTURE.md) | Farm boundaries, component roles, resource admission and latency targets. |
| [Discovery, enrollment, and worker lifecycle](plan/02-DISCOVERY-AND-WORKERS.md) | Address-only join, untrusted discovery, enrollment, leases, revocation and node lifecycle. |
| [NAS, model catalog, and artifact delivery](plan/03-NAS-AND-MODELS.md) | NAS/local model library, signed catalog, bounded staging, cache and artifacts. |
| [Security, identity, RBAC, and trust](plan/04-SECURITY-AND-RBAC.md) | Threat model, identity, farm/workspace roles, RLS, isolation and locality. |
| [Agent runtime, routing, cloud fallback, and shared tools](plan/05-RUNTIME-ROUTING-AND-TOOLS.md) | Durable broker, specialist delegation, Switchyard, MCP and OpenAI gateway. |
| [Conversation history, Obsidian vaults, Graphify, and retrieval](plan/06-MEMORY-AND-KNOWLEDGE.md) | Vault projection, assertions, Graphify, source-cited retrieval and deletion. |
| [User and administrator interfaces](plan/07-INTERFACES.md) | User/admin navigation, assignment and setup flows, memory/media and accessibility. |
| [Data and API contracts](plan/08-DATA-AND-API-CONTRACTS.md) | Typed entities, endpoints, events, worker transport, grants and turn ordering. |
| [Validation, quality, and release gates](plan/09-VALIDATION-AND-RELEASE.md) | All 61 acceptance scenarios, quality/hardware/load tests and release outputs. |
| [Deployment and operations](plan/10-OPERATIONS.md) | Install/update, recovery, failures, observability and scheduling. |
| [Installation and central node management](plan/11-INSTALLATION-AND-CENTRAL-MANAGEMENT.md) | Binding Create/Join, managed appliance, pairing, NodePlans and provisioning. |
| [First inference provider and the hearth admin agent](plan/12-ADMIN-AGENT-AND-FIRST-PROVIDER.md) | Binding three-path bootstrap, protected agent, approvals, secrets and operation lifecycle. |
| [hearth visual identity](plan/brand/BRAND_GUIDE.md) | Original v1.0 identity; historical, superseded by active brand 1.2. |
| [Build handoff](plan/BUILD_HANDOFF.md) | Fixed stack, completion definition and implementation authority; retains local 3D. |
| [Build status ledger](plan/BUILD_STATUS.md) | Historical all-planned ledger from the source package. |
| [Rendered diagram gallery](plan/diagrams/README.md) | Original source-diagram gallery; all fourteen SVGs retained. |
| [Specification validation](plan/DOCUMENT_CHECKS.md) | Historical specification-only integrity checks, not product acceptance. |
| [P0: foundation and integration contracts](plan/phases/P0-FOUNDATION.md) | Foundation contracts, real upstream probes and appliance prerequisites. |
| [P1: identity, RBAC, and separate application shells](plan/phases/P1-IDENTITY-AND-SHELLS.md) | Real identity, roles, separate apps and secure setup acceptance. |
| [P2: discovery, secure pairing, and node lifecycle](plan/phases/P2-DISCOVERY-AND-ENROLLMENT.md) | Minimal member install, pairing, inventory and returning-node acceptance. |
| [P3: secure NAS library and model staging](plan/phases/P3-NAS-AND-CATALOG.md) | Gateway/catalog/recipe preparation and verified resumable transfer. |
| [P4: first inference provider, local models, and the admin agent](plan/phases/P4-LOCAL-INFERENCE.md) | Managed inference, all first-provider paths and useful protected admin actions. |
| [P5: Switchyard routing, capability coverage, and OpenAI overflow](plan/phases/P5-ROUTING-AND-CLOUD.md) | Selection, policy-controlled cloud and optional client compatibility API. |
| [P6: shared MCP toolbox](plan/phases/P6-SHARED-TOOLS.md) | Real isolated MCP servers/tools and scoped side-effect handling. |
| [P7: shared conversation history and topic memory](plan/phases/P7-CONVERSATION-MEMORY.md) | Vaults, retrieval, Graphify, correction and complete deletion. |
| [P8: specialist collaboration and multimodal output](plan/phases/P8-COLLABORATION-AND-MEDIA.md) | Brokered specialists and actual image/3D/transcription/speech outputs. |
| [P9: hardening, packaging, recovery, and release](plan/phases/P9-HARDENING-AND-RELEASE.md) | Signed packaging, clean hosts, recovery and the full release matrix. |
| [hearth: a private, distributed AI farm](plan/README.md) | Original design navigation, phase overview and binding product requirements. |
| [Sources and upstream boundaries](plan/SOURCES.md) | Dated upstream references and integration boundaries; not refreshed by this audit. |
| [Video review: hybrid local inference and staged specialist work](plan/VIDEO-REVIEW-IH8XmxiwliQ.md) | Optional hybrid/expert-cache and staged-work experiments; later binding 3D references distinguished. |

## Architecture decisions (6)

| Document | Role in this audit |
|---|---|
| [ADR 0001: control stack and upstream boundaries](adr/0001-foundation-and-upstream-adapters.md) | Actual pinned Switchyard/Graphify APIs and bounded foundation qualification. |
| [ADR 0002: appliance, trust and native execution boundaries](adr/0002-installation-trust-and-native-boundaries.md) | OS targets, accelerated appliance, helper and crypto/origin boundaries. |
| [ADR 0003: local geometry pipeline](adr/0003-local-geometry-pipeline.md) | TripoSR qualification candidate and required GLB validation; no real mesh yet. |
| [ADR 0004: First testable identity and private workspace slice](adr/0004-first-testable-identity-slice.md) | Implemented local BFF/setup/identity behavior and remaining P1 differences. |
| [ADR 0005: Reference WHPX guest CPU compatibility](adr/0005-whpx-shadow-stack-compatibility.md) | Reference guest CPU workaround and unresolved production reliability. |
| [ADR 0006: managed runtimes and existing inference services](adr/0006-managed-and-external-providers.md) | Accepted existing-service extension, resource pools, TLS and replaceable media stages. |

## Implementation milestones and evidence ledgers (13)

| Document | Role in this audit |
|---|---|
| [Visual identity 1.1: the lowercase hearth](implementation/BRAND_REVISION_1_1.md) | Historical lowercase-h mark revision, superseded by integrated lockup 1.2. |
| [visual identity 1.2: one integrated hearth wordmark](implementation/BRAND_REVISION_1_2.md) | Current fireplace h + earth lockup and lowercase naming rule. |
| [hearth build preparation](implementation/BUILD_PREPARATION.md) | Historical complete-package inspection and pre-build sequencing. |
| [hearth implementation ledger](implementation/BUILD_STATUS.md) | Current implementation/evidence status, reconciled to the routing milestone. |
| [Capability routing and external LAN providers](implementation/CAPABILITY_ROUTING.md) | Current ordered routes, retargeting, receipts, connector and qualification limits. |
| [contextual image planning](implementation/CONTEXTUAL_IMAGE_PLANNING.md) | Scoped prompt preparation, description variations and durable image handoff. |
| [images inside conversations](implementation/CONVERSATION_IMAGES.md) | Original direct chat/channel image dispatch and scoped publication milestone. |
| [existing local providers and private chat](implementation/EXISTING_PROVIDER_CHAT.md) | Original LM Studio/external provider and durable private chat milestone. |
| [image batches and capability navigation](implementation/IMAGE_BATCHES_AND_CAPABILITY_NAVIGATION.md) | Bounded plural images, partial cancellation and capability destinations. |
| [hearth provider network test](implementation/LAN_PROVIDER_TESTING.md) | Portable connector setup, trust, assignments and real multi-host test procedure. |
| [notes, shared channels and local images](implementation/NOTES_CHANNELS_IMAGES.md) | Keyboard, private notes, steering, joined channels and first SDXL milestone. |
| [Release gates](implementation/RELEASE_GATES.md) | Current exact gate states; 16 partial, 45 not run, zero passed. |
| [Local Shapecast orchestration inspection](implementation/SHAPECAST_INSPECTION.md) | Read-only pack/stage observations; not a hearth integration or quality claim. |

## Current guides (6)

| Document | Role in this audit |
|---|---|
| [hearth implementation guidance](AGENT_GUIDANCE.md) | Active repository implementation, security, brand and verification instructions. |
| [hearth visual identity](brand/BRAND_GUIDE.md) | Current v1.2 logo, lowercase copy, tokens, iconography and accessibility rules. |
| [Building hearth](DEVELOPMENT.md) | Build/check/maintenance commands, environment boundaries and recovery. |
| [hearth sign-in theme](operations/IDENTITY.md) | Branded Keycloak resources, packaging and isolated appearance qualification. |
| [hearth image provider](runtimes/IMAGE_PROVIDER.md) | Experimental SDXL environment, model closure, typed jobs and lifecycle limits. |
| [Try hearth locally](TESTING.md) | Prepared local user test procedure and current supported feature limits. |

Subsequent audio additions include [microphone/transcription](implementation/TRANSCRIPTION.md) and [its runtime guide](runtimes/TRANSCRIPTION_PROVIDER.md), outside the historical sweep count.

## Reorganization

Subsequent additions include [Read aloud](implementation/READ_ALOUD.md) and [the CPU speech runtime](runtimes/SPEECH_PROVIDER.md). These report the implemented private-speech slice and do not change the original sweep's document count.

| Original location | Current location / treatment |
|---|---|
| `DEVELOPMENT.md` | [Development guide](DEVELOPMENT.md) |
| `TESTING.md` | [Local testing](TESTING.md) |
| `AGENTS.md` content | [Repository guidance](AGENT_GUIDANCE.md); root file retained as an automatic-discovery pointer |
| `brand/BRAND_GUIDE.md` | [Current brand guide](brand/BRAND_GUIDE.md) |
| `deploy/identity/README.md` | [Identity operations](operations/IDENTITY.md) |
| `runtimes/image/README.md` | [Image provider guide](runtimes/IMAGE_PROVIDER.md) |
| Root numbered designs, handoff, planning status, document checks, sources, video review, `phases/` and `diagrams/` | Moved 42 files, including 14 SVGs, to [the duplicate archive](archive/root-package/README.md). Canonical links use `plan/` |
| Root `README.md` | Small current documentation pointer; complete original retained at [plan/README.md](plan/README.md) |
| Brand SVG/CSS/PNG sources and gallery, runtime/configuration manifests, generated API schemas, evidence | Remain at their code/asset paths; these are build inputs or test records, not relocated prose guides |

New navigation/audit documents are this inventory, [docs/README](README.md), [design coverage](implementation/DESIGN_COVERAGE.md) and the [archive note](archive/root-package/README.md). They are outputs of the sweep rather than inputs counted among the 55 reviewed documents.

All 48 moves are recorded with source paths and pre-move SHA-256 digests in [reorganization.json](../evidence/documentation/2026-09-13/reorganization.json). Duplicate removal was blocked by automatic approval review, so the duplicate documents were archived without deletion. The 119-file immutable baseline remains the preservation authority. Moved Markdown links were rebased; executable assets and historical test evidence retain their original locations.

## Provider lifecycle and VM audio setup

- [Provider lifecycle](implementation/PROVIDER_LIFECYCLE.md): persistent qualification, startup connection checks and error invalidation.
- [Audio VM setup](operations/AUDIO_VM_SETUP.md): Ubuntu systemd services, pinned model downloads, credentials, HTTPS and migration boundaries.
