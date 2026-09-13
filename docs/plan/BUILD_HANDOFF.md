# Build handoff

## Instruction for the next session

> Build Hearth from this specification. Read README.md, this file, the architecture, security, contract, installation/central-management, and first-provider/admin-agent documents, then implement the phases in order. Use the documented defaults and make routine implementation decisions autonomously. Build real functionality, run each phase's acceptance checks, and maintain BUILD_STATUS.md and an evidence directory. Do not turn configuration choices into a questionnaire. Treat missing secrets, unreachable hardware, and unavailable provider accounts as deployment inputs; complete independent implementation and report the exact blocked verification. Do not label mocks as real integrations or claim the farm is complete while required acceptance gates remain unverified.

## Scope and authority

This package authorizes a future build when the user asks to build it. This planning session has not authorized purchases, paid API calls, account creation at external providers, firewall changes on other machines, or deployment to unmentioned hosts. During the build, honor the user's active authorization and existing repository instructions. Implement setup forms for actual environment inputs instead of asking the user to dictate framework internals.

If started in an empty directory, use that directory as the repository. If started inside an unrelated project, create a `hearth/` subdirectory and leave unrelated code untouched. Copy this package into `docs/plan/`; do not modify the original delivered package while implementing. Do not automatically create a separate Codex task.

## Fixed engineering choices

| Area | Decision |
|---|---|
| Controller | Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2, Alembic; modular application with separately runnable services |
| Admin agent | Protected control-plane module using typed management tools, live administrator permissions and durable change sets; usable after first-provider setup without MCP or Graphify |
| Worker | Go native service, Windows/Linux/macOS builds; typed versioned HTTPS control protocol |
| Web applications | TypeScript, React, Vite, accessible component primitives, shared design system; distinct admin/user bundles |
| Database | PostgreSQL 18, local SSD, transactional outbox and leased jobs; no broker required initially |
| Authentication | Keycloak through OIDC authorization code + PKCE; backend-for-frontend sessions |
| TLS | Caddy edge and step-ca for a farm CA, separate listener for worker mutual TLS |
| Routing | Pinned NeMo Switchyard library behind a Hearth adapter; Hearth enforces policy and performs dispatch |
| Text inference | Pinned llama.cpp runtime packages; CUDA or Vulkan as verified; CPU fallback explicitly labeled |
| Media | Approved service recipes: images via pinned Diffusers, transcription via whisper.cpp, speech via pinned Kokoro ONNX; local 3D adapter with validated GLB output and separately approved model/dependencies |
| Knowledge | PostgreSQL full-text search and provenance tables, scoped Obsidian Markdown vaults, isolated Graphify adapter |
| NAS | Linux storage gateway mounts a dedicated model share read-only and serves authenticated, resumable model transfers |
| Packaging | Signed cross-platform Hearth installers and native supervisors; automatically managed Linux control appliance with pinned QEMU; Compose inside the appliance |
| Observability | Structured redacted logs, metrics, task activity events, security audit records |
| Tests | pytest, Go tests, Vitest, Playwright, real PostgreSQL integration environment, adversarial fixtures |

Resolve exact compatible versions at P0 and commit lockfiles, container digests, and binary hashes. Version numbers above are intentional major/runtime choices, not assertions that arbitrary latest packages interoperate. Prefer a current security-patched compatible release. Any necessary replacement gets a short ADR explaining evidence, consequences, and compatibility; it does not require reopening the whole design with the user.

Do not invent fixed GPU compatibility based on marketing names. A worker must prove its runtime and hardware combination before accepting an assignment. Do not require Docker for native laptop text inference. The first supported Windows/Linux/macOS host becomes the Hearth Node. Its installer manages the Linux control appliance; users do not set up a VM or Compose. Member GPU runtimes stay native. [Installation and central management](11-INSTALLATION-AND-CENTRAL-MANAGEMENT.md) fixes the host matrix, first-run flow, enrollment, and recipe lifecycle.

## Proposed repository

