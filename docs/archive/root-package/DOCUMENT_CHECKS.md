# Specification validation

Checked on 12 September 2026. These checks validate the planning package, not an implemented Hearth application.

- All internal Markdown file links resolve within the delivered package.
- Markdown code fences are balanced; no em dashes occur in the documents.
- All fourteen current Mermaid source diagrams have rendered successfully with Mermaid CLI using headless Chrome; changed diagrams were rendered again during revision 1.2.
- The diagram gallery and architecture were visually inspected. Linear flows were arranged vertically for readable document display.
- Each of the ten implementation phases has dependencies, concrete work, verification steps and an exit gate.
- Requirements map to phase ownership and named acceptance scenarios in the validation document.
- Upstream boundaries were checked against the primary references in SOURCES.md.
- The consistency review clarified cloud labeling for new versus historical content, private conversations inside shared workspaces, MCP process credential isolation, uncertain paid retries, and private release signing.

No application, hardware, NAS, model-quality or paid-cloud acceptance gate has been run. BUILD_STATUS.md records implementation as not started. Example JSON/YAML uses placeholders and is a contract illustration, not deployable production configuration.

## Video review addendum

The linked video review introduced two Mermaid diagrams, both rendered and visually checked. Its hybrid-inference and role-cache recommendations remain proposed experiments. The full auto-generated transcript was retrieved and read; technical claims were compared with primary model/runtime sources. The archive includes the review and its SVGs. Revision 1.1 below incorporates central setup and distinct media service provisioning into the binding baseline.

## Binding revision 1.1: central installation and management

The setup contract is now part of the binding baseline. The package contains 28 Markdown documents and 12 source/SVG diagrams: ten baseline diagrams and two proposed video-review workflows. The architecture, enrollment and admin assignment diagrams were updated, and a central provisioning diagram was added. Internal file links and fences were checked again, and the revised diagrams were rendered and visually inspected.

The consistency pass replaced the manual member join-bundle path and the requirement for a separately installed Linux controller. Phase documents and C01-C09 now require cross-platform Create/Join installation, address/port-only member inputs, central recipe provisioning and configuration, browser/enrollment security, reboot/update recovery and single-head fencing. Model-cache/hybrid performance claims remain unvalidated experiments. No installer, host configuration, virtualization software or application was installed as part of this planning update.

## Binding revision 1.2: first provider and admin agent

The current package contains 29 Markdown documents and 14 source/SVG diagrams. The architecture diagram now includes the protected admin agent; two new diagrams cover the first-provider wizard and authorized management sequence. Changed/new diagrams were rendered and visually inspected, and internal links/code fences were validated again.

The consistency pass removes a NAS/local-GPU prerequisite from first-provider onboarding, brings the minimum safe cloud adapter and useful admin-management tools into P4, and distinguishes those protected tools from ordinary user/MCP traffic. A01-A12 cover real provider choices, actual setup actions, live RBAC, secure forms, scoped approvals, cloud data limits, idempotency and provider-loss recovery. The handoff, installer, UI, contracts, operations and phase gates reflect revision 1.2. These are document checks only; no application or provider acceptance test, paid call or administrative operation has been performed.
