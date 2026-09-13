# Security, identity, RBAC, and trust

## Security objectives and limits

Assume a curious or malicious LAN client, a spoofing discovery peer, malicious uploaded content, an untrusted model/tool response, an accidentally misconfigured NAS, and a compromised enrolled worker. Prevent unauthorized enrollment, access across users/workspaces, arbitrary tool execution, silent cloud export, and credential propagation.

A worker handling plaintext inference can observe the prompt assigned to it. Only a node approved by the Owner or a delegated FarmAdmin may process private data; expose node trust pools in placement policy. Root access to the controller, its database, or an authorized inference host is outside application-level confidentiality guarantees. Normal admin roles do not gain private-content read permissions, but the software must not promise protection from the machine's root operator. A worker is not allowed to enroll merely because any LAN user runs it.

## Network boundaries

| Boundary | Allowed traffic | Enforcement |
|---|---|---|
| LAN browsers to user/admin/identity origins | HTTPS 8444/8443/8445 in IP mode, or 443 with configured DNS | Trusted certificate, sessions, CSRF, RBAC, LAN admission policy |
| Discovery on selected interfaces | mDNS UDP 5353 | Untrusted bounded metadata only |
| Pending enrollment to head | Narrow 8443 bootstrap route, outbound initiated | Public bounded metadata and JWE ciphertext only; no task/configuration authority |
| Enrolled workers to controller | TLS 8443, outbound initiated | Mutual TLS, current membership, scoped messages |
| Workers to storage gateway | Authenticated HTTPS | Node certificate plus assignment/artifact authorization |
| Gateway to NAS | SMB 445 with encryption/signing | Dedicated read-only model identity, host allowlist |
| Internal services | Private container network or mTLS across hosts | Service identities; database roles; no public DB ports |
| Cloud gateway to provider | HTTPS 443 to approved provider | Server-side credentials, egress and data policy |
| Toolbox to external services | Denied unless connector explicitly allows | Per-tool egress destinations and per-user credentials |

If an edge terminates worker mTLS, it strips client-supplied identity headers and forwards verified identity only over a protected internal hop. Public clients cannot reach that internal listener. LAN addresses are an admission condition, never identity. Respect IPv4 and IPv6; a private IPv4 firewall rule does not protect an open IPv6 listener. No WAN port forwarding is configured by Hearth.

## Signup, login, and bootstrap

Follow the first-node bootstrap and application-scoped member trust flow in [11](11-INSTALLATION-AND-CENTRAL-MANAGEMENT.md). Use Keycloak OIDC code flow with PKCE. User and admin web applications use distinct confidential BFF clients and host-only Secure, HttpOnly cookies. In IP/port mode, cookies are not isolated by port: use distinct names, independent sessions, exact-origin CORS/CSRF and per-BFF validation. Validate issuer, audience, signature, nonce/state, redirect URI, and session lifetime. Store refresh credentials server-side. API keys are generated high-entropy tokens stored as hashes, scoped to a user/workspace and optional capability set, expirable and revocable.

First owner creation is authorized by a random, one-use bootstrap secret displayed only on the controller console. It is never a race in which the first LAN signup becomes owner. After owner setup, enable self-registration from explicitly configured LAN ranges. New accounts immediately receive Member rights to their private workspace and conservative local quotas; no email service is required. Configure registration throttles and bounded password attempts. Keycloak handles password hashing and MFA. Farm administrators must enroll MFA; recovery uses one-use recovery material held by the owner.

