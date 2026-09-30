# Run the hearth head on a LAN VM

> Addresses, host labels and accounts shown here are illustrative placeholders. Use your own private deployment configuration.

The standalone head profile listens on **0.0.0.0** and accepts your public **workspace base URL** during setup. Its hostname/IP determines the server certificate, while its port determines where the workspace, client API and MCP listen. Your laptop's browser, Hermes, OpenClaw and editor clients use that address. `0.0.0.0` is a listening address; it is never a browser URL or certificate identity.

This runs the current application directly in Docker Compose on Linux. It does not require the Windows launcher or its QEMU appliance. The signed product installer and migration of an existing farm remain separate work.

## Prepare a fresh VM

Use Ubuntu 24.04 LTS on an x86-64 VM with the x86-64-v2 CPU baseline, 4 vCPUs, 8 GiB RAM and at least 50 GiB disk for source builds and state. The head does not need a GPU. Give it a stable address or a DNS name that resolves to its LAN address from every client. Keep models resident on their existing provider machines.

Install Python 3 and Docker Engine with Compose **2.24.4 or newer**. Use [Docker's Ubuntu installation instructions](https://docs.docker.com/engine/install/ubuntu/). Enable Docker at boot and use an account allowed to run Docker. The helper never changes the VM's network or firewall configuration.

Use the small [fresh-farm VM ZIP](VM_PACKAGE.md), which already includes both built browser bundles. To prepare it from this checkout, run `pnpm build` then `python scripts/package_head.py`; the outputs are `dist/hearth-vm.zip` and its SHA-256 file. The package allowlists application/setup inputs and excludes current farm state, models and development environments. The runtime image builds its own locked Python dependencies on the VM; it does not use the laptop's virtual environment. First setup needs internet access.

For a fresh farm, exclude `.hearth/`, `.venv/`, `node_modules/`, `.git/`, model files and any private `.env` files from the copy. Do not put fresh configuration over an existing farm's databases or encryption keys.

From the repository root on the VM, enter the URL your clients will use:

```bash
cd /opt/hearth
python3 scripts/head.py configure --base-url https://hearth.home.arpa
python3 scripts/head.py up
python3 scripts/head.py owner
```

Running `python3 scripts/head.py configure` without an address opens an interactive base URL prompt. For a VM IP and the earlier workspace port, enter `https://10.20.30.50:8444`. A URL without a port uses standard HTTPS port **443**. A trailing slash is accepted and normalized. Use an HTTPS origin, without credentials, a path such as `/v1`, a query or a fragment. DNS names need an A record resolving to the VM; setup does not create DNS records.

Administration and sign-in keep ports 8443 and 8445 by default, on the same name/IP. The helper prints all URLs. First startup builds the pinned images, applies database migrations, configures branded identity, issues the matching certificate and exports the client certificate package. Owner creation happens through the local console, with a hidden password prompt. Sign in through the browser to enroll your authenticator and save recovery codes. Subsequent browser registrations receive Member access.

Private configuration is saved at `.hearth/head/config.json`, with owner-only Linux permissions. Rerunning an equivalent URL preserves credentials and farm identity. An address, port or project change is rejected instead of silently changing the issuer for existing accounts. Optional `--ports 9443 443 9445` sets the admin, workspace and identity ports together; choose three distinct ports from 1 to 65535, with the middle port matching the base URL. The earlier `--host 10.20.30.50` form remains supported and retains its default workspace port 8444. Use the same account and state directory for every command.

## Connect from your laptop

| Purpose | Example address |
|---|---|
| Administration | `https://hearth.home.arpa:8443` |
| Workspace | `https://hearth.home.arpa` |
| Sign-in service | `https://hearth.home.arpa:8445` |
| Client API base URL | `https://hearth.home.arpa/v1` |
| Shared MCP endpoint | `https://hearth.home.arpa/mcp` |

Allow the three configured TCP ports from your client LAN through your VM/network firewall. Only the HTTPS edge publishes ports. PostgreSQL, raw application listeners, Keycloak's administration endpoints and the reference tool service have no published ports in this profile. The development maintenance forwards are removed by the override. Use the VM address when registering providers too, even when a provider runs on the same VM: container `localhost` refers to that container.

Caddy creates and renews HTTPS certificates whose Subject Alternative Name matches the base URL's DNS name or IP address. Startup exports `.hearth/head/hearth-client-certificates.zip`, containing:

- `hearth-root.crt`: the public root certificate in PEM format, suitable for CA bundles.
- `hearth-root.cer`: the same public root in DER format, suitable for certificate import.
- `hearth-server-chain.pem`: the current public server certificate and intermediate chain.
- `connection.json`: the exact workspace/admin/identity/API/MCP URLs, server name and certificate SHA-256 fingerprints.
- `README.txt`: trust and connection instructions.

The ZIP contains no private keys, account passwords, client API keys or farm credentials. Copy it to your laptop over your trusted VM access path and compare its root fingerprint with the one printed in the VM console. Import the root into the browser and client runtimes; browser trust and Python/Node trust may be separate. Trust the root rather than pinning the short-lived server certificate. The standalone PEM also remains at `.hearth/head/hearth-root.crt`. Re-export either form as needed:

```bash
python3 scripts/head.py export-certificates
python3 scripts/head.py export-ca
openssl x509 -in .hearth/head/hearth-root.crt -noout -fingerprint -sha256
```

In **Workspace → Client connections**, create a scoped key. Use the printed `/v1` base URL and a capability alias such as `auto` or `code.implement`; register and verify providers and assign those capabilities first. Configure MCP separately with the `/mcp` endpoint and a key allowing shared tools. See [shared tools and client configuration](../implementation/SHARED_TOOLS_AND_CLIENT_API.md) for the compatibility profile and harness examples.

For a Python client, supply the root to its HTTP transport, for example `httpx.Client(verify=ssl.create_default_context(cafile="hearth-root.crt"))`. Node clients can receive the public root through `NODE_EXTRA_CA_CERTS`. Keep certificate verification enabled.

## Operation and existing data

```bash
python3 scripts/head.py status
python3 scripts/head.py up
```

Services use Docker restart policies and resume when Docker starts. `up` applies this checkout's build and migrations, so use it during an idle maintenance period after a backup. It does not load provider models, move their workloads or reassign capabilities. Speech/transcription can live on this or another VM using [audio VM setup](AUDIO_VM_SETUP.md).

Keep `.hearth/head/config.json` and the Compose project's PostgreSQL, Caddy and memory-vault volumes together in backups. Configuration contains the farm ID, database/identity credentials and encryption key required to recover existing data. Do not regenerate it as a recovery procedure. The default Compose project is `hearth-head`, separate from `hearth-development`.

**Moving the current laptop farm is not the same as creating a fresh VM farm.** Preserving its accounts, conversations, memory, provider approvals and credentials requires a coordinated database/volume/secret restore and identity-address migration. That Move hearth workflow and old-head fencing are not implemented here. The new profile does not alter the current laptop deployment.

## Verification boundary

The LAN profile is qualified separately from the current development farm. Its evidence covers a fresh Linux Compose startup, merged and actual published-port inspection, certificate-verified access from a separate container through the VM's non-loopback address, public sign-in URLs and branded return links, and API/MCP authentication boundaries. The [base URL follow-up](../../evidence/head-lan/2026-09-14-base-url/validation.json) additionally checks actual DNS-name certificate SANs, HTTPS port 443, matching certificate-package contents and 74 targeted tests on Windows/Linux. See the [current build ledger](../implementation/BUILD_STATUS.md) for the recorded results. A physical ESX deployment and full Hermes/OpenClaw/Continue acceptance remain to be tested.

The configuration follows [Compose's explicit port replacement rules](https://docs.docker.com/reference/compose-file/merge/), [Caddy's listener and default-SNI settings](https://caddyserver.com/docs/caddyfile/options), and [Keycloak's public hostname configuration](https://www.keycloak.org/server/hostname). IP clients that omit SNI still receive the configured head certificate. Browser origins, client metadata, trusted hosts, OIDC redirects and theme return links all use the same saved address.

## Change the address after setup

Use [Administration → Settings → Address & certificates](../implementation/HEAD_ADDRESS_SETTINGS.md) to preview and apply a new base URL. The local supervisor preserves the trust root and existing accounts, updates sign-in bindings, rebuilds the public certificate package and attempts rollback if checks fail. Browser sessions end during the change. Install the supervisor with `sudo python3 scripts/head.py install-control` on an updated existing systemd deployment.
