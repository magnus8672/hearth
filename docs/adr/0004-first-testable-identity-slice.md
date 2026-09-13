# ADR 0004: First testable identity and private workspace slice

Status: implemented for the local development reference, not a completed P1 release gate.

The first user test exercises real accounts and durable private work before provider installation. Separate React bundles are served over HTTPS at localhost ports 8443 and 8444. Keycloak is on 8445. The edge excludes the master realm and administrative identity routes.

Each BFF process has a fixed audience. Login uses confidential clients, authorization code flow, S256 PKCE, nonce/state, exact callback origins and a browser-bound, one-use PostgreSQL login attempt. ID token signatures, issuer, audience, nonce and lifetime are verified with maintained libraries. OIDC credentials are encrypted in PostgreSQL with a private generated key. Distinct Secure, HttpOnly, host-only cookie names contain opaque session secrets. Token hashes and audience bindings prevent cookie renaming from granting cross-application access. Mutation requests require the exact Origin and the session's CSRF token.

Sessions expire after eight hours or 30 minutes of inactivity. Refresh tokens stay server-side; live introspection checks identity activity. Database authorization versions and current roles are checked on every request. Logout removes the BFF session even when the identity service is unavailable. All local browser accounts require a second factor. The Keycloak browser flow offers OTP or recovery codes, with required OTP enrollment when no second factor exists. Step-up for future sensitive management actions is still pending.

The native Go developer setup tool binds only to loopback and uses a random 256-bit fragment proof. It clears the fragment from browser history and requires both the proof and exact Host/Origin for fixed setup operations. It has no general command endpoint. Owner provisioning is serialized and one-use in the database; public provisioning can create only Member grants and one personal workspace. The helper remains a local developer component holding maintenance credentials, not the production privileged-helper protocol or signed installer.

Windows root trust requires the user's explicit setup button. The root is fetched through the pinned maintenance channel and its SHA-256 fingerprint is displayed. Browser automation uses a separate Linux NSS trust store with certificate validation enabled. It does not change Windows trust or bypass a certificate interstitial.

Migration 0002 provisions personal accounts atomically. Draft endpoints operate through the restricted application database role and forced RLS. Draft updates use revision checks. Catalog cards come from PostgreSQL and remain Unassigned until future real provider probes succeed. No inference, model download or cloud call is implied by this milestone.

The implementation follows the [Keycloak hostname and backchannel documentation](https://www.keycloak.org/server/hostname), [client protocol mapper reference](https://www.keycloak.org/admin-api/protocol-mappers), and [authentication/2FA guide](https://www.keycloak.org/docs/latest/server_admin/). Qualification records live under `evidence/identity/2026-09-12/`.

Remaining P1 scope includes LAN range/rate policies, a signed installer, OS trust qualification on other systems, administrator role editing and step-up, API keys, workspace roles, suspension controls, audit browsing and broader recovery/authorization scenarios. P4 still owns actual first-provider and protected admin-agent workflows.
