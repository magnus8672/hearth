# P5: Switchyard routing, capability coverage, and OpenAI overflow

Dependency: P4. Outcome: the interface uses available local specialists and authorized cloud capability fallback.

## Build

Use the provisioning states and compatible recipe/model defaults from [11](../../../plan/11-INSTALLATION-AND-CENTRAL-MANAGEMENT.md). Central assignment must install/configure the selected service before it becomes an eligible route. C03-C04 extend dashboard/reassignment validation.

1. Integrate the pinned Switchyard adapter with policy-filtered candidates and deterministic fallback. Add session affinity, per-call route provenance and fair queue selection.
2. Complete dashboard coverage for local assignments, absent/failed/warming deployments, and separately configured cloud routes. Add model/capability selection from measured evidence.
3. Extend the safe minimal OpenAI text/tool gateway delivered in P4: complete provider management, allowed model routing, versioned pricing and Responses streaming across ordinary and admin workflows. Keep state local and apply supported storage controls.
4. Complete standing per-user cloud preference and workspace/source policy across routing, using the transactional cost reservation, reconciliation and unknown-outcome safeguards already required by P4's first-provider path. Admin cloud consent never enables cloud use for Members.
5. Add the limited external chat compatibility API and document its supported fields. Cloud setup supplies actual model IDs and secrets without hardcoding a commercial account into source.
6. Extend the admin agent's multi-provider placement and backup-provider setup actions with the same immutable previews, live grants and redacted result checks. Its internal tools remain inaccessible to public chat clients and ordinary specialist handoffs.

## Prove

E07-E09, E22 and S06, S15, S17. Simulated providers cover rate limits, network failures and price races. Real OpenAI integration requires a configured key and authorized test budget; preserve a blocked gate until these exist. Verify that unassigned capability fallback works, while busy local inference queues unless overflow-on-delay was explicitly enabled.

Capture denied-egress evidence for a local-only request containing retrieved history. Classifier calls and retries cannot leak its text. Revoking user cloud permission invalidates pending dispatch, and unknown prices fail closed.

## Exit gate

Policy and budget suites pass, Switchyard selects actual local endpoints, and configured OpenAI behavior is either verified or precisely externally blocked. No cloud activation is implied merely by installing the gateway.

Next: [P6](../../../plan/phases/P6-SHARED-TOOLS.md).