```text
apps/
  admin-web/
  user-web/
services/
  api/                 # auth sessions, RBAC, admin/user APIs
  orchestrator/        # task state machine, broker, routing, scheduling
  admin-agent/         # protected management facade, conversations, plans and grants
  storage-gateway/    # NAS ingestion and bounded artifact/model delivery
  knowledge/          # vault projections, retrieval, graph jobs
  cloud-gateway/      # sole model-provider credential and egress boundary
  toolbox/            # MCP host, tool policy and isolated processes
worker/
  cmd/hearth/          # public installer/service/status entry point
  cmd/hearth-worker/   # internal worker process
  internal/           # identity, enrollment, inventory, runtime adapters
packages/
  contracts/          # OpenAPI, JSON Schema, generated Go/TS clients
  ui/
  python-common/
adapters/
  switchyard/
  inference/
  graphify/
  mcp/
deploy/
  compose/
  worker-packages/
  bootstrap/
  appliance/          # reproducible x86-64/arm64 control images
  service-recipes/     # signed typed dependency and provisioning manifests
tests/
  integration/
  security/
  e2e/
  fixtures/
docs/
  plan/
  adr/
  operations/
evidence/
```

Services may share Python packages and the same development image. Keep the cloud and tool boundaries separately deployable so process isolation and network policy are enforceable. Go workers may launch a pinned Python service package for toolbox, knowledge, or media roles. That package must use the same enrollment and job identity, not a new unauthenticated LAN endpoint.

## Execution discipline

1. Inspect the repository and instruction files; write the initial status and implementation ADRs.
2. Establish contracts and a runnable local integration stack in P0. Add minimal vertical slices before expansive UI polish.
3. Finish the phase's negative tests alongside its successful flow. Security tests are release requirements, not optional follow-up work.
4. Keep sample records under an explicitly marked Demo mode. Never show sample nodes as discovered hardware.
5. Record commands, outcomes, versions, screenshots, and hardware measurements with secrets removed.
6. Continue to the next runnable task when one integration awaits real hardware. Preserve the blocked gate and its exact reason.
7. At a context or session boundary, update status, decisions, known failures, and the next concrete task. A later session should resume without reconstructing history.

## Necessary setup inputs, collected by the product

The first-node wizard establishes hostname/IP, trusted LAN ranges, Owner/MFA and one inference provider. Choose local-head, joined-member or OpenAI through the complete paths in [12](12-ADMIN-AGENT-AND-FIRST-PROVIDER.md). Local bootstrap can use an approved local library; NAS is optional until configured later. Depending on the path, collect actual model/license approval, member proof through secure central UI, or an OpenAI key and positive bounded budget through a secure form. Supply defaults and validation; never fabricate secrets or silently accept untrusted certificates. NAS, MCP, knowledge and additional nodes can then be set up using the admin agent or dashboard.

Cloud configuration can remain disabled while everything local is built and tested. Unknown NAS credentials do not block a fixture-backed storage adapter and its security tests. Unavailable Macs do not block packaging or protocol tests, but real Mac compatibility remains unverified.

## Completion definition

Complete means every required P0-P9 gate is supported by evidence, the user can install the controller and join supported workers, the first-provider wizard enables a real admin agent that performs authorized setup actions, two users remain isolated, models load from the NAS through authorized transfers, local and approved cloud requests complete, tools and specialist handoffs work, history is retrievable with citations, and backup/restore and node-loss scenarios pass. A documented unsupported device is acceptable; quietly advertising it as working is not.

For every delivered supported modality, at least one real local implementation must pass its contract and quality tests. Text, image generation, 3D generation, transcription, and speech are the initial modalities. Choose and record the 3D backend in a P0 feasibility ADR from current primary sources, available hardware, license terms and the GLB contract; this is an implementation selection, not a request for a user questionnaire. Cloud tests can be marked externally blocked until credentials and a paid test budget are provided, but that is not a completed cloud gate.

## Binding setup and admin-agent rules

Revision 1.2 retains these setup rules and adds [12](12-ADMIN-AGENT-AND-FIRST-PROVIDER.md). Implement the useful admin agent and all three wizard choices in P4. Bring the safe minimal cloud gateway and its budget/locality safeguards forward from P5. Do not require a local GPU, NAS, MCP or shared knowledge merely to use the OpenAI-first setup path. Missing external credentials can block real verification, but not independent implementation. A01-A12 are required release gates.

A member supplies only the control-head address and port. All runtime/model/toolbox/media configuration belongs in the Hearth admin UI. Capability assignment provisions approved packages and dependencies automatically through versioned NodePlans, never arbitrary remote shell. Use the same installer product to create or join a farm; a failed connection never creates a new head. See [11](11-INSTALLATION-AND-CENTRAL-MANAGEMENT.md) and C01-C09 in [validation](09-VALIDATION-AND-RELEASE.md). The video review remains a separate proposed optimization; it does not weaken these binding installation requirements.
