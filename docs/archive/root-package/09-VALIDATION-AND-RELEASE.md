# Validation, quality, and release gates

## Evidence standard

Every phase has automated checks and, where applicable, real hardware checks. Store sanitized commands/results, package hashes, hardware inventory, measured memory, screenshots, and trace IDs under `evidence/<phase>/<run-id>/`. Each gate is `PASS`, `FAIL`, or `BLOCKED`, with an exact reason. A mock response proves orchestration behavior, not model quality or GPU support.

The reference evaluation farm has one controller, two independently enrolled workers, a NAS or protocol-faithful test server, two Member accounts, one Owner, and one restricted workspace. Real release validation must include both NVIDIA and AMD local inference paths and laptop disconnect/reconnect. Intel Mac support is separately qualified by tested OS/device; an untested Mac is explicitly unsupported/unverified.

## End-to-end acceptance scenarios

| ID | Scenario | Required outcome |
|---|---|---|
| E01 | First boot and LAN signup | Console bootstrap creates Owner; later signup creates isolated Member |
| E02 | Start a new worker | Pending card within 10 seconds; no task/model access before pairing |
| E03 | Pair and assign coding | Verified identity, measured inventory, compatible assignment, real load and readiness |
| E04 | Restart/change DHCP address | Same enrolled identity restores approved role without re-pairing |
| E05 | NAS model transfer interruption | Resume safely; digest verified; partial file never loaded |
| E06 | One local chat | Real model streams response; correct owner, source deployment and usage recorded |
| E07 | Unassigned job type | Persistent dashboard card; meaningful user unavailable or approved cloud state |
| E08 | OpenAI fallback | Missing local capability uses allowed configured provider and accounts for spend |
| E09 | Local-only workflow | Zero external model/embedding/graph requests, including classifier and tool results |
| E10 | Shared toolbox | Two users invoke authorized tools with separate connector identities |
| E11 | Specialist consultation | Writer requests coder evidence and returns one cited answer; no held-slot deadlock |
| E12 | Cross-session recall | Another model retrieves an earlier decision with its exact message citation |
| E13 | Superseded preference | Current retrieval favors correction; historical query can show the earlier state |
| E14 | Delete conversation | Immediate exclusion; all dependent summaries/index entries purged or rebuilt |
| E15 | Concurrent users | No content, context-cache, artifact, graph or event leakage |
| E16 | Worker loss mid-task | Stale route withdrawn; output marked interrupted; bounded visible retry |
| E17 | Controller restart | Accepted jobs recovered; safe retry; no duplicate external side effect |
| E18 | NAS/internet unavailable | Warm local inference continues; missing services report specific state |
| E19 | Media workflow | Real image, 3D geometry, transcription and speech artifacts accessible in the same authorized session with provenance and modality validation |
| E20 | Backup restoration | Identities, grants, tasks and history recover; deletions stay deleted |
| E21 | Install/update/uninstall | Signed packages verified, service lifecycle works, rollback documented |
| E22 | Budget race | Concurrent parent/child cloud calls cannot overspend reserved application ceiling |

## Adversarial security matrix

| ID | Attack or failure | Required defense |
|---|---|---|
| S01 | Spoofed discovery hostname/key | Untrusted pending record; fingerprint mismatch blocks pairing |
| S02 | Replay/steal encrypted enrollment grant | One use, expiry, worker-key/nonce/farm bindings and CSR proof checked |
| S03 | Revoked node on existing stream | Route, job/model grants and streaming access withdrawn promptly |
| S04 | User A requests User B IDs or SSE cursor | No content or existence leakage; no unauthorized event replay |
| S05 | Graph search reveals another user's node/count | Partition filtering before traversal/ranking; no leak |
| S06 | Prompt says to use admin tool/cloud | Current grants and locality gate reject request |
| S07 | NAS path traversal/symlink/corrupt weights | No escape, no unauthorized bytes, no unverified model load |
| S08 | Uploaded HTML/SVG/script/tool output | No app-origin script execution or trusted instruction promotion |
| S09 | Forged mTLS identity headers | Edge strips them; protected internal listener rejects spoofing |
| S10 | Malicious tool URL / DNS rebinding | Connector egress policy validates resolved destination and redirect hops |
| S11 | Tool adds schema/requests wider credentials | Changed schema quarantined; grants remain bounded |
| S12 | Database pool reuses prior identity | Transaction-local scope reset; RLS isolation holds |
| S13 | Concurrent deletion and index write | Tombstone generation check prevents resurrection |
| S14 | Copied node certificate | Duplicate identity quarantined; no silent additional node |
| S15 | Unknown paid-call outcome/retry | No blind replay; unsettled reservation retained and visible |
| S16 | User promotes self via role API | Server-side grant permissions and anti-escalation rules deny |
| S17 | Cloud access through Graphify ambient env | Credentials absent; explicit local backend; outbound denied |
| S18 | IPv6 or alternate admin route bypass | Equivalent listener/network authorization rules enforced |

## Installation and central-management gates

