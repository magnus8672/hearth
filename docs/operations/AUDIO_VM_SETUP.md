# CPU audio providers on a VM

The speech and transcription providers can run in the head VM or on a separate CPU VM. The head only routes requests to their saved addresses. They do not require the laptop, a GPU, GPU passthrough, LM Studio or the image provider. Give speech and transcription separate resource groups so they can run concurrently with each other and the GPU specialists.

The [setup script](../../scripts/setup_audio_vm.py) supports Ubuntu 24.04 x86-64, Python 3.12 and systemd. An initial sizing suggestion is four vCPUs, 8 GB RAM and at least 8 GB free disk for audio installation and its caches. Reserve additional capacity for the control stack if it shares this VM. Actual ESX hardware sizing and whole-farm migration remain to be tested.

## Install

Create the Ubuntu VM in ESX, give it a stable private address or DNS name, and copy the hearth source checkout to `/opt/hearth`. Do not copy Windows virtual environments. Install the prerequisites inside the guest:

```bash
sudo apt-get update
sudo apt-get install -y python3.12 python3.12-venv openssl pipx
pipx install uv==0.12.5
cd /opt/hearth
sudo python3 scripts/setup_audio_vm.py install --uv "$HOME/.local/bin/uv" --address 10.20.30.50
```

Replace `10.20.30.50` with the actual VM address. This is an explicitly requested preparation operation: it downloads the locked Python dependencies and approximately 840 MB of digest-pinned Kokoro/Whisper model files. Normal service startup does not download anything. Source files stay under `/opt/hearth`; models, job receipts and per-provider credentials live under `/var/lib/hearth-audio`. Private CA material is root-only under `/etc/hearth-audio`.

The installer creates an unprivileged `hearth-audio` service account, separate systemd services, independent controller keys and a private CA with HTTPS certificates. Both services are enabled at boot and restart after process failure. They listen on HTTPS ports 1236 and 1237, reject unapproved Host headers and browser Origins, and disable outbound Python socket connection calls during inference. Their configured systemd restrictions supplement that guard, but do not establish OS-level network egress attestation. Permit only your head's network path to those ports in your existing network/firewall policy; this script does not alter that policy.

Certificates are checked daily and renewed under the same CA when fewer than 30 days remain. Renewal restarts the two audio processes. A job interrupted by restart keeps its durable receipt and is never replayed automatically. The private CA lasts ten years; CA rotation and automated fleet-wide trust replacement remain future managed-worker work.

Rerunning the installer preserves credentials, CA identity, model files and job stores, and does not restart already-running inference. After an intentional source/dependency upgrade, restart the two services during an idle period. The first installer refuses a conflicting saved VM address instead of silently changing certificate identity.

## Register with the head

The installer prints a registration summary with file paths, never the controller secrets. The same summary is in `/var/lib/hearth-audio/registration.json`.

In Administration, add each service independently:

| Setting | Speech | Transcription |
|---|---|---|
| Type | hearth speech provider | hearth transcription provider |
| Address | `https://10.20.30.50:1236` | `https://10.20.30.50:1237` |
| Model | `kokoro-82m-v1.0-onnx` | `faster-whisper-small.en` |
| API key file | `/var/lib/hearth-audio/speech/controller.key` | `/var/lib/hearth-audio/transcription/controller.key` |
| Provider CA file | `/var/lib/hearth-audio/provider-ca.crt` | `/var/lib/hearth-audio/provider-ca.crt` |
| Resource group | VM speech CPU | VM transcription CPU |
| Capability | Speech output | Speech input |

Use a privileged local session to retrieve the key contents privately and paste them into the corresponding API key field. Paste the public CA certificate into each provider's trusted CA field. Do not paste the CA private key. Run the initial full capability verification, then assign the capabilities to these targets. [Successful qualification now persists](../implementation/PROVIDER_LIFECYCLE.md); there is no hourly renewal chore.

If the head runs in Docker on this same VM, still use the VM address in the table. `127.0.0.1` inside a container points at that container. The laptop's QEMU `10.0.2.2` development aliases are not a migration mechanism.

Existing text/image providers remain on their existing machines. Change capability assignments when you are ready to use the VM audio services; the installer never changes them for you.

## Check or recover

```bash
sudo python3 /opt/hearth/scripts/setup_audio_vm.py status
systemctl status hearth-speech hearth-transcription
sudo journalctl -u hearth-speech -u hearth-transcription -n 50 --no-pager
```

On an idle qualification VM, test real synthesis, transcription, TLS, rejected untrusted requests and durable receipts across service restart:

```bash
sudo python3 /opt/hearth/scripts/qualify_audio_vm.py --restart
```

This uses a synthetic English phrase, not microphone input or private chat content. It deliberately restarts only the two audio services. Broader language/accent/quality evaluation and noisy physical microphones remain separate tests. Speech currently uses the `af_heart` stock voice; transcription is English-only with a two-minute input limit.

## Moving the head is a separate operation

This installs the audio capability providers. A fresh head can now run directly on a LAN VM using [head VM setup](HEAD_VM_SETUP.md), with its public DNS/IP address and identity origins configured together. Moving an existing farm still requires preserving and restoring its PostgreSQL data, Keycloak database, farm ID, session/credential encryption key, OIDC client secrets, Caddy/step-ca state and current trust material. Keep provider job stores and their credentials if migrating those services too. Do not create a replacement farm or generate new encryption keys over existing data.

The current developer stack and launcher still assume localhost origins and the WHPX appliance. A supported whole-head ESX migration script, restore drill, production bootstrap and signed managed-worker enrollment remain open roadmap work. This recipe has actual Ubuntu guest qualification, including service restarts, but has not been run on your ESX host. The setup downloads model files from the pinned [Kokoro release](https://github.com/thewh1teagle/kokoro-onnx/releases/tag/model-files-v1.0) and [Whisper revision](https://huggingface.co/Systran/faster-whisper-small.en/tree/d1d751a5f8271d482d14ca55d9e2deeebbae577f), checking the repository manifests before loading them.
