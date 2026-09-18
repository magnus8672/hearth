# Set up a fresh hearth VM from the ZIP

This package creates a **new farm**. The existing laptop farm, its accounts, chats, memory and provider settings remain on the laptop. The ZIP contains the head application, built browser apps, branded identity theme, database migrations, setup console and optional CPU audio installer. No laptop credentials, farm data, virtual disks, model weights or development environments are included.

This is an **online setup package** for Linux x86-64. First startup downloads pinned container images and builds locked server dependencies. Node, pnpm, QEMU, Go and the laptop's Python environment are not required on the VM. This is a development deployment package, not the future signed/offline appliance installer.

## Prepare the VM

Use Ubuntu 24.04 LTS, 4 vCPUs, 8 GiB RAM and at least 50 GiB disk. Expose the x86-64-v2 CPU feature baseline to the ESX guest. No GPU is needed for the head. Models can remain loaded on separate provider machines.

Install Python 3 and unzip (`sudo apt-get install python3 unzip`), then Docker Engine with Compose 2.24.4 or newer using [Docker's Ubuntu installation instructions](https://docs.docker.com/engine/install/ubuntu/). Enable Docker at boot. Use an account allowed to run Docker and use that same account for all hearth commands. `docker compose version` and `docker info` should work before continuing.

Assign a stable LAN address. If using a DNS name, configure it to resolve to the VM from every client. Allow TCP 443 (workspace), 8443 (administration) and 8445 (sign-in) from your client LAN through the VM/network firewall. Setup can use other ports, but it does not create DNS or firewall rules.

## Copy and start

Copy `hearth-vm.zip` and `hearth-vm.zip.sha256` to the VM. In the directory containing them:

```bash
sha256sum -c hearth-vm.zip.sha256
sudo install -d -o "$(id -un)" -g "$(id -gn)" /opt/hearth
unzip hearth-vm.zip -d /opt
cd /opt/hearth
python3 scripts/head.py configure
python3 scripts/head.py up
python3 scripts/head.py owner
```

Choose an unused directory for this fresh farm. Do not unpack it over an existing farm. The outer checksum detects transfer damage; it is not a release signature. `package-manifest.json` records every payload file's SHA-256 and length.

`configure` asks for the **workspace base URL**, for example `https://hearth.home.arpa` or `https://10.20.30.50:8444`. Use your actual VM address, not `localhost` or `0.0.0.0`. An omitted port means 443. The base URL must be an HTTPS origin without a path or credentials. For non-interactive configuration:

```bash
python3 scripts/head.py configure --base-url https://hearth.home.arpa
```

The head listens on **0.0.0.0**. The chosen name or IP drives the TLS certificate and browser, sign-in, client API and MCP URLs. Admin/sign-in use ports 8443/8445 by default. To choose all three, use `--ports ADMIN WORKSPACE IDENTITY` with three distinct ports; the middle one must match your base URL. After creating accounts, use [Administration address settings](../implementation/HEAD_ADDRESS_SETTINGS.md) to change the URL and rebuild certificates. Do not edit the private configuration by hand.

First startup can take several minutes while Docker builds the server, applies migrations, configures identity and issues certificates. The Owner console prompts for a username, display name, farm name and hidden password. In the browser, enroll an authenticator and save your recovery codes. The next users who register receive Member access.

## Trust and connect

Startup creates `.hearth/head/hearth-client-certificates.zip`. Copy **that certificate ZIP** back to your laptop over your trusted VM access path. It contains the public root in PEM/DER, the current public server chain, exact connection URLs and fingerprints. Compare the root fingerprint with the one printed in the VM console and import the root into the browser/client trust stores. There are no private keys in the certificate ZIP. Python and Node clients may need the root separately from browser trust.

Using the DNS example above:

| Purpose | Address |
|---|---|
| Workspace | `https://hearth.home.arpa` |
| Administration | `https://hearth.home.arpa:8443` |
| Client API base URL | `https://hearth.home.arpa/v1` |
| Shared MCP endpoint | `https://hearth.home.arpa/mcp` |
| Sign-in | `https://hearth.home.arpa:8445` |

In Administration, add each existing provider by its LAN URL, select its resident model, verify the required features and assign capabilities. Multiple servers of the same type and multiple targets per capability are supported. Plain HTTP on a private LAN requires explicit risk acceptance for that connection. A provider address such as `127.0.0.1` would point to the head container, not your laptop. Use the provider machine's LAN address even if it shares the VM with the head.

For Hermes, OpenClaw or an editor, create a scoped key under **Workspace → Client connections**. The `/v1/models` list contains capability aliases such as `auto` and `code.implement`. Supply your key and the `/v1` base URL to a Chat Completions-compatible client, and configure `/mcp` separately if needed. General harness compatibility still needs testing. The MCP manifest exposes `list_tools`, `describe_tool` and `run_tool`; administrators register upstream servers centrally.

## Optional speech and transcription

Skip this if you will use existing audio providers. To install the included CPU services on this VM or another Ubuntu 24.04 x86-64 VM, use the extracted package there as well:

```bash
sudo apt-get update
sudo apt-get install -y python3.12 python3.12-venv openssl pipx
pipx install uv==0.12.5
sudo python3 scripts/setup_audio_vm.py install \
  --uv "$HOME/.local/bin/uv" --address 10.20.30.50
```

Replace the example address with the audio VM's LAN name or IP. Reserve another 8 GB of disk for audio dependencies, models and caches. This explicitly downloads the pinned Kokoro and Whisper models, approximately 840 MB, plus their CPU dependencies. The installer creates separate systemd services that start at boot, verified HTTPS and private controller credentials. Its registration summary prints URLs and paths to the public CA and controller key files, never the secrets themselves. Retrieve the key contents privately and enter them in the head's Providers page, verify the services and assign Read aloud/Transcription. The default ports are 1236 and 1237; allow access from the head. Keep the audio secrets private. This installer does not install image/3D models or move existing workloads.

## Operation and backup

```bash
python3 scripts/head.py status
python3 scripts/head.py export-certificates
```

Docker restart policies resume services at VM boot. Re-running `up` rebuilds/applies this package and migrations; use it during maintenance. Only the HTTPS edge publishes ports. PostgreSQL, raw APIs, identity administration and reference tools remain private inside Compose.

Back up `.hearth/head/config.json` together with the Compose project's PostgreSQL, Caddy and memory-vault volumes. The default project is `hearth-head`. Configuration contains the farm identity and encryption keys needed for recovery. Restoring only the application ZIP does not restore a farm. Keep the current laptop farm separately; this package neither exports nor changes it.

This package is for a fresh farm. Existing-farm migration, signed distribution, full ESX qualification and all external agent/harness combinations remain separate work. Image editing, local 3D and the rest of the unfinished roadmap are not added by packaging.