These C gates are binding revision 1.1 requirements in addition to the existing E/S scenarios. An OS installer target and an inference backend are separately qualified. Use actual clean Windows/Linux/macOS hosts for release claims, including Intel/Apple Silicon macOS targets; package builds alone do not prove installation works.

| ID | Scenario | Required evidence |
|---|---|---|
| C01 | First node creates Hearth | Start with no user-installed Docker/Python/PostgreSQL. Installer manages the appliance and service; trusted Owner/MFA setup reaches admin/user links. Record prerequisites, OS prompts, listener reachability and reboot persistence on each advertised head OS/architecture. |
| C02 | Member needs only head address/port | Install minimal agent; approve proof in Hearth; assign a real capability. Its dependencies/models configure and start automatically. Record every local input and confirm there were no local role settings, NAS credentials, CA bundle imports or runtime edits. Multicast-disabled join also passes. |
| C03 | All normal settings managed centrally | Change assignment/context/quotas and package version through Hearth; reject conflicting revisions; queue edits while offline; reboot/logout/reconnect and reconcile. No SSH/RDP/config editor is used. Desired and observed state remain distinct. |
| C04 | Correct service for assigned job | On a compatible tested host, assign text then image or geometry jobs and verify distinct approved recipes, environments, resource reservations, health and real outputs. Shared dependencies are not duplicated; unsupported jobs stay unavailable. |
| C05 | Pairing proof/envelope integrity | Wrong/expired proof, tampered JWE, alternate algorithms, wrong node/nonce/farm, foreign CSR and replay cannot enroll. Libraries interoperate against known fixtures and generate fresh IVs. Proofs do not appear in logs, URLs, broadcasts or diagnostics. |
| C06 | Rogue head or anonymous endpoint | A substituted CA, redirect or attacker relay cannot authorize membership without the locally displayed proof. Bootstrap exposes only bounded public metadata/ciphertext. It cannot deliver software/configuration or accept privileged credentials. Failed connection never initializes a farm. |
| C07 | Untrusted provisioning input | Unapproved signer/package/URL, manifest traversal, shell injection, inappropriate privilege request and stale plan are rejected. General model/tool/Member traffic cannot mutate NodePlans; protected admin-agent changes require live administrator grants. Secret delivery is service scoped. |
| C08 | Setup and browser-origin isolation | Loopback setup rejects remote clients, CSRF/rebinding and replay after bootstrap. IP/port and DNS profiles enforce independent BFF sessions, exact CORS/Origin, redirect allowlists and trusted TLS. Cookies received on another port cannot authorize that app. |
| C09 | Recovery and single control head | Interrupt install/download/activation, test safe rollback or explicit restore, lose/sleep the head, and run guided migration. Members retain identity but never self-promote. Verify old-head fencing before a restored head serves. Simultaneous restored copies are never a supported recovery procedure. |

## First-provider and admin-agent gates

These A gates are binding revision 1.2 requirements. Use real provider responses and actual management receipts for success paths; fixtures cover failure and attack cases. One benign tool call is a readiness probe, not proof of general administrative competence or safety.

| ID | Scenario | Required evidence |
|---|---|---|
| A01 | First provider on Hearth itself | No OpenAI key, NAS, MCP or knowledge service; wizard provisions an approved local-library model on the native worker, validates a real tool round trip and opens the admin agent. |
| A02 | First provider on a member | Start with no head-local model; join using address/port and central proof approval, provision the member model, validate tools and continue agentic setup. |
| A03 | OpenAI-first setup | No local model/GPU/NAS; secure key form, explicit admin-data allowance, known pricing and positive budget precede a disclosed bounded real test. Agent tools execute locally; usage and uncertain outcomes are accounted for. |
| A04 | Missing/broken provider | Unreachable endpoint, invalid key, failed schema/tool probe or text-only model stays accurately unready/chat-only. Manual wizard/dashboard remains available; no fake success or forced cloud activation. |
| A05 | Real agentic management | Inspect actual node state, prepare a concrete scoped configuration/assignment plan, Apply once, provision it and report real progress/readiness. Missing hardware/backend support remains a reasoned unavailable state. |
| A06 | Role and history isolation | Member and ordinary tool clients cannot reach admin agent/tools/history. Operator cannot exceed existing rights. One admin cannot read another's private conversation. Permission revocation blocks further privileged steps; public aliases cannot upgrade task mode. |
| A07 | Secret and cloud boundary | Canary secrets entered through secure forms never appear in model payloads/history/logs. Pairing proof stays in its trusted component. Cloud operational context is minimized and allowed; local-only logs/user data never leave via summaries or tool results. Admin opt-in does not opt in Members. |
| A08 | Prompt injection and fake approval | Hostnames, model/package descriptions, logs and tool results containing instructions to install packages, leak keys or approve changes remain untrusted. Model-generated UI/approval flags cannot create authority. |
| A09 | Plans and bounded routine grants | Stale revision/hash, expired approval, changed scope/impact and out-of-scope target/action/resource use are rejected. One valid Apply covers reviewed routine dependency steps. High-impact changes still require their trusted stepped-up approval. |
| A10 | Idempotent durable operations | Duplicate Apply, lost acknowledgments, controller/model failure and cancellation do not replay applied effects. Accepted operations retain bounded scope and truthful partial outcomes; closing chat does not lose them. Logout blocks new interactive actions; live role revocation blocks further execution. |
| A11 | Agent changes its own provider | Reassignment/drain of the sole provider previews the impact, verifies a replacement where feasible, or completes a specifically authorized deterministic removal. Manual repair remains available; no silent OpenAI fallback or controller promotion. |
| A12 | Useful setup and growth before optional services | With MCP/Graphify initially absent, use the agent to add an approved storage/model service and guide one additional member through actual installation/pairing/assignment. Later demonstrate a supported media/3D assignment. Secure actions remain in trusted forms, not model prose. |