Default session lifetime: user 12 hours with 60-minute idle expiration; admin 4 hours with 15-minute idle expiration. Step-up authentication is required for enrollment approval, role elevation, secret changes, and recovery changes. Logout/revocation invalidates application sessions and long-lived streams. Use mature OIDC integrations rather than implementing authentication protocols. [Keycloak OIDC](https://www.keycloak.org/securing-apps/oidc-layers)

## RBAC and resource scopes

Authorization is `principal + action + resource + policy`. Roles grant named permissions; resource ownership and workspace membership further constrain them. Every API, stream, worker result, artifact access, retrieval query, and tool invocation checks authorization. Deny by default. The design follows the principle of validating permissions on each request. [OWASP authorization guidance](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html)

| Role | Permissions | Exclusions |
|---|---|---|
| Owner | Configure farm, assign admin roles, recovery, security policy and billing ceilings | No automatic UI access to another user's private content |
| FarmAdmin | Enroll/revoke nodes, assign capabilities, approve models/tools, configure authorized providers | Cannot grant Owner or exceed owner spending ceiling; no default private-content read |
| Operator | Inspect operational health, drain/restart approved deployments, retry safe jobs | Cannot approve nodes, new executable packages, secrets, or role elevation |
| Auditor | Read redacted audit/configuration history and usage totals | No private prompts, secrets, or mutations |
| Member | Chat, tools explicitly allowed to members, own memory/artifacts/API keys | No farm administration or other users' content |
| WorkspaceAdmin | Manage members and published knowledge within a specific workspace | No farm role grants; no implicit private conversation access |
| WorkspaceEditor | Write shared project documents and explicitly published artifacts | No membership management |
| WorkspaceViewer | Read workspace-published material | No write or membership management |

Farm and workspace roles are independent grants. Multiple roles combine named permissions, but explicit locality, credential, and owner restrictions still apply. Ship these built-in roles and a permission catalog; allow Owners to create custom roles from catalog entries with server-side anti-escalation checks. Service identities are separate from human roles and have narrow actions.

By default a workspace conversation is still private to its author; publishing it or specific artifacts to the workspace is explicit. Public farm documentation must be deliberately published. Cross-user topic merging is disabled. Resource ACL changes increment an authorization version used in caches and invalidate active retrieval/session views.

## Database isolation

Every content table includes farm, owner, and workspace scope where applicable. Apply PostgreSQL RLS and application authorization. The application role must not be a table owner, superuser, or have BYPASSRLS; force RLS where appropriate. Migration and backup roles are separate. Set identity context transaction-locally from validated server claims and reset it on pooled connections; never trust a client-provided user ID. Test background jobs and joins, not just direct selects. [PostgreSQL row security](https://www.postgresql.org/docs/current/ddl-rowsecurity.html)

RLS does not replace path permissions for files, graph partitioning, or artifact authorization. Even counts, suggestions, autocomplete, graph topology, and error details can reveal another user's data and must be scoped.

## Tool and model isolation

- Models produce requests, not authority. Tool grants are the intersection of user permission, task purpose, capability recipe, workspace resources, and tool policy.
- Tool descriptions are approved catalog data. Retrieved text, generated scripts, and tool results cannot add tools or expand scopes.
- Run MCP servers with dedicated service identities and isolated filesystems. Linux is the initial toolbox host profile, with container or namespace isolation, read-only base filesystems, resource limits, and restricted egress. Do not pass a Docker socket into an agent sandbox.
- Code execution receives a per-task sandbox and selected repository snapshot, not the host home directory or all NAS shares. Store patches as artifacts; committing or publishing follows explicit tool policy.
- Credentials are injected only into the authorized tool process. They do not appear in prompts, general logs, model manifests, or worker inventories.
- Third-party tool servers are approved at a pinned package revision. Tool schema changes invalidate approval before they become available.
- Destroy task contexts and tool sandboxes after completion/expiry. Cross-user prompt-prefix/KV cache reuse is disabled initially. Shared weights are acceptable; shared user context is not.

## Cloud authorization and data labels

Use a monotonic locality label: `cloud_allowed` or `local_only`. Unclassified content defaults to `local_only`. Derived output inherits the most restrictive label of all contributing input, including retrieved memories and tool results. A model cannot remove a label by summarizing content.

When a user starts a conversation with their standing cloud preference enabled, the application explicitly labels their newly authored messages cloud-allowed, subject to workspace policy. Existing history, imported files and tool results retain their source labels. The composer explains this once when setting the preference, so cloud fallback can operate automatically for eligible new work without reclassifying older private material.

Cloud use requires all of: configured approved provider, capability permission, farm budget, user quota, workspace policy, user standing opt-in, and every outgoing content item labeled cloud-allowed. User opt-in can be set once in preferences or per conversation; do not prompt repeatedly for an already authorized scope. Existing private memories remain local-only until the user explicitly changes their source policy. A blocking local-only reference is shown as a reason to queue locally or let the user explicitly exclude/reclassify it.

Default farm cloud budget is zero until configured. This is an application setup default, not a request for additional approval during this planning task. Provider model lists and price schedules are versioned deployment configuration. All classifier, embedding, graph extraction, and specialist subcalls use the same cloud gate. Do not let Graphify auto-detect ambient provider credentials.

Locality is enforced before sending any classifier prompt, before context assembly is exported, and at the final egress gateway. OpenAI keys live only in the cloud gateway. Use `store=false` for Responses where supported and hold durable conversation state locally; do not describe this as zero retention. Provider handling varies by feature and account. [OpenAI data controls](https://developers.openai.com/api/docs/guides/your-data)

## Secrets, audit, and backup

Encrypt secret records using a maintained envelope-encryption library; keep the master key outside the database in a root-readable deployment secret or OS secret store. Back it up separately with the recovery kit. Use full-disk encryption on controller and authorized content workers where available; the installer checks and reports this posture without falsely claiming Hearth can encrypt arbitrary existing disks.

Audit role changes, enrollment, revocation, model/tool approval, secret configuration metadata, cloud policy decisions, data export/deletion, and privileged operations. Exclude raw prompts and secret values from security logs. Separate conversation content storage from audit metadata. Audit writes are append-only to the app role, with daily hash-linked exports to a restricted backup destination; these are tamper-evident under the defined threat model, not immutable against root.

Backups are encrypted and access-controlled. Restore applies the deletion ledger before serving traffic so removed content is not resurrected. Supply a redacted support-bundle command. A full log export is not the default troubleshooting artifact.

## Security invariants

1. Discovered is never trusted; trusted is never automatically authorized for every task.
2. A child task has no greater authority, cloud permission, or budget than its parent.
3. A resource ID never substitutes for authorization.
4. Cloud routing cannot be induced through prompts, tool output, retries, or missing nodes.
5. A revoked identity cannot receive new work or content.
6. A deleted or unauthorized source cannot participate in retrieval or graph traversal.
7. Credentials do not move to inference workers unless a narrowly scoped tool execution requires them.
8. Browser, model, node, and NAS inputs are validated at their respective boundaries.

## Central provisioning boundary

Only an authorized administrative action may commit a NodePlan. General model/tool traffic, ordinary Members and the anonymous bootstrap channel cannot install software or change service settings. The protected admin-agent executor in [12](12-ADMIN-AGENT-AND-FIRST-PROVIDER.md) may submit a reviewed or explicitly delegated change under live administrator permissions; the model itself receives no administrative token. NodePlans refer to approved signed recipes with typed parameters, not arbitrary commands or caller-supplied download URLs. A privileged local helper performs only fixed installation/service operations allowed at setup; inference processes stay unprivileged. Package updates require digest/signature, compatibility, replay/downgrade and rollback checks. FarmAdmin assignment rights do not imply permission to approve arbitrary executable code.

Enrollment proof material is generated on the member, entered only into the authenticated admin UI, and never broadcast, logged, or included in diagnostics. The waiting member validates the JWE grant before trusting any farm configuration. Normal clients cannot fall back into the special anonymous bootstrap transport. Test compromised LAN relay, substituted farm root, foreign node CSR, replay, and both IP-mode origins and DNS-mode origins.

## Administrative agent security

Add `admin_agent.use` and own-history permission without granting any new management rights. Model-visible tools are a fixed policy facade, separate from public user/MCP tools. Effective authority intersects live role/resource permissions, run scope, a reviewed change or bounded session grant, and farm policy. Credential and pairing widgets submit directly to protected services; return references/status only. No prompt, diagnostic output or provider response can approve its own plan or grant permissions.

Admin histories are author scoped and separate from user memory; infrastructure administration does not unlock Member content. OpenAI-first setup requires its own informed admin-data allowance, budgets and per-call egress checks. Minimize operational fields with opaque aliases; raw credentials, configuration files, private paths and user content never enter that default allowance. All incoming labels, logs and model cards remain untrusted data. Expired/stale approvals, role revocation, duplicate Apply, dangerous self-provider changes and model-injected package requests are tested in A01-A12. Ordinary UI administration remains available when inference is unavailable.
