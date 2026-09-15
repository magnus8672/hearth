# Data and API contracts

These are implementation contracts for Hearth v1. They are not claims that endpoints already exist. Generate OpenAPI/JSON Schema from typed definitions, commit the generated artifacts, and validate examples and client compatibility in CI.

## Common conventions

Use UUIDs for entity IDs, UTC RFC3339 timestamps, bytes for storage/memory, integer minor units for configured currency budgets, and explicit schema versions. Every event includes `event_id`, `event_type`, `occurred_at`, `aggregate_id`, `aggregate_version`, and `trace_id`. User-visible events never contain secrets or private content outside the authenticated scope.

Mutation requests use idempotency keys and optimistic revision preconditions where appropriate. Idempotency keys are scoped to principal + endpoint + canonical request digest; reuse with a different body returns conflict. Return typed errors containing code, safe message, retryable flag, and trace ID. Use 401 for missing identity, 403 for prohibited actions, 404 for resources whose existence must be concealed, 409 for revision conflicts, 422 for invalid schema, and 429 for quotas/rate limits.

Default pagination is 50, maximum 200. Upload/body limits are endpoint specific, not unlimited. Use signed cursor contents or opaque server cursors bound to scope. Logs redact authorization headers and secret fields.

## Principal and scope propagation

```json
{
  "principal_id": "uuid",
  "workspace_id": "uuid",
  "task_id": "uuid",
  "parent_task_id": null,
  "authorization_version": 12,
  "resource_grant_ids": ["uuid"],
  "locality": "local_only",
  "remaining_budget_id": "uuid",
  "expires_at": "2026-09-12T20:00:00Z"
}
```

The controller constructs and signs short-lived audience-bound job grants using a maintained JOSE library. A worker validates issuer, audience, expiry, membership, task attempt, and grant revision. This envelope is never accepted as an unsigned user/model assertion. Grants authorize a bounded task, not arbitrary tools or all workspace data. A context assembled from several resources is restricted to principals allowed to read all contributing private sources; it does not inherit the broadest ACL.

## Core entities

| Entity | Important fields and constraints |
|---|---|
| User | OIDC subject unique per issuer, state, locale, cloud preference, quota |
| Role / Permission / Grant | Scope, catalog permission IDs, grantor, revision, expiry |
| Workspace / Membership | Owner, visibility policy, locality, member role, ACL version |
| NodeObservation | Ephemeral discovery ID, interface, untrusted label/key fingerprint, expiry |
| Node | Farm ID, key identity, certificate serial, trust pool, state, epoch, lease |
| NodeInventory | Versioned measured OS/GPU/runtime/cache/power inventory |
| Capability | Stable ID, version, schemas, modalities, recipe, minimum features, quality suite |
| Assignment | Node, capability, desired profile/deployment, desired revision, pin policy |
| ModelArtifact | Immutable model/revision, manifest, license, file hashes, approval |
| RuntimePackage | Engine/version/platform/digest, signature, approval, launch schema |
| Deployment | Unique node/model/profile/runtime combination, observed state, metrics, lease |
| ProviderRoute | Capability, provider/model ID, scope, price revision, enabled state |
| Conversation / Message | Owner/workspace, ordered sequence, role, status, content references, locality |
| Task / Attempt | Parent, capability, state, constraints, deadline, lease/fence, route decision |
| ToolServer / Tool | Package/schema digest, execution class, egress, connector scope, approval |
| ToolInvocation | Task/caller, args artifact, grant, idempotency key, execution/result state |
| Artifact | Owner/workspace, digest, content type, size, lineage, locality, retention |
| KnowledgeRecord / Edge | Partition, subject, assertion/relation, evidence, source spans, supersession |
| Projection / IndexJob | Partition, source generation, output version, lag, status |
| Deletion | Source IDs, tombstone generation, cleanup receipts, backup horizon |
| Budget / Reservation / Usage | Scope, ceiling, price revision, reserved/settled/uncertain amounts |
| AuditEvent / Outbox | Actor, safe metadata, aggregate revision, delivery state |

Uniqueness prevents duplicate identity grants, duplicate deployment loads, repeated message sequence numbers, and repeated task side effects under the same invocation key. Foreign keys include or validate partition relationships, so an artifact reference cannot silently cross workspace boundaries.

## API surface