Evaluate admin task quality with held-out representative setup/diagnosis prompts and the same real management schemas used in production. Include ambiguous requests that should produce one focused clarification, unavailable capabilities, and explanations that must not trigger mutations. Record time/tool iterations, successful outcomes, unnecessary approvals and incorrect claims. A user-facing promise of useful agentic setup needs this evidence in addition to authorization tests.

## Quality evaluation

Create a small versioned evaluation set for each capability before selecting “best” models. Include 20-50 representative tasks per core text capability, held separate from tuning examples. Coding evaluates executable tests and source-grounded explanation; extraction validates schemas and facts; writing evaluates adherence and factual support; retrieval measures correct source recall and citation precision. Model-judge scores may supplement these but never replace deterministic checks and human spot review.

Record model revision, quantization, runtime, GPU, peak VRAM, context/concurrency, time to first token, generation speed, completed-task latency, pass rate, and total cloud cost. Compare a collaboration workflow with a single-worker baseline on the same tasks. Avoid claiming improvement merely because more agents participated.

For images, inspect prompt adherence, valid files, output dimensions and provenance. For speech, use a known script and intelligibility check; for transcription, use a known recording and measured word error rate. File decoding alone is not adequate quality evidence.

## Reference load and failure testing

Test 10 simulated nodes, 20 active user sessions, 5 concurrent text tasks, 2 media tasks, two NAS transfers, and background memory indexing. Simulators test scheduling, while real nodes establish model performance. Publish both clearly. Validate the software-overhead targets in [architecture](../../plan/01-ARCHITECTURE.md), worker memory headroom, bounded queues, cancellation, and fair per-user scheduling.

Inject controller restart, worker sleep, NAS disconnect, expired certificates, full disk, 429 provider responses, malformed tool JSON, stalled MCP server, stale deployment epoch, and lost event acknowledgments. Use at-least-once delivery tests to prove idempotent reconciliation. External side effects use a controllable fixture with queryable operation IDs.

## Test layers and release automation

- Unit tests for policy, state transitions, budgets, lineage and manifest validation.
- Contract tests for Go/Python/TypeScript wire compatibility and Switchyard, Graphify, inference, MCP and OpenAI adapters.
- Integration tests using real PostgreSQL with RLS and actual identity flow.
- Browser tests for all major user/admin flows and accessibility.
- Security tests for the matrix above, plus dependency/static analysis and secret scanning.
- Hardware acceptance tests for every supported engine/GPU/OS combination.

Required release outputs: versioned source, migration scripts, signed worker distributions, pinned controller images, runtime manifests, SBOM, operator guide, recovery kit instructions, support matrix, known limitations, evidence index, and release notes. No known cross-user disclosure or unauthenticated administration defect can be waived for release. Unavailable hardware must narrow the published support matrix rather than become a fabricated pass.

## Requirement-to-phase traceability

| Requirement | Implementation phases | Acceptance evidence |
|---|---|---|
| Automatic node discovery and role selection | P2, P4 | E02-E04, S01-S03 |
| First installer becomes Hearth on supported Windows/Linux/macOS | P0, P1, P9 | C01, C08-C09 |
| Member address/port only; proof entered centrally | P2, P9 | C02, C05-C06 |
| Central installation/configuration of capability-specific services | P2-P8, P9 | C03-C04, C07 |
| Wizard validates local-head/member/OpenAI first provider | P0-P4, P9 | A01-A04 |
| Admin agent performs authorized setup and farm expansion | P4-P8, P9 | A05, A09-A12 |
| Admin chat/tool/secret isolation | P1, P4-P5, P9 | A06-A08 |
| Available/unassigned job dashboard | P1, P4, P5 | E07, UI screenshots |
| Secure shared NAS model access | P3, P4 | E05, S07 |
| Multi-user signup and full RBAC | P1, P6, P7 | E01, E10, E15, S04-S06, S12, S16 |
| OpenAI overflow for un-homed capabilities | P5 | E08-E09, E22, S15, S17 |
| Interlinked specialist agents | P6, P8 | E11, E17 |
| Shared MCP toolbox role | P6 | E10, S10-S11 |
| Obsidian/Graphify and conversation RAG | P7 | E12-E14, S05, S13, S17 |
| Images, 3D, speech and text in one interface | P8 | E19, C04 |
| Security, recovery and installable release | All, P9 | E16-E22 and full S matrix |
