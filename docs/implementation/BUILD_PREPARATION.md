# Hearth build preparation

Prepared 12 September 2026 against engineering specification 1.2 and visual identity 1.0.

**Ready to begin P0.** The product scope, architecture, identity and delivery sequence are sufficiently defined to start implementation. The current workspace contains a design package, with no application code, dependency manifests or Git repository. This inspection adds preparation notes and reproducible inspection evidence. Application implementation and all product acceptance gates remain unstarted.

## Product understanding

Hearth, **Agentic Cloud at Home**, turns the household's approved computers into one private assistant. Users work in conversations and projects; Hearth selects available capabilities, coordinates specialists, executes authorized tools and preserves scoped history. Administrators enroll machines and assign jobs centrally. Model files come from an approved local library or NAS through a controlled gateway.

The defining installation journey is:

1. Install Hearth on a supported first host and explicitly create the farm.
2. Establish browser trust, Owner/MFA, recovery material and permitted LAN access.
3. Connect the first inference provider through a deterministic wizard: this host, an enrolled member, or OpenAI.
4. Verify an actual model response and a typed management-tool round trip.
5. Continue through the admin agent or dashboard to add storage, members and services.
6. Let Members sign up for private workspaces and use the available capabilities.

The first provider and useful admin agent precede any requirement for NAS, MCP or Graphify. The OpenAI-first path works without a local model or GPU. A local path works without an OpenAI account. Provider failure leaves manual administration usable.

## Sources reviewed and authority

The inspection covers all 30 Markdown documents: the 12 numbered engineering documents, 10 phase plans, README, build handoff, status ledger, document checks, sources, video review, diagram gallery and brand guide. It also covers the gallery HTML/JavaScript, JSON/CSS tokens, icon catalog, SVG assets, existing desktop/mobile previews and platform image exports. The complete 119-file inventory includes SHA-256 hashes in [inspection.json](../../evidence/preparation/2026-09-12/inspection.json).

| Source | Build treatment |
|---|---|
| [README](../../README.md), [handoff](../../BUILD_HANDOFF.md), numbered design documents and phase plans | Binding product baseline and fixed engineering choices |
| [Installation and central management](../../11-INSTALLATION-AND-CENTRAL-MANAGEMENT.md) | Binding Create/Join, address-and-port enrollment, managed appliance and central provisioning requirements |
| [First provider and admin agent](../../12-ADMIN-AGENT-AND-FIRST-PROVIDER.md) | Binding revision 1.2 onboarding, protected management tools, grants and operation lifecycle |
| [Brand guide](../../brand/BRAND_GUIDE.md), SVG masters and tokens | Implementation source for the existing identity |
| [Video review](../../VIDEO-REVIEW-IH8XmxiwliQ.md) | Hybrid placement, expert caching and planner/executor/reviewer comparisons remain experiments |
| Geometry requirements referenced by [P8](../../phases/P8-COLLABORATION-AND-MEDIA.md) and the handoff | Local 3D generation and validated GLB output are required despite their earlier discussion in the video review |
| [Sources](../../SOURCES.md) | Research pointers; exact upstream versions, APIs, licenses and interoperability must be revalidated in P0 |
| Gallery screenshots and prior validation reports | Design evidence, with illustrative machine names and telemetry |

No product feature is considered implemented because its screen appears in the gallery or its behavior appears in a specification example.

## Architecture to carry forward

| Boundary | Implementation baseline |
|---|---|
| Control plane | Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2 and Alembic; modular domain services with separately runnable processes |
| Durable state | PostgreSQL 18 on local SSD; transactional outbox, leased jobs, attempt fencing and row-level security |
| Native host software | Go supervisor/worker and fixed-operation privileged helpers; Windows, Linux and both macOS architectures are packaging targets |
| Control distribution | Pinned QEMU with same-architecture Linux appliances and Compose inside; native host inference avoids GPU passthrough |
| Browser applications | Separate React/TypeScript/Vite admin and user bundles; shared UI package and independent BFF sessions |
| Identity and transport | Keycloak OIDC/PKCE, Caddy, step-ca, scoped application trust and mTLS for enrolled worker traffic |
| Provisioning | Signed service recipes, immutable packages, revisioned NodePlans, capacity reservations and observed readiness |
| Inference and routing | Pinned llama.cpp adapters; Switchyard receives only eligible LLM candidates; typed dispatch handles other service families |
| Cloud | A separately deployable gateway owns provider credentials, final egress checks and reserved/settled/uncertain usage |
| Tools | Assigned isolated MCP host with per-caller grants, credential separation and durable invocation records |
| Knowledge | PostgreSQL records and full-text search, scoped Markdown/JSONL projections, derived Graphify indexes and source lineage |
| Media | Approved Diffusers, whisper.cpp and Kokoro ONNX recipes; a separately selected and validated geometry backend |

The Python services can share domain packages and a development image. Deployment boundaries for cloud, tools and privileged operations must remain enforceable. Avoid multiplying infrastructure before its process or trust boundary requires it.

