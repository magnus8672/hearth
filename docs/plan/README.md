# Hearth: a private, distributed AI farm

Build specification, revision 1.2, 12 September 2026. **Status: planned; no application has been implemented or deployed by this document.** Hearth is a working project name.

Hearth turns a collection of home computers into one assistant. Each enrolled computer serves selected capabilities using models that fit its hardware. A shared runtime coordinates requests, specialist consultation, MCP tools, conversation history, and topic memory. Model files live in a NAS library. An optional OpenAI backend covers capabilities without an available local worker, subject to explicit user and administrative policy.

## Start here

Give a new coding session [BUILD_HANDOFF.md](BUILD_HANDOFF.md). It contains the execution instructions, fixed decisions, repository layout, and rules for handling missing hardware or credentials. Read [Installation and central management](11-INSTALLATION-AND-CENTRAL-MANAGEMENT.md) and [First provider and admin agent](12-ADMIN-AGENT-AND-FIRST-PROVIDER.md) as binding setup contracts. Implement the phases in order. This package specifies product behavior and acceptance gates, rather than merely describing possible technologies.

| Document | Purpose |
|---|---|
| [Build handoff](BUILD_HANDOFF.md) | Copyable instruction for the implementing agent |
| [Architecture](01-ARCHITECTURE.md) | Components, deployment, decisions, boundaries, diagrams |
| [Discovery and workers](02-DISCOVERY-AND-WORKERS.md) | Automatic discovery, secure pairing, node lifecycle, placement |
| [NAS and model catalog](03-NAS-AND-MODELS.md) | Secure storage access, manifests, caching, model selection |
| [Security and RBAC](04-SECURITY-AND-RBAC.md) | Threat model, identity, permissions, isolation, cloud authorization |
| [Runtime, routing, and tools](05-RUNTIME-ROUTING-AND-TOOLS.md) | Switchyard, durable tasks, peer requests, MCP, cloud fallback |
| [Conversation and topic memory](06-MEMORY-AND-KNOWLEDGE.md) | Obsidian vaults, Graphify, retrieval, consistency, deletion |
| [Interfaces](07-INTERFACES.md) | Separate admin and user applications, screens and user flows |
| [Contracts](08-DATA-AND-API-CONTRACTS.md) | Data model, API surface, wire examples, state machines |
| [Validation](09-VALIDATION-AND-RELEASE.md) | Test scenarios, quality gates, traceability, release evidence |
| [Operations](10-OPERATIONS.md) | Installation, trust, recovery, updates, observability |
| [Installation and central management](11-INSTALLATION-AND-CENTRAL-MANAGEMENT.md) | First machine becomes Hearth; members need only its address/port; all service configuration is central |
| [First provider and admin agent](12-ADMIN-AGENT-AND-FIRST-PROVIDER.md) | Wizard connects local-head, member or OpenAI inference; an authorized admin agent then helps configure and expand the farm |
| [Sources](SOURCES.md) | Verified upstream boundaries and references |
| [Rendered diagrams](diagrams/README.md) | Twelve baseline SVG diagrams plus two proposed workflows from the video review |
| [Build status](BUILD_STATUS.md) | Honest progress ledger for future sessions |
| [Document checks](DOCUMENT_CHECKS.md) | Validation performed on this planning package |
| [Video review and proposed amendments](VIDEO-REVIEW-IH8XmxiwliQ.md) | Hybrid GPU/RAM/SSD inference and planning, execution, and review workflows; proposed changes to the baseline |

## Phased delivery