| Group | Initial endpoints | Authorization |
|---|---|---|
| Identity | `GET /api/v1/session`, login/callback/logout BFF routes | Validated OIDC or existing session |
| User capabilities | `GET /api/v1/capabilities` | Caller-filtered availability |
| Conversations | `POST/GET /api/v1/conversations`, `GET/DELETE /api/v1/conversations/{id}` | Owner or explicit sharing grant |
| Messages/tasks | `POST /api/v1/conversations/{id}/messages`, `GET /api/v1/tasks/{id}`, `POST /api/v1/tasks/{id}/cancel` | Authorized conversation/task |
| Activity | `GET /api/v1/tasks/{id}/events` | Authenticated SSE, replay cursor, rechecked scope |
| Artifacts | `POST /api/v1/artifacts/uploads`, `GET /api/v1/artifacts/{id}/content` | Bounded task/user grant |
| Memory | `POST /api/v1/memory/search`, `PATCH /api/v1/memory/{id}`, `POST /api/v1/memory/exports` | Authorized partitions and revisions |
| Admin discovery | `GET /api/v1/admin/discoveries`, `POST /api/v1/admin/enrollments` | Node enrollment permission + step-up |
| Admin nodes | `GET /api/v1/admin/nodes`, `POST /api/v1/admin/nodes/{id}/revoke` | Operational or privileged node permission |
| Assignments | `PUT /api/v1/admin/assignments/{id}` | Assignment permission, revision precondition |
| Catalog/storage | `/api/v1/admin/models`, `/storage/connectors`, `/models/{id}/approve` | Curator/storage permissions |
| Tools/roles/cloud | `/api/v1/admin/tools`, `/roles`, `/users`, `/providers`, `/budgets` | Action-specific permissions |
| Anonymous bootstrap | `POST /bootstrap/v1/pending`, `GET /bootstrap/v1/pending/{attempt_id}/grant` | Public bounded metadata/JWE ciphertext only; no configuration or execution authority |
| Enrollment approval | `POST /api/v1/admin/enrollment/{attempt_id}/approve` | Stepped-up admin session and installer proof |
| Enrollment | `POST /node/v1/enroll` | Verified TLS using envelope-provided trust, one-use key/nonce-bound token + CSR |
| Central node plan | `GET/PUT /api/v1/admin/nodes/{id}/plan`, `POST /api/v1/admin/nodes/{id}/plan/preview` | Scoped admin policy; expected revision on mutation |
| Runtime packages | `GET /node/v1/package-blobs/{digest}` | mTLS and exact approved NodePlan dependency authorization |
| Worker control | `/node/v1/heartbeat`, `/commands`, `/commands/{id}/ack`, `/attempts/{id}/events` | Mutual TLS + active node/task authorization |
| Models | `GET /node/v1/model-blobs/{digest}` | Mutual TLS + exact assignment grant; range supported |
| Internal tools | `POST /internal/v1/tool-invocations` | Runtime identity + audience-bound task grant |

All abbreviated admin group paths are under `/api/v1/admin`; generate exact paths in P0 and use them consistently in clients. Do not ship wildcard administrative endpoints accepting arbitrary operations. CSR enrollment is the sole narrow exception on `/node/v1`; `/bootstrap/v1` is a separate minimal unauthenticated surface that cannot serve packages, models, inventory, commands or configuration.

Provide `GET /v1/models` and `POST /v1/chat/completions` as an optional authenticated compatibility surface with an explicitly tested subset: text messages, streaming, and supported function-call schemas. Advertise capability aliases, not hidden unauthorized deployments. These calls are inference only; client-supplied functions are returned as tool requests to that client and do not become executable farm tools. The full agent workflow uses Hearth task APIs. OpenAI-as-backend is mandatory; complete emulation of every OpenAI API is not.

## Capability availability response

```json
{
  "capability_id": "image.generate",
  "assignment_state": "unassigned",
  "local_state": "unavailable",
  "local_deployment_ids": [],
  "cloud_configured": true,
  "cloud_allowed_for_caller": false,
  "effective_state": "unavailable",
  "reason": "user_local_only",
  "available_actions": ["queue_local", "change_cloud_preference"]
}
```

Actions are filtered by authorization. A Member never receives `assign_node`. Admin availability has an operational view and does not imply any user's cloud eligibility.

## Worker transport

Workers initiate outbound HTTPS long polls for commands, maximum 25 seconds, over mTLS. Heartbeats and result events use separate requests so a waiting poll cannot block progress. Stream result events in bounded batches, initially 64 KiB or 100 ms, with monotonic sequence numbers and replay acknowledgments. Large binary media goes through artifact upload endpoints. An optional WebSocket transport can later implement the same message contracts.

Command delivery is at least once. Persist command IDs before acknowledging. Results include attempt fencing tokens; late output from an expired attempt is rejected. Heartbeats carry a bounded active-attempt list and observed desired-state revision. The controller never dispatches arbitrary shell scripts through this channel.

