# Current ESX head

This is the active head and runtime test host. The user retired laptop-hosted hearth on 15 September 2026. Use the laptop for source editing, Git and browser/client access; preserve its old farm files without restarting its QEMU appliance or local hearth-managed providers. Do not create another test farm. Test changes here with existing VM data protected, and adapt destructive integration fixtures to isolated test storage before running them.

The user's active head VM is `10.20.30.10`, with the deployment package at `/opt/hearth`. It runs Ubuntu 26.04.1 on VMware with 24 vCPUs, approximately 60 GiB usable RAM and a 98 GiB root filesystem. Docker Engine 29.8.0 and Compose 5.5.1 were installed from Docker's signed Ubuntu repository and Docker is enabled at boot.

Use the existing SSH agent key as **operator** for future maintenance. Passwordless sudo is configured and verified. The matching public key was copied from root's authorized keys, without replacing any existing operator keys. Root SSH access was preserved. The package and private farm configuration remain root-owned; use sudo for setup commands.

```powershell
ssh operator@10.20.30.10
```

## Existing accounts and registration

The live farm already has its Owner and user content. Preserve those accounts, credentials and MFA enrollment. First-Owner console bootstrap is only for an empty new installation; follow [fresh-head setup](HEAD_VM_SETUP.md) for that separate case.

New web signups now enter a pending workspace with zero permissions. An Owner or FarmAdmin approves access in **People**, selecting feature/capability grants. Workspace and Administration reuse the same MFA identity session while retaining separate BFF authorization. See [account approval](../implementation/ACCOUNT_APPROVAL.md) and [SSO](../implementation/SINGLE_SIGN_ON.md).

## Addresses and certificates

| Purpose | URL |
|---|---|
| Welcome and certificate download | `http://hearth.example.invalid` |
| Workspace | `https://hearth.example.invalid` |
| Administration | `https://hearth.example.invalid:8443` |
| Identity | `https://hearth.example.invalid:8445` |
| Client API | `https://hearth.example.invalid/v1` |
| MCP | `https://hearth.example.invalid/mcp` |

The saved base URL is the workspace origin above. The edge listens on 0.0.0.0. The current server certificate names `hearth.example.invalid`, whose DNS A record is `10.20.30.10`. The hostname migration preserved the existing trust root. Its root is separate from the laptop development farm's root and must be trusted separately. The public certificate package is `/opt/hearth/.hearth/head/hearth-client-certificates.zip`; previously exported local copies used `dist/hearth-esx-certificates/` and `dist/hearth-esx-client-certificates.zip`. Those ignored outputs are not guaranteed to exist in this checkout. Compare the exported root fingerprint over SSH before importing it.

The HTTP welcome page serves public trust downloads and connection checks; account and application operations remain on HTTPS. The 16 September migration passes certificate-verified HTTPS and the in-app browser reaches workspace, admin welcome and branded sign-in without a trust bypass. Later account qualification includes real temporary-account signup/MFA/approval/SSO. Full OS/browser trust and release qualification remain open; historical Zen-specific results are not a claim about every current browser. Use [Administration address settings](../implementation/HEAD_ADDRESS_SETTINGS.md) for further URL changes and certificate-package downloads.

## Maintenance

```bash
cd /opt/hearth
sudo python3 scripts/head.py status
sudo python3 scripts/head.py export-certificates
```

The Compose project is `hearth-head`. Re-running `sudo python3 scripts/head.py up` rebuilds the current source and applies migrations, so use it during maintenance. Docker restart policies resume the services at VM boot. Back up `.hearth/head/config.json` and the project's PostgreSQL, Caddy and memory-vault volumes together. Never regenerate the farm encryption key or change the identity address as a recovery shortcut.

Models remain on their provider machines. Register LAN addresses in the farm instead of the old laptop's loopback/QEMU aliases. Speech/transcription were not installed during head startup; the included audio installer currently targets Ubuntu 24.04/Python 3.12, and its host recipe needs a separate update for this Ubuntu 26.04 VM.

## Current observations and providers

The [18 September snapshot](../implementation/CURRENT_STATE.md) records migration `0025`, six running services and certificate-verified readiness for both public APIs. Historical [first-start evidence](../../evidence/head-esx/2026-09-14/deployment.json) is narrower than the subsequent account, worker and media evidence in the [build ledger](../implementation/BUILD_STATUS.md).

LM Studio on model-host (`10.20.30.30:1234`) supplies Qwen3.8 27B; Fooocus and TRELLIS on media-worker (`10.20.30.20`, SSH `operator`) share a worker-managed GPU. Use **Workers** for service selection and queue controls. Do not independently start the two GPU services. Current provider verification and capability bindings are listed in the snapshot; installed code does not make an unconfigured capability available.

For read-only service inspection:

```bash
sudo docker ps --filter label=com.docker.compose.project=hearth-head
```

Only the edge publishes application ports (80/443/8443/8445). The native address-control supervisor is separate from the six containers. The 18 September review did not rerun inference, real sign-in, reboot or recovery acceptance.
