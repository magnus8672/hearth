# Current ESX head

This is the active head and runtime test host. The user retired laptop-hosted hearth on 15 September 2026. Use the laptop for source editing, Git and browser/client access; preserve its old farm files without restarting its QEMU appliance or local hearth-managed providers. Do not create another test farm. Test changes here with existing VM data protected, and adapt destructive integration fixtures to isolated test storage before running them.

The user's fresh head VM is `10.20.30.10`, with the deployment package at `/opt/hearth`. It runs Ubuntu 26.04.1 on VMware with 24 vCPUs, approximately 60 GiB usable RAM and a 98 GiB root filesystem. Docker Engine 29.8.0 and Compose 5.5.1 were installed from Docker's signed Ubuntu repository and Docker is enabled at boot.

Use the existing SSH agent key as **operator** for future maintenance. Passwordless sudo is configured and verified. The matching public key was copied from root's authorized keys, without replacing any existing operator keys. Root SSH access was preserved. The package and private farm configuration remain root-owned; use sudo for setup commands.

```powershell
ssh operator@10.20.30.10
```

## First Owner

The user requested a fresh farm and will create the first Owner themselves. No laptop accounts, chats, memory, credentials or provider settings are migrated. Run from the laptop:

```powershell
ssh -t operator@10.20.30.10 "cd /opt/hearth && sudo python3 scripts/head.py owner"
```

The console prompts for the username, display name, farm name and password. Then sign in through the browser to enroll an authenticator and save recovery codes. Browser-only first-Owner bootstrap is not included in this package. Public registration opens for Members after the Owner exists.

## Addresses and certificates

| Purpose | URL |
|---|---|
| Welcome and certificate download | `http://hearth.example.invalid` |
| Workspace | `https://hearth.example.invalid` |
| Administration | `https://hearth.example.invalid:8443` |
| Identity | `https://hearth.example.invalid:8445` |
| Client API | `https://hearth.example.invalid/v1` |
| MCP | `https://hearth.example.invalid/mcp` |

The saved base URL is the workspace origin above. The edge listens on 0.0.0.0. The current server certificate names `hearth.example.invalid`, whose DNS A record is `10.20.30.10`. The hostname migration preserved the existing trust root. Its root is separate from the laptop development farm's root and must be trusted separately. The public certificate package is `/opt/hearth/.hearth/head/hearth-client-certificates.zip`; local copies are under `dist/hearth-esx-certificates/` and `dist/hearth-esx-client-certificates.zip`. Compare the exported root fingerprint over SSH before importing it.

The HTTP welcome page serves public trust downloads and connection checks; account and application operations remain on HTTPS. The 16 September migration passes certificate-verified HTTPS and the in-app browser reaches workspace, admin welcome and branded sign-in without a trust bypass. Full real MFA sign-in in Zen remains a user acceptance check. Use [Administration address settings](../implementation/HEAD_ADDRESS_SETTINGS.md) for further URL changes and certificate-package downloads.

## Maintenance

```bash
cd /opt/hearth
sudo python3 scripts/head.py status
sudo python3 scripts/head.py export-certificates
```

The Compose project is `hearth-head`. Re-running `sudo python3 scripts/head.py up` rebuilds the current source and applies migrations, so use it during maintenance. Docker restart policies resume the services at VM boot. Back up `.hearth/head/config.json` and the project's PostgreSQL, Caddy and memory-vault volumes together. Never regenerate the farm encryption key or change the identity address as a recovery shortcut.

Models remain on their provider machines. Register LAN addresses in the new farm instead of the old laptop's loopback/QEMU aliases. Speech/transcription were not installed during head startup; the included audio installer currently targets Ubuntu 24.04/Python 3.12, and its host recipe needs a separate update for this Ubuntu 26.04 VM.

The first deployment checks are deliberately limited to package integrity, SSH/sudo, service startup, published ports, private configuration permissions and HTTPS reachability. Account enrollment and browser/provider workflows are reserved for the user's test. See [deployment evidence](../../evidence/head-esx/2026-09-14/deployment.json) and [HTTPS checks](../../evidence/head-esx/2026-09-14/https.json) for observed results, rather than assuming complete product acceptance.