## Turn ordering and context consistency

Serialize mutating agent turns per conversation. A new user message during an active task becomes an ordered steering event, or a queued next turn according to the client action. Do not run two uncoordinated writers against the same conversation head. Artifacts and memory records use revision preconditions; independent tasks can run concurrently in separate branches of the task tree.

## Example task events

```json
{
  "schema_version": 1,
  "event_type": "specialist.started",
  "event_id": "uuid",
  "aggregate_id": "task-uuid",
  "aggregate_version": 7,
  "occurred_at": "2026-09-12T19:30:00Z",
  "trace_id": "uuid",
  "data": {"capability": "code.explain", "label": "Inspecting implementation"}
}
```

Other required event types: `task.accepted`, `task.queued`, `route.selected`, `model.loading`, `response.delta`, `tool.requested`, `tool.completed`, `approval.required`, `artifact.created`, `memory.sources_selected`, `task.interrupted`, `task.completed`, `task.failed`, and `task.cancelled`. Public events describe actions and outcomes, not private chain-of-thought.

## Central provisioning entities and contracts

The protected admin-agent facade may prepare/apply these operations only through the current administrator's bounded execution grant, as specified in [12](../../plan/12-ADMIN-AGENT-AND-FIRST-PROVIDER.md). Ordinary model/task/MCP traffic still has no NodePlan mutation authority.

Revision 1.1 adds `ServiceRecipe` (immutable signed manifest, platform selectors, dependency DAG, typed settings, entrypoint ID, readiness and upgrade policy), `NodePlan` (farm/node/controller generation, expected/desired revision, service instances, dependency hashes, reservations, secret references and drain policy), `ServiceInstance` (node, recipe revision, deployment mapping, observed state and health), and `EnrollmentAttempt` (public node identity, nonce, expiry, state and encrypted grant). Never store/log raw pairing proof in ordinary records.

An assignment refers to a service instance/deployment supplied by the desired plan. Several capabilities may reuse one instance. Service state is independent of node heartbeat and LLM deployment state. Use the full provisioning state enumeration in [11](../../plan/11-INSTALLATION-AND-CENTRAL-MANAGEMENT.md).

Admin plan preview is side-effect-free apart from bounded catalog/resource reads. Apply uses compare-and-swap on the prior revision, transactional reservations and an outbox command. Command `reconcile_plan` carries a signed, schema-validated plan reference/hash and epoch; the worker fetches the authenticated plan, rejects stale/foreign generations, journals progress and reports observed revision. Node credentials authorize only its own plans and exact package dependencies.

Receipts expose per-stage bytes/progress and a typed reason such as `unsupported_recipe_platform`, `insufficient_host_ram`, `package_signature_invalid`, `local_privilege_required`, `driver_restart_required`, `configuration_conflict` or `control_head_unreachable`. Configuration includes secret references, not plaintext values in events. Newer desired revisions cannot blindly interrupt irreversible migrations; their service recipe defines safe drain/rollback behavior.

The enrollment wire schema and fixed JWE algorithm policy are in [11](../../plan/11-INSTALLATION-AND-CENTRAL-MANAGEMENT.md). Reject alternate algorithms, unknown security headers, decompression, oversized bodies, replay, mismatched node/nonce/farm bindings and redirect-supplied authorities. A bootstrap response is never a general command envelope.

## First-provider and admin-agent contracts

Add `ProviderBootstrap`, `AdminConversation`, `AdminRun`, `AdminChangeSet`, `AdminExecutionGrant` and `AdminOperation` with farm/principal scope and schema versions. Readiness is separately recorded as configured, inference-verified and admin-agent-ready. Provider probe evidence identifies the actual endpoint/deployment, model/profile and non-mutating tool round trip. A mock cannot promote production readiness.

Use `/api/v1/admin/provider-bootstrap` and its test/status subroutes, plus `/api/v1/admin/assistant/{conversations,runs,changes,operations,grants}` with exact schemas in P0. Run events and histories are author scoped with live admin authorization. Change preparation is side-effect-free except bounded operational reads; Apply requires the immutable change hash, idempotency key, expected revisions and a server-held current grant. A secure-form receipt is a scoped reference, never a credential value.

Model tool schemas omit administrator IDs, execution tokens and approval flags. The facade checks the principal/run server-side and emits redacted receipts. Accepted operations use their own narrowly bounded grant until their deadline; logout prevents new conversational actions, while cancellation or live permission revocation prevents further privileged execution. Malformed arguments, stale previews, expired grants and duplicate Apply are explicit contract fixtures. These management tools are absent from public capability and MCP discovery APIs.
