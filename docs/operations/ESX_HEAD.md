# Operating an existing head VM

Actual addresses, SSH accounts, hardware inventory and private access policy belong in operator configuration outside Git. For a new installation, use [head VM setup](HEAD_VM_SETUP.md).

## Access and preservation

Use the operator-authorized maintenance account and deployment path. `/opt/hearth` and Compose project `hearth-head` are documented defaults, not a claim about your machine. Do not assume root login or passwordless sudo is enabled.

Preserve accounts, credentials, MFA, private configuration and content. First-Owner console bootstrap is only for a new empty installation. Automated reset fixtures require isolated test storage. Do not start another farm or local appliance as a maintenance shortcut.

New signups start pending with zero permissions. Administrators approve access in **People**; workspace and administration share MFA identity while keeping separate authorization. See [account approval](../implementation/ACCOUNT_APPROVAL.md) and [SSO](../implementation/SINGLE_SIGN_ON.md).

## Addresses and trust

Read actual origins from private head configuration. Default conventions are:

| Surface | Default convention |
|---|---|
| Welcome and public certificate downloads | HTTP on the configured head hostname |
| Workspace | Configured HTTPS base URL |
| Administration | Same hostname, HTTPS port 8443 |
| Identity | Same hostname, HTTPS port 8445 |
| Client API / MCP | Workspace origin plus `/v1` or `/mcp` |

Custom ports must match deployment configuration. Configure DNS for the real hostname and preserve the existing trust root during address changes. HTTP serves public trust downloads; application and account operations remain on HTTPS. Export public certificates through the head helper, verify the root fingerprint through a trusted channel, and retain TLS validation. See [address settings](../implementation/HEAD_ADDRESS_SETTINGS.md).

## Maintenance

Run on the authorized host, adapting the installation directory if needed:

```bash
cd /opt/hearth
sudo python3 scripts/head.py status
sudo python3 scripts/head.py export-certificates
sudo docker ps --filter label=com.docker.compose.project=hearth-head
```

`sudo python3 scripts/head.py up` rebuilds services and applies migrations; schedule it as maintenance. Back up `.hearth/head/config.json` and the PostgreSQL, Caddy and memory-vault volumes together. Never regenerate the farm encryption key or change the identity address as a recovery shortcut.

Model services run on separately configured provider hosts. Inspect **Providers**, **Workers** and **Farm map** for your bindings and residency. For shared GPUs, pause/drain through the worker before maintenance and let its signed recipe control service selection. Do not independently start competing media services.

Keep private records and raw diagnostics in ignored `.hearth/` storage. Publish only reviewed results according to [repository privacy](REPOSITORY_PRIVACY.md). The [ledger](../implementation/BUILD_STATUS.md) records dated qualification; it is not a live inventory.