| Phase | User-visible result | Gate |
|---|---|---|
| [P0](phases/P0-FOUNDATION.md) | Reproducible development stack and validated contracts | Dependencies and interfaces proven |
| [P1](phases/P1-IDENTITY-AND-SHELLS.md) | LAN signup, private accounts, separate admin application | Authorization and isolation tests pass |
| [P2](phases/P2-DISCOVERY-AND-ENROLLMENT.md) | New machines appear for pairing and role assignment | Spoofing and revocation tests pass |
| [P3](phases/P3-NAS-AND-CATALOG.md) | NAS library browsed and assigned weights securely staged | Corruption, traversal, and access tests pass |
| [P4](phases/P4-LOCAL-INFERENCE.md) | First-provider wizard and a working admin agent; local inference readiness | Real provider/tool round trip and authorized setup action; remaining hardware/provider gates tracked |
| [P5](phases/P5-ROUTING-AND-CLOUD.md) | Job dashboard, routing, and controlled OpenAI overflow | Local-only and budget enforcement pass |
| [P6](phases/P6-SHARED-TOOLS.md) | Shared MCP toolbox with per-user execution rights | Tools cannot expand the caller's authority |
| [P7](phases/P7-CONVERSATION-MEMORY.md) | Conversations and topic memory retrieved across sessions | Retrieval, provenance, deletion, ACL tests pass |
| [P8](phases/P8-COLLABORATION-AND-MEDIA.md) | Specialists consult each other and return media in one session | Workflow and deadlock recovery tests pass |
| [P9](phases/P9-HARDENING-AND-RELEASE.md) | Installable farm with tested recovery and operating guide | End-to-end release checklist complete |

## Binding product requirements

- A user can sign up from an allowed LAN without an administrator creating their account. Signup grants a private personal workspace and the Member role, never farm administration.
- The first supported Windows/Linux/macOS installation becomes the Hearth control node through its local setup page.
- A deterministic wizard connects the first inference provider: a model on Hearth, a model on a joined member, or OpenAI. NAS, MCP and knowledge services are not prerequisites for this step.
- After a real provider/tool protocol check, administrators can choose conversational setup through an admin agent. It inspects actual farm state and applies authorized management changes; manual administration remains available without inference.
- A member installer requires only the Hearth address and port; the administrator approves its displayed proof in Hearth. No join bundle or role configuration is entered on the member.
- An administrator assigns job types centrally. Hearth installs their approved runtime dependencies, stages models, applies settings, starts services, and registers readiness. Returning nodes restore approved assignments automatically.
- Every enabled job type has a permanent dashboard card. An unassigned or unavailable job remains visible with a clear reason and next action.
- Approved workers can fetch assigned NAS model artifacts without receiving broad NAS credentials.
- A model assignment becomes routable only after compatibility, memory, loading, and readiness checks.
- Specialists can ask other specialists for bounded supporting work using the broker. Users retain a single conversation and a visible activity trail.
- An assigned toolbox node hosts MCP servers. A separately assignable knowledge role maintains topic graphs and vault projections. Roles may share a machine.
- Conversation history and topic knowledge are user/workspace scoped, inspectable in Markdown, and retrievable through the farm. Graphify is a derived index adapter, with a local execution path.
- OpenAI fallback is supported for eligible missing capabilities. It requires provider configuration, a positive budget, an administrator policy, and the user's standing choice to allow cloud use. Local-only data stays local throughout a workflow.
- Security controls are part of each phase. Administrative convenience never grants a discovered node, a model, or a retrieved document authority.

## Deliberate defaults

One logical control head created by the first installer, a managed Linux control appliance on supported Windows/Linux/macOS hosts, one PostgreSQL instance on local SSD, native workers, one NAS gateway, and separate browser origins for users and administrators. No Kubernetes, distributed VRAM pooling, compulsory vector database, or MoE pruning is required for the first release. These are scope decisions for a home farm, not judgments about those technologies.

Each deployment must measure its available GPU memory and backend support. Hardware labels are inventory hints, not validated specifications. Older machines can serve tools, memory, storage, or CPU inference without GPU acceleration.

See [BUILD_STATUS.md](BUILD_STATUS.md) for what has actually been built. All Mermaid diagrams in this package are Markdown source diagrams and should render in GitHub, Obsidian, or another Mermaid-capable viewer.
