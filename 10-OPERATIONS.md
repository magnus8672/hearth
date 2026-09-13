# Deployment and operations

## Reference installation

Use the signed Hearth installer on the first supported Windows/Linux/macOS host. Complete Create Hearth in its local first-run page. The installer manages the Linux control appliance, native supervisor, private service network, unique secrets, restricted data storage, service startup, and update lifecycle. A separate manual Linux/Compose installation is an advanced path only. [Binding installation contract](11-INSTALLATION-AND-CENTRAL-MANAGEMENT.md)

The control appliance starts with a provisional 4 CPU, 8 GiB RAM, 40 GiB local-SSD envelope, excluding model/artifact storage and the host OS. Validate available host headroom before creation. PostgreSQL stays on local storage. GPU execution uses the host-native worker and does not require VM GPU passthrough.

The local first-run page establishes the Owner and browser trust. IP-based origins work without router DNS changes; optional DNS/domain mode is configured in Hearth. Other browsers require a trusted public-root onboarding path or a configured publicly trusted domain. Configure selected private interfaces, exact permitted CIDRs and listener/firewall rules through setup; never open WAN/router forwarding or treat all RFC1918 addresses as trusted.

Use step-ca for the farm CA. Keep the root private key offline after setup and protect the issuing intermediate. The installer creates a recovery export workflow and clearly marks setup incomplete until recovery material is saved. [step-ca](https://smallstep.com/docs/step-ca/), [Caddy HTTPS](https://caddyserver.com/docs/automatic-https)

## First operational walkthrough

1. Run the installer, choose Create Hearth, establish trusted administration, create Owner/MFA and save recovery material.
2. Use the first-provider wizard to validate local-head, joined-member or OpenAI inference and its admin-tool round trip. No NAS is required; OpenAI-first needs no local GPU. Configure budget/data allowance before any paid test.
3. Choose admin-agent conversation or the dashboard. Use it to inspect real farm state and prepare one setup operation with the correct authority.
4. Add NAS through a trusted secure-input card when desired. Add members using address/port and central proof approval; no secrets or pairing proofs go into model-visible chat.
5. Apply an authorized capability/service plan and observe package installation, model transfer, configuration, start and readiness. The agent cites actual receipts rather than declaring success on submission.
6. Validate LAN Member signup and a real user request; verify a Member cannot reach the admin agent or its tools. Change node settings without local edits.
7. Assign compatible toolbox, knowledge, image/audio or approved 3D recipes through the same dashboard or protected admin-agent flow.
8. Optionally configure OpenAI, capability/price policy and budget, then enable the user's desired cloud preference.
9. Verify backup/restore, member reboot, offline configuration, control-head loss and conversation deletion.

## Worker installation and updates

Native wrappers target Windows services, Linux systemd and macOS launchd. Install the minimal agent first; no local role setup or separate Docker/Python/model installation is required. A persistent service survives logout/reboot. Local status/doctor/repair remain recovery tools, not the normal configuration surface.

Publish detached release signatures verified against a trusted distribution key separate from farm TLS keys. Platform signing/notarization is additional when credentials exist; document OS prompts honestly. Never claim platform signatures or ask users to disable endpoint security. The first installer may request OS consent for fixed service/helper operations; ordinary inference runs unprivileged.

The controller resolves approved service recipes to NodePlans, and the node automatically downloads verified dependencies, renders typed configuration, injects scoped secrets and runs probes. Models come through assignment-scoped NAS gateway transfers; members never need the NAS password. No arbitrary shell command or unapproved URL is accepted as configuration.

Updates drain affected work, stage and verify a compatible package, activate and probe it, and commit only on success. Preserve one known-good rollback image/configuration when its data-format compatibility permits. Interrupted updates resume from a durable journal. Failed upgrades and privilege limitations are visible in Hearth. Do not silently replace models, GPU drivers or firmware.

## Secrets and recovery kit

The recovery kit contains encrypted database backups, configuration revisions, owner recovery instructions, offline CA material, secret-encryption recovery key, model/runtime approval manifests, and the latest deletion ledger. Keep the recovery key separate from the NAS backup files. Model weights can be restored independently from immutable hashes; they need not be copied in every database backup.

Nightly encrypted database backup plus periodic transaction-log backup is the target. Initial recovery objectives: RPO 15 minutes for database state when WAL archiving is enabled, RTO 2 hours on a prepared replacement controller. With nightly-only backups, report RPO as 24 hours instead. Confirm objectives through a timed restore exercise.

Use the replacement installer's Move/Restore Hearth workflow, preserve farm identity, and fence/retire the old head before service resumes. Restore order: isolate new controller, restore secrets/identity and database, apply deletion ledger, validate ACLs, restore projections/catalog, renew service trust if needed, reconcile workers, run smoke tests, then allow user traffic. Do not restore into a publicly reachable unauthenticated setup state.

## Operational behavior under failure

| Failure | Expected behavior |
|---|---|
| NAS unavailable | Warm verified models continue; new downloads wait; vault projection lag displayed |
| Internet unavailable | Local requests/tools continue; cloud unavailable without repeated futile retries |
| Knowledge node unavailable | Recent-context chat continues; long-term retrieval visibly degraded |
| Toolbox unavailable | Tool jobs queue or fail with reason; no fabricated tool results |
| Worker sleeps | Lease expires, capability withdrawn, interrupted task reconciled |
| Controller unavailable | No new work; bounded active results retained until reconnect; no member auto-promotion |
| Admin inference provider unavailable | Manual admin/provider setup and durable operation status remain usable; no automatic cloud permission expansion |
| Database unavailable | No new accepted tasks or authorization-dependent side effects |
| Certificate expired/revoked | Connection rejected; admin diagnostic and safe re-enrollment path |
| Cache disk full | Stop staging before corruption; explain eviction options |
| OOM/model crash | Mark deployment failed, withdraw readiness, bounded restart policy |

## Observability

Dashboard and metrics include ready nodes/deployments, lease age, job queue depth, context size, model load time, peak VRAM, first-token latency, output rate, completed-task latency, tool errors, graph/index lag, NAS throughput, and cloud reserved/settled/uncertain spend. Record units and measurement windows. Health endpoints expose liveness separately from dependency readiness.

Use trace IDs across user request, route decision, child task, worker attempt, tool call, memory query, and provider call. Operational logs contain metadata by default; private prompts remain in authorized conversation storage. A privileged diagnostic content capture, if ever added, must be explicit, time-bounded, and visible to the owner of that content.

Audit role changes and administrative actions. Alert on repeated pairing failures, revoked identity reuse, missing backups, low disk, stale CA renewal, budget exhaustion, and repeated deployment crashes. Alerts stay in the admin interface by default; external notifications require separately configured connectors.

## Capacity and scheduling

Each user initially receives one active task and five queued tasks; the Owner can increase quotas. The scheduler rotates eligible users and gives interactive generation precedence over background graph jobs, with aging to prevent starvation. Admission limits media jobs separately from text to avoid monopolizing memory. Jobs reserve a model generation slot only during actual inference, not while waiting for tools or children.

Pinning is explicit. The system does not evict the coding worker's resident model to run an indexing job. A spare compatible worker may be assigned the same capability for availability. Present cloud eligibility separately from local redundancy.

## Upgrade and release policy

Pin dependency versions and digests, generate an SBOM, and run the full compatibility suite before updating Switchyard, Graphify, MCP SDKs, or inference engines. Use additive database migrations first; for destructive schema changes, require backup and a documented roll-forward/restore plan. Retain API protocol-major compatibility during a rolling worker update and quarantine incompatible agents rather than sending them unreadable commands.

The installer and admin dashboard expose version compatibility and support status. Maintain an explicit matrix of tested GPU/driver/engine combinations. Do not present unsupported old AMD Mac GPUs as accelerators merely because an engine has a Metal/Vulkan option.
