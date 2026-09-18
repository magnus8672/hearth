# Head address and certificate settings

Owners and FarmAdmins can open **Administration → Settings → Address & certificates**, enter the workspace HTTPS base URL, preview the derived addresses and choose **Apply & rebuild certificates**. The preview checks DNS from the head and shows the workspace, administration, identity, client API and HTTP welcome URLs. Download the public certificate ZIP from the same settings page or the HTTP welcome page.

The existing trust root is preserved. A newly named endpoint receives a certificate from that root; existing clients that trust it do not need another root import. The package contains the public root, current server chain, fingerprints and updated connection metadata. It contains no private keys, passwords or client API keys. Rebuilding at the current URL refreshes the package; it does not rotate the root or force renewal of a still-valid leaf. Caddy handles routine leaf renewal.

## Applying a change

1. Set a DNS A record to the head's LAN IPv4 address. All IPv4 answers seen by the head must belong to one of its non-loopback interfaces. DNS and firewall rules remain the administrator's responsibility.
2. Preview the new URL. Use an HTTPS origin without `/v1`, credentials, paths, query or fragment. The workspace port can change; administration and sign-in retain their existing separate ports.
3. Review the URLs and apply. The head briefly restarts its identity, API and edge services. Browser sessions end; sign in at the new Administration link after the restart.
4. Update saved URLs in agents and editors. The same API keys remain valid at the new `/v1` URL. Existing browser bookmarks redirect to the new root when the corresponding listener port is unchanged. Redirects never forward POST bodies, query strings or OIDC callback codes.

The operation updates Keycloak's hostname and exact client redirects, both BFF origins, the trusted host, Caddy certificates and public setup downloads together. Existing user IDs and Keycloak subject IDs are retained while the saved issuer changes. Roles, passwords, MFA enrollment, private content, provider configuration and client keys remain in place. Old browser sessions and in-progress browser login attempts are invalidated.

## Local supervisor boundary

`scripts/head_control.py` runs as `hearth-head-control.service` on the Linux host. It exposes only status, preview, apply and public certificate download over a Unix socket. Only the admin BFF receives a read-only mount containing that socket. The personal BFF, models, MCP tools and external API keys cannot reach the host control interface. Neither BFF receives the Docker socket, private head configuration or PKI private keys.

The BFF requires a live admin session, exact origin, CSRF token and `farm.configure` permission, then records an audit event before submission. The host verifies the peer UID and checks the approving account's current Owner/FarmAdmin role again through its existing console. It accepts bounded, closed request objects, validates all URLs and invokes fixed maintenance commands without a shell. It does not expose a general host-command interface.

Only one address change may run at once. A revision binds the preview to the current addresses; operation IDs make submission retries idempotent. A private atomic journal stores the previous configuration. HTTPS certificate validation, BFF readiness and the advertised OIDC issuer must pass before success and certificate export. A failure restores the previous configuration and identity binding, restarts those services and checks them again. After a daemon interruption, recovery runs before new requests are accepted. A failed rollback remains explicit and blocks further changes.

## Installation and recovery

Standalone startup installs the service automatically when `scripts/head.py up` runs as root on systemd. For an existing deployment with updated source and browser bundles:

```bash
cd /opt/hearth
sudo python3 scripts/head.py install-control
```

The API/edge containers also need the updated Compose configuration and API image. Routine updates must be done while no address operation is in progress. The initial `configure` command still refuses to overwrite an established address; use the settings workflow for an existing farm.

For an operation that reports manual recovery required:

```bash
cd /opt/hearth
sudo systemctl stop hearth-head-control
sudo python3 scripts/head_control.py recover
sudo systemctl start hearth-head-control
```

Do not regenerate `.hearth/head/config.json`, delete volumes, rotate the CA or reset accounts to fix an address change. The journal and source backups are private maintenance state under `.hearth/head/` and `.hearth/`.

## Verification and limits

The VM suite covers URL validation, farm-key preservation, DNS mismatch, safe old-address redirects, duplicate/concurrent operations, interrupted-operation recovery, injected failure rollback, admin audience and role restrictions, CSRF, audit insertion, account identity preservation, private draft restoration and reuse of an existing API key after an issuer change. Those database fixtures use a separate temporary database on the existing VM PostgreSQL service, then remove it. They never reset the live farm or start another farm.

This is a bounded Linux/systemd head-management feature. IPv6, public NAT-only DNS addresses, multi-head coordination, custom public CA enrollment, sensitive-action step-up and complete disaster recovery remain separate work. A passing certificate/issuer check does not by itself prove a user's browser trust store or a full real MFA sign-in. No release gate is closed by this addition.
