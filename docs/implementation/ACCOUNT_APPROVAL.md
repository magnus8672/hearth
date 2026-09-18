# Signup, approval and capability access

The head's HTTP welcome page provides the current public root certificate, a Windows installer, manual browser instructions and secure-connection checks. After confirming certificate installation, **Continue to secure registration** opens the branded HTTPS registration flow. Passwords, authenticator enrollment and recovery codes remain in Keycloak. The registration entry uses the same browser-bound state, nonce and PKCE checks as sign-in. See the [Keycloak administration reference](https://www.keycloak.org/docs/latest/server_admin/) for the underlying registration and required-action flow.

A browser cannot silently install a root certificate. The Windows download is a self-contained `.cmd` installer that verifies its embedded certificate digest, asks the person to compare the fingerprint and type `YES`, and imports only that root into the current Windows user's trusted-root store. It does not download code or request administrator elevation. Zen and Firefox can require the documented manual Authorities import. Other operating systems use the PEM/DER downloads. The installer and certificate ZIP are regenerated together when the head address package is rebuilt.

## Approval

New accounts have `pending` state, no roles and no permissions. They can sign in, view the waiting workspace, check access and sign out. Signing in again never adds grants. The first Owner remains a console-only bootstrap operation.

In **Administration → People**, an Owner or farm administrator can:

- Enable an account with selected workspace features and individual capability grants.
- Apply a Chat only preset or grant all workspace capabilities.
- Grant the Farm administrator, Operator or Auditor role.
- Return an account to waiting status or suspend sign-in.

Farm administrators can manage users and promote other farm administrators. Owner recovery and package approval remain reserved for Owners. The editor cannot change the acting person's account or any Owner account, preventing self-lockout and removal of the final Owner. These checks run inside the serialized database change function as well as the authenticated admin API. Stale edits fail with a revision conflict. Account changes are audited without exposing private content.

Approval changes invalidate existing browser sessions, client keys and execution receipts by advancing the account's authorization version. **Check access** starts sign-in again and reuses an existing valid MFA SSO session. Affected users must replace old API keys. Suspending an account preserves its data but blocks login and execution.

Migration `0025` preserves existing accounts, roles and content. Previously provisioned Members receive explicit grants equivalent to their existing workspace access. Future Members receive only the administrator's chosen grants; the Member role alone grants nothing.

## Permission boundaries

Each of the fourteen catalog capabilities has a `capability.<id>` permission. Private chat, channels, drafts, shared tools and client keys have separate feature permissions. Images and 3D models can be granted independently of chat. Memory retrieval and memory changes have separate grants.

The server enforces permissions at browser handlers, automatic and explicit specialist routing, image planning, client-key creation and use, MCP discovery/execution, memory recall and durable GPU queue dispatch. Client-key scopes intersect current account grants. Revocation fences prevent queued work from starting and stop publication of stale in-flight results; already-dispatched external tool side effects cannot be undone. The existing cancellation/drain protocol still determines when GPU capacity is safe to release.

Navigation and media controls reflect the granted permissions. They are convenience controls, not authorization boundaries. Private content retains owner/farm RLS; an administrator cannot browse another person's conversations or artifacts through account management.

## Qualification and remaining work

Focused tests use isolated PostgreSQL storage on the head VM. Browser fixtures use the deployed bundles with explicit synthetic API responses; the public welcome and registration entry use the real HTTPS edge and identity service. Live signup qualification uses a temporary synthetic account and verifies its removal without changing existing credentials.

The deployed build passes three focused backend runs (98, 50 and 10 passing cases, with overlap) and seven browser cases. A real temporary account completed password registration, authenticator and recovery-code enrollment, reached the pending workspace with zero permissions, then gained Administration through the existing MFA SSO session after promotion. Its account was removed and existing credentials were unchanged. The root certificate remains unchanged and the public installer matches the certificate ZIP. See the [qualification record](../../evidence/accounts/2026-09-18/validation.json) for boundaries and remaining limits.

Invitation-only registration, email verification, password/MFA recovery administration, permanent account deletion, quotas by account, group policies and fleet-wide OS certificate installer qualification remain separate work. No full release gate is closed by this increment.
