# One sign-in across hearth

> Addresses, host labels and accounts shown here are illustrative placeholders. Use your own private deployment configuration.

Implemented and deployed on the existing head at `10.20.30.10`, 17 September 2026.

Previously every `/auth/login` request sent `prompt=login`, and the custom Keycloak browser flow contained only password and second-factor steps. Both choices forced credentials again when an administrator moved between the workspace and Administration. OTP replay protection then correctly rejected a code just used in the other application, making the unnecessary second login particularly awkward.

Ordinary login now permits Keycloak to reuse its existing authenticated session. The versioned `hearth-browser-sso-v1` flow has two alternatives: the Cookie authenticator, or a complete password/MFA subflow. That subflow retains OTP/recovery authentication and mandatory OTP enrollment when no usable second factor exists. The old flow remains available for in-flight sign-ins and rollback; setup builds the new flow before selecting it. OTP code reuse stays disabled. The live realm retains its 30-minute idle and eight-hour maximum session limits.

Sidebar links go directly to the destination's `/auth/login`, so switching applications creates the destination session without an extra welcome-page click. A direct visit to an anonymous application's home still shows its welcome page; selecting Sign in also reuses SSO when available. Separate browser profiles and expired or signed-out identity sessions still need authentication.

The two BFF clients remain confidential and audience-specific. They retain separate opaque Secure/HttpOnly cookies, state and nonce, S256 PKCE, exact callback origins, signature/audience validation, encrypted server-side tokens, CSRF checks and current database permissions. A Member does not become an administrator through SSO. Sensitive-action step-up remains a separate incomplete feature.

Sign out removes the current BFF session and the same account's companion session presented by that browser. The pinned Keycloak backchannel logout ends the shared identity session, invalidating both client grants without sending refresh or ID tokens through browser URLs. This uses Keycloak's provider-specific refresh-token logout endpoint and must be requalified if the identity implementation changes. Other devices' unrelated sessions are not deleted by user ID. The browser clears both application cookies. If the identity service is unavailable, local logout still succeeds and sets a Secure/HttpOnly marker requiring fresh credentials on the next login; a successful callback clears that marker.

## Deployment and qualification

Normal setup uses the new flow. For an existing head, update/build the source and both browser bundles, then run the private Compose `head-console sso` action using `scripts/head.py`'s configured environment. This action changes authentication flow configuration only. It does not reset accounts, credentials, clients, roles, sessions or farm storage. Both BFF processes need the updated image. The active deployment's prior image is tagged `hearth-control:before-sso`, and prior source files are under private `.hearth/before-sso-*` backups. The old `hearth-browser` flow is retained.

The [protocol qualification script](../../scripts/identity_sso_qa.py) runs against the existing Keycloak service, creates one marked disposable realm, and removes it in `finally`. It never provisions a test farm or user in the real realm. Synthetic accounts exercise password/OTP once, immediate SSO in both directions, signed audience-specific token validation, full identity logout, mandatory enrollment and idempotent flow setup. Existing account and credential identifiers are compared before and after. This is an HTTP protocol test, not a claim of browser acceptance in Zen.

Twelve focused BFF, origin and packaging tests passed on the head VM with an isolated temporary database that was removed afterward. They include callback replay/browser binding, cookie-audience separation, Member permission denial, CSRF, logout, session expiry, authorization changes and identity-outage recovery. Type checks, both production builds, source lint and documentation checks pass. Live certificate-verified checks confirm the active flow, unchanged timeouts, disabled OTP reuse, both readiness endpoints and authorization redirects without `prompt=login`. See [deployment evidence](../../evidence/identity/2026-09-17-sso/deployment.json) and [validation scope](../../evidence/identity/2026-09-17-sso/validation.json).

Refresh both browser applications once to load the updated links. Sign in normally if needed, then switch using Administration / Your workspace. Full user acceptance in Zen remains the next manual check. No full release gate changes status.

References: [Keycloak authentication flows](https://www.keycloak.org/docs/latest/server_admin/#_authentication-flows), [Keycloak logout endpoint](https://www.keycloak.org/securing-apps/oidc-layers#logout-endpoint).
