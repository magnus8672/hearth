# P1: identity, RBAC, and separate application shells

Dependency: P0. Outcome: LAN users can create private accounts, while authorized administrators use a separate application.

## Build

1. Implement console-bound one-use Owner bootstrap, Keycloak realm/client configuration, OIDC BFF sessions, admin MFA/step-up, account suspension, and logout invalidation.
2. Implement allowed-LAN self-registration with rate limits. Provision a personal workspace and Member grant atomically after first successful login. Repeated callbacks must not duplicate these records.
3. Add role/permission catalog, custom role composition, scoped grants, anti-escalation rules, workspace roles, and PostgreSQL RLS. Separate migration and application database credentials.
4. Build user and admin bundles/origins with shared accessible visual components. Add navigation and capability cards populated from the real catalog, showing Unassigned initially.
5. Add audit events for bootstrap, grants and security changes; API key lifecycle and minimal authorized session/capability APIs.
6. Implement installer-launched, one-time loopback Create Hearth setup with owner/MFA/recovery, automatic control-stack preparation, LAN/interface selection and trusted links. Support IP-based HTTPS origins before optional DNS mode. Use distinct cookie names and exact-origin protections because ports do not isolate cookies. Follow [11](../../../plan/11-INSTALLATION-AND-CENTRAL-MANAGEMENT.md).

## Prove

Add the deterministic first-provider wizard and Admin agent UI shell with protected session/history namespaces. Display honest no-provider states until P4 supplies real inference. Implement secure input/pairing cards, concrete plan preview/grant components and manual recovery navigation. Read-only access and mutation rights remain separate; a Member cannot discover or call admin-agent tools. See [12](../../../plan/12-ADMIN-AGENT-AND-FIRST-PROVIDER.md).

E01, E15 and S04, S12, S16, S18 from [validation](../../../plan/09-VALIDATION-AND-RELEASE.md). Test an Owner, Operator, Auditor, two Members, and a workspace membership revocation. Exercise authorization directly at API and database levels, including pooled connections and SSE access.

User A cannot read User B's records by guessing IDs. A self-registered account cannot reach administrative operations. A stolen/expired CSRF token fails. Removing the last Owner is rejected. An admin session cookie is not valid on the user application and vice versa.

Exercise C01's reference first-node path and C08's loopback, DNS rebinding, origin, cookie and browser-trust cases. A remote LAN client cannot win Owner bootstrap. Restarting or failing to find a head does not create another farm.

## Exit gate

Actual signup/login works in the browser over trusted HTTPS in the test environment; security tests pass; screenshots cover empty and unauthorized states. Decorative screens without working authorization do not satisfy this phase.

Next: [P2](../../../plan/phases/P2-DISCOVERY-AND-ENROLLMENT.md).
