# Direct HTTP for existing LAN providers

Implemented 13 September 2026 at the user's request. Administrators can connect an existing LM Studio or another supported external provider using HTTP on a trusted private network, without installing certificates or a connector. hearth-managed runners retain automatic TLS as their intended default. This is an explicit amendment to the earlier external-provider TLS-only policy; the original design snapshot remains unchanged.

## Use it

On an existing failed provider card, select **I understand the risks. Use HTTP**. hearth saves approval for that server address and retries verification. For a new connection, enter its HTTP address and select **I’m the administrator and I understand the risks. Allow HTTP for this server.** Then connect and verify normally. The approved card shows **HTTP · admin accepted risks** and offers **Revoke HTTP approval**.

The warning explains that prompts, replies, images and any provider API key travel unencrypted and can be read or changed by someone with access to that network. The choice is available directly in Administration; there is no separate confirmation from the coding assistant, certificate ceremony or global insecure-mode setting.

## Scope and behavior

| Boundary | Behavior |
|---|---|
| Authorization | Owner/FarmAdmin provider-configuration permission, admin BFF audience, active session and CSRF checks are required. Requests use the target revision to reject stale changes. |
| Approval scope | A persisted boolean belongs to one provider connection, whose normalized address is fixed. Every model on that connection shares the same transport policy. New addresses start unapproved, and the form clears approval whenever an address changes. |
| Evidence | Acceptance/revocation appends an audit event with the actor, time, connection ID and decision. Changed policy invalidates every affected model's probe evidence and increments revisions. Disabled siblings remain disabled. Admission receipts retain the policy used for that turn. |
| In-flight work | Policy changes wait until all affected resource groups are idle, including groups awaiting resolution of an uncertain job. Unrelated server approvals, groups and assignments remain unchanged. |
| Network constraints | The override permits HTTP only to the existing eligible private addresses. DNS results are still checked and pinned; mixed public/private answers, public and metadata-service addresses, hearth application loopback ports, arbitrary paths and redirects remain blocked. |
| HTTPS | Certificate and hostname verification remain enabled. HTTP approval cannot be used as a bypass for an HTTPS certificate failure. |
| Ownership | The option applies to external provider connections, including supported image-job providers. It does not change worker enrollment, managed-runner trust, application/identity HTTPS or cloud budgets. The connector remains an optional TLS path. |

Migration `0013` adds `provider_connections.allow_insecure_http`, default `false`. Existing approvals remain off until explicitly accepted. The API exposes the value on provider cards and accepts it during registration/editing, plus a scoped `POST /api/v1/providers/{target_id}/http-consent` action for acceptance or revocation.

## Validation

- The browser regression reproduces the failed model-server card, accepts the risk, retries verification with the new revision, restores approval after reload, revokes it, and confirms that a different address needs fresh approval. Desktop/mobile screenshots are in the evidence directory.
- API/database regressions cover admin/Member/CSRF isolation, stale revisions, shared-model invalidation, disabled siblings, busy/uncertain groups, durable audit events, revocation and moving to another address. The application role remains unable to read audit storage; tests inspect those fixture side effects through the migration test role.
- Transport regressions cover exact-address scoping in production and test modes, DNS pinning, public/metadata/mixed-DNS rejection, strict booleans, and continued HTTPS trust/hostname checks. Existing text and image regressions remain in the full suite.
- The [live LAN test](../../evidence/http-consent/2026-09-13/live-lan.json) connects to the user's actual `qwen/qwen3.8-27b` on another machine. A probe is blocked without approval, then succeeds after the explicit admin action; a routed chat reply completes and loaded model IDs remain unchanged. It uses a disposable farm with explicit OIDC fixtures and does not change the user's saved model-server record.

See [deployment and test results](../../evidence/http-consent/2026-09-13/validation.json). This is real remote-model transport evidence, not completion of every multi-host farm gate. All 61 release gates retain their prior status. General managed residency, enrollment, other modality adapters and complete LAN/load/failure acceptance remain open.
