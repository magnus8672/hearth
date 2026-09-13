# P4: first inference provider, local models, and the admin agent

Dependency: P3 contracts and usable artifact/provider prerequisites. Outcome: the wizard verifies a chosen first provider and enables a real admin agent; local-head and joined-member model loading are supported alongside an explicit OpenAI-first path. Real hardware/NAS gates remain separately tracked.

## Build

1. Package a pinned llama.cpp engine and implement hardware/backend probes, typed launch profiles, loopback-only serving, model identity validation, stop/drain and crash handling.
2. Implement memory admission, one deployment per unique node/model/profile/runtime, readiness checks and measurement reports. Add CUDA and Vulkan runtime paths with CPU fallback clearly labeled.
3. Build durable tasks, attempt fencing, streamed worker results, cancellation, per-user queues and conversation turn serialization.
4. Persist real messages/artifacts and provide the user chat UI with capability override, source deployment information and error recovery. Build actual Ready/Busy/Failed/Offline capability states.
5. Record context/concurrency limits, peak VRAM, time to first token and output rate per tested profile.
6. Complete the central NodePlan reconciliation path: choose a text capability on a clean enrolled member, automatically install its approved engine/dependencies, render settings, stage its model and pass readiness. Changing context/resource settings centrally drains and reapplies the deployment without any local edits.
7. Implement all three first-provider choices and the real non-mutating management-tool round trip in [12](../12-ADMIN-AGENT-AND-FIRST-PROVIDER.md). Local bootstrap can use the head-local library. OpenAI-first needs no NAS/local GPU: bring the complete minimal text/tool provider adapter, secret isolation, explicit data allowance, bounded paid-test approval, price/budget reservation and uncertain-outcome handling forward from P5. No temporary unsafe cloud path is permitted.
8. Implement protected admin conversations, live RBAC, typed management facade, immutable change previews, bounded routine grants, secure input/pairing components, durable apply/status/cancel and provenance. A useful agent can inspect and apply existing setup/capability configuration without depending on P6 MCP or P7 memory.

## Prove

E03, E06, E15-E18. Complete real prompts on an NVIDIA and AMD worker. Verify full residency rather than infer it from a successfully loaded file. Cause OOM, kill the engine, sleep the laptop, cancel generation and restart the controller. Interrupted streams remain truthful and late attempts cannot overwrite results.

Two capability assignments sharing one deployment must not allocate two model copies. Waiting jobs must not exceed the configured per-user quota. Prompt cache/context from one user must not be visible to another.

Complete C02-C03 with a real local conversation and member reboot. Model provisioning and settings survive installer exit/logout. Test interrupted package activation and a failed update without losing the last safe configuration.

Run A01-A12 against available real providers and policy-faithful fixtures for failure cases. Prove one real admin request inspects a node, prepares an exact configuration/assignment change, applies under valid authority and reports measured readiness. Test cloud-first without local inference or NAS, and local-first without an OpenAI key. Missing paid-test authorization or hardware marks the respective real gate blocked, never passed by mocks.

## Exit gate

A chosen first-provider path and a real admin setup operation work with evidence; API/RBAC/secret/approval/idempotency tests pass. All three wizard paths are implemented. A cloud-first verified path may enable agentic setup before local-GPU/NAS verification; local inference and the remaining provider/host release gates stay explicit for P9. No account or NAS requirement is introduced into an otherwise local first-provider path.

Next: [P5](P5-ROUTING-AND-CLOUD.md).
