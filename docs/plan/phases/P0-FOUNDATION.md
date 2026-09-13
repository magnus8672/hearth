# P0: foundation and integration contracts

Dependency: none. Outcome: a reproducible development stack with real authorization/data contracts and honest adapter boundaries.

## Build

1. Create the repository layout in [handoff](../BUILD_HANDOFF.md), development commands, CI, dependency lockfiles, schema generation, and Compose services for PostgreSQL, identity, edge, and API.
2. Implement core IDs, scope/locality types, error envelope, event envelope, typed capability definitions, and database migrations. Seed capability definitions and built-in permission names; do not seed production users or passwords.
3. Define adapters for Switchyard selection, inference load/generate/stop, NAS fetch, MCP tools, Graphify indexing, and OpenAI calls. Implement deterministic fixtures behind an explicit test configuration.
4. Run narrow compatibility probes against the pinned Switchyard and Graphify packages. Verify actual supported entry points and generate ADRs; do not treat examples in this plan as upstream APIs.
5. Establish package signatures/digests and a deny-by-default production configuration. Provide one command to launch fixtures and one to run the integration suite.
6. Define signed service recipes, NodePlan/ServiceInstance schemas, dependency graphs, privileged-helper boundaries, and the cross-platform installer/supervisor and managed control-appliance contract in [11](../11-INSTALLATION-AND-CENTRAL-MANAGEMENT.md). Lock supported OS versions and probe QEMU/hypervisor and x86-64/arm64 guest-image dependencies; manual VM setup cannot substitute for the target experience.
7. Prove JWE enrollment-envelope interoperability with maintained Go/Python libraries, fixed algorithms and binding/tamper fixtures. Validate the default IP/port-origin BFF design and browser trust bootstrap before shipping enrollment or setup.

## Prove

Revision 1.2 adds first-provider wizard, protected admin-tool, change-set/grant and operation schemas from [12](../12-ADMIN-AGENT-AND-FIRST-PROVIDER.md). Define all three provider paths, schema-constrained tool probes, secure-input receipts, admin/user namespace separation and A01-A12 fixtures. Plan the safe minimum cloud gateway/budget implementation in P4 so OpenAI-first setup has no local-GPU dependency. Add the optional head-local model library behind the existing storage interface.

- A fresh checkout starts the test stack without manual source edits.
- Python, Go and TypeScript validate the same contract fixtures; invalid versions and unknown security fields fail.
- Migrations apply to an empty real database and upgrade a prior fixture snapshot.
- Real pinned adapter packages load and return expected typed results in bounded tests; no paid provider request is required.
- Test-mode shortcuts cannot start under the production profile.
- A reference managed appliance boots from a clean host through the supervisor and starts the real control stack; other platform probes remain explicit tracked gates. Anonymous enrollment clients cannot call authenticated configuration or package APIs.

## Exit gate

Commit lockfiles, generated schemas, initial ADRs, CI configuration, dependency evidence, and a populated status ledger. All P0 contract tests pass. Missing network/package access is recorded as a blocked integration, never replaced with a claim of compatibility.

Next: [P1](P1-IDENTITY-AND-SHELLS.md).