Keep these distinctions explicit in schemas and UI: capability versus infrastructure role; assignment versus deployment; node health versus service readiness; desired versus observed revision; provider configured versus inference verified versus admin-agent ready; cloud configured versus allowed for this caller versus actually used for this request.

Core invariants are part of the first implementations: new users are Members, discovered nodes are untrusted, admin roles do not automatically read private content, tools and child tasks cannot expand authority, local-only labels propagate through derived outputs, and uncertain external effects are reconciled before retry. A model's text never becomes an approval or an administrative credential.

## Branding integration

Preserve the arched hearth, single ember, hearthstone and custom lowercase wordmark. Carry the existing warm neutral palette into both applications and installation surfaces. The product name is Hearth; the tagline is exactly **Agentic Cloud at Home**.

- Copy trusted vector masters into shared product assets with a checked filename mapping. Use the existing 33 icons and semantic CSS/JSON tokens; derive platform resources from the provided sources.
- Use System / Light / Dark as product settings. Daylight and Firelight remain the gallery's descriptive theme names. Restore appearance before first paint and persist the user's choice across authorized apps.
- Use the native font stacks, 16 px body/input text, 14 px essential compact labels, 44 px interaction targets and the supplied geometry. The gallery's miniature dashboard sizes are specimens.
- Pair every status with a label and distinct icon. Preserve permanent unavailable capability cards and meaningful recovery actions.
- Use `control-border` for necessary control boundaries. The decorative border cannot carry interaction state alone. In particular, light-theme muted text on raised surfaces passes with little margin, so do not reduce its opacity.
- Translate the visual system into real components: application shell, capability card, assignment drawer, provider wizard, secure-input card, change preview, activity trail, chat artifacts and recovery states.
- Validate actual component combinations in both themes at 320/390/1440 px, 200% zoom, keyboard navigation and reduced motion. Include long names, offline states and provider failure.

Existing previews show a coherent identity across desktop and mobile. The browser gallery itself is a reference artifact; its inline icon script and illustrative machine names should not become production dependencies or seed data.

## Issues to resolve during implementation

| Item | Resolution and evidence needed |
|---|---|
| Managed appliance is on P0's critical path | Prove one real supervisor-launched control appliance early. Lock host OS floors, QEMU packages, accelerator checks, guest images, networking and resource reservations. Cross-compilation is not clean-install evidence. |
| Port 8443 serves admin, bootstrap and worker traffic in the default profile | Record the exact listener/route layout in an ADR. Keep the anonymous bootstrap client isolated, enforce mTLS on enrolled routes, and test that browser access never bypasses worker authentication or vice versa. |
| Private-CA browser trust and IP-based origins | Prove loopback Owner bootstrap and trusted transition into Keycloak/BFF sessions. Test host-only cookies across ports, exact origins, redirects, CSRF and forged identity headers. |
| Go/Python enrollment envelope interoperability | Select maintained JOSE libraries, pin versions and verify the fixed JWE algorithms, node/nonce/farm/endpoint bindings, foreign CSRs, expiry and replay before enabling enrollment. |
| P4 cites A01-A12, while parts of A12 depend on later media work | Track each gate's subscenarios by phase. Prove available setup actions in P4 and the media extension in P8. Keep the complete release gate open until its required evidence exists. |
| UI states are richer than individual backend enums | Model node state, service lifecycle, deployment readiness, queue activity and policy separately. Derive Busy, Local action required, Pending delivery and effective availability from typed fields and reasons. |
| Geometry has a contract but no selected backend | Complete the P0 feasibility ADR using current primary sources, actual available hardware, runtime/model license terms, supported inputs and GLB validation. Required local geometry remains in release scope. |
| Routing/index adapters are upstream-sensitive | Exercise real pinned Switchyard and Graphify entry points behind Hearth adapters. Deterministic routing and PostgreSQL search remain defined failure paths. |
| Admin agent changes its only provider | Persist the management operation before any shutdown/reassignment, preview its impact, and retain deterministic operation status and manual repair. Test this explicitly. |
| Hardware and external services are deployment inputs | Gather exact inventory, NAS settings, model/license approvals and optional cloud credentials through product setup. Track missing real verification without blocking unrelated software work. |

These are bounded implementation investigations. The overall product architecture does not need another design questionnaire.

## First implementation sequence

P0 should produce a runnable foundation and evidence for its risky boundaries. Use small, reviewable increments in this order:

1. **Preserve and establish the repository.** Initialize Git in this workspace at build start, snapshot the delivered sources under `docs/plan/` with their relative assets, and retain the originals. Create the handoff's application/service/package directories, development commands and CI. Keep a live implementation ledger under `docs/implementation/BUILD_STATUS.md` so the supplied planning ledger remains an honest historical record. Exclude local secrets, models, VM disks, caches and generated runtime state from source control.
2. **Qualify the reference development host.** Establish the missing Go and appliance toolchains, verify a supported accelerated guest boot, and resolve compatible pinned versions. Use Python 3.12 and the real PostgreSQL 18 integration environment. Commit language lockfiles, image digests, package hashes and the first host/appliance ADR.
3. **Define the shared contracts.** Generate OpenAPI/JSON Schema and Go/TypeScript clients from typed definitions. Cover scope/locality, errors/events, capability availability, recipes/NodePlans, enrollment, provider probes, protected admin changes/grants/operations, task attempts and artifact lineage. Security-sensitive inputs reject unknown authority fields. Define exact endpoints for the abbreviated groups in the specification.
4. **Prove the trust and state foundations.** Run Go/Python JWE interoperability fixtures and origin/session-boundary checks. Start the real database, identity, edge and API inside the reference stack. Apply migrations and exercise transaction-local identity context and pooled-connection isolation with dedicated application roles.
5. **Prove adapter feasibility.** Run bounded real Switchyard/Graphify package probes; record inference/runtime and geometry feasibility. Fixtures must have a separate explicit mode that cannot start as production. Do not require paid calls for this work.
6. **Close the P0 evidence record.** Verify a fresh checkout can start the development stack, contract fixtures agree in all three languages, the reference appliance runs real services, and dependency decisions are pinned. Record any remaining platform-specific probes individually.

The first useful product milestone then spans P1-P4: trusted Create Hearth, real Owner/Member isolation, permanent capability cards, secure member enrollment, approved package/model staging, one real first-provider/tool round trip, and one authorized admin operation whose observed completion is visible. All three wizard paths must be implemented; an unavailable real provider or machine retains a specific unverified gate.

## Delivery order and acceptance

| Phase | Concrete result |
|---|---|
| P0 | Reproducible contracts, dependencies, integration stack and reference appliance proof |
| P1 | Trusted Owner bootstrap, LAN signup, private accounts, independent app sessions and branded shells |
| P2 | Address/port member join, central proof approval, mTLS identity, leases and desired/observed node state |
| P3 | Local library and secure NAS connector, approved recipes/packages/models and resumable authorized staging |
| P4 | All first-provider choices, real local inference path, safe minimum cloud gateway and useful protected admin agent |
| P5 | Multi-deployment routing, persistent capability availability and policy/budget-controlled cloud overflow |
| P6 | Assigned MCP toolbox with real tools, isolation and bounded side effects |
| P7 | Cited cross-session recall, Markdown vaults, real Graphify adapter and complete deletion propagation |
| P8 | Specialist collaboration, image/3D/transcription/speech outputs and corresponding admin setup actions |
| P9 | Clean installation, supported host/backend matrix, failure recovery, accessibility and evidenced release |

The [release matrix](../../09-VALIDATION-AND-RELEASE.md) contains **61 named scenarios**: 22 end-to-end, 18 security, nine installation/management and 12 first-provider/admin-agent gates. A gate has PASS, FAIL or BLOCKED evidence with an exact reason; its individual test cases may span several phases. All product gates remain unrun in this preparation session.

Reference release validation needs two independently enrolled physical workers, both NVIDIA and AMD text paths, two Members, an Owner, a restricted workspace, NAS transfer behavior and laptop reconnection. Every advertised installer/backend combination needs its own evidence. Actual media outputs, real provider responses and working management receipts are required for their corresponding gates.

Hybrid GPU/RAM/SSD execution, expert-profile warming and staged planning/review comparisons remain optional experiments. Distributed VRAM pooling, Kubernetes, compulsory vector infrastructure and a fully bidirectional Obsidian plugin remain outside the baseline.

## Current environment and inspection evidence

[Historical deployment inventory removed for repository privacy.]

No dependency installation, OS configuration, network enrollment, NAS connection, model execution or paid provider call was performed. Upstream packages and price/model configurations were not revalidated during this document inspection. The source list's earlier upstream checks remain inputs to P0, not newly verified compatibility claims.

Fresh package checks passed:

- Internal Markdown file links and gallery local asset links resolve; Markdown code fences are balanced.
- All 14 Mermaid blocks have corresponding rendered SVG files; all 61 SVG files parse.
- All 33 icon catalog entries resolve, and the gallery's inline drawing geometry matches the individual sources.
- All 68 listed contrast checks pass when recalculated from the actual tokens; all four CSS palette blocks agree with JSON.
- All 19 PNG exports pass signature/chunk integrity checks; the ICO contains the expected seven PNG frames from 16 through 256 px.
- All five delivered JSON files parse. The six supplied gallery/identity PNG previews were visually inspected.

These checks establish design-package integrity. They do not replace browser interaction, component accessibility, pixel decoding of every export, application tests or hardware qualification.

Evidence: [package results and original-file hashes](../../evidence/preparation/2026-09-12/inspection.json), [reproducible inspection script](../../evidence/preparation/2026-09-12/inspect_package.py), [local environment observations](../../evidence/preparation/2026-09-12/environment.json).

The next concrete build action is to preserve the source snapshot and establish the P0 toolchain/appliance feasibility proof, followed by the shared contracts and real integration stack.
