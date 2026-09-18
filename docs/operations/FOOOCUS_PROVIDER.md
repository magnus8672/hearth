# Fooocus on media-worker

Prepared 17 September 2026 at the user's request. media-worker is the external image machine at `10.20.30.20`; the hearth head remains `10.20.30.10`. The user subsequently registered and assigned the provider through Administration. The [advanced settings update](../implementation/IMAGE_OPTIONS.md) requalified that existing target and preserved its assignments. The registration instructions below remain useful for another installation; do not add a duplicate to this farm.

## Register through Administration

Open [hearth Administration](https://hearth.example.invalid:8443), then Providers and Add server.

| Field | Value |
|---|---|
| Provider type | hearth image provider |
| Connection name | media-worker Fooocus |
| Server address | `http://10.20.30.20:1235/v1` |
| Model identifier | `fooocus/juggernaut-xl-v8` |
| Resource group | `media-worker GPU` |
| API key | Private controller key from the command below |

Accept the visible HTTP risk checkbox for this existing LAN application and confirm local processing. Save, verify images, then assign the model to Image generation. This is the existing per-connection HTTP exception, not a change to managed-worker TLS policy. The adapter accepts connections only from the head IP and loopback, requires its bearer key and rejects browser Origin requests. It ignores forwarded client-address headers. HTTP still transmits prompts, images and that credential without transport encryption.

From Windows PowerShell, copy the key directly to the clipboard and paste it into the password field:

```powershell
ssh operator@10.20.30.20 "cat /var/lib/hearth-fooocus/controller.key" | Set-Clipboard
```

Use the same resource group for future image/3D services sharing this GPU. Separate physical GPUs should have separate groups. hearth cannot reserve VRAM against applications used outside its scheduler.

## What is running

- Fooocus 2.5.5 in `/opt/Fooocus-main`, using its existing `fooocus_env` Python 3.12 environment and Juggernaut XL v8 safetensors checkpoint. No replacement model or 3D stack was downloaded.
[Historical deployment inventory removed for repository privacy.]
- The `fooocus.service` systemd unit runs as `operator`, starts on boot and restarts on failure. The existing account now has a validated passwordless sudo rule in `/etc/sudoers.d/90-hearth-operator`. Subsequent maintenance uses this account; existing SSH keys were preserved.
- The adapter at `/opt/hearth-fooocus` exposes the existing `hearth.image.v1` job contract on `0.0.0.0:1235`. Its private configuration, model/source inventory, key and jobs live under `/var/lib/hearth-fooocus` (directory mode 0700, key 0600).
- The graphical Fooocus UI listens at `127.0.0.1:7865`. It shares the worker/model with the adapter, so it is not a second inference process. From another computer use `ssh -L 7865:127.0.0.1:7865 operator@10.20.30.20`, then open `http://127.0.0.1:7865` while that SSH session remains connected.
- The existing ComfyUI Desktop process and its files were left running and unchanged. There is no farm-wide capacity coordination for jobs launched directly in either graphical UI.

The initial failure was Gradio 3.41.2 calling the legacy positional Starlette template API after FastAPI 0.141.1 / Starlette 1.6.0 had been installed. The [compatibility overlay](../../runtimes/image/requirements-fooocus.txt) pins FastAPI 0.115.14 and Starlette 0.46.2. Existing Torch 2.14.0+cu130 and torchvision 0.29.0+cu130 were retained and exercised on the real GPU. `pip check` passes.

The [preparation helper](../../runtimes/image/prepare_fooocus.py) backs up and applies a bounded patch to the existing Fooocus worker: task-scoped cancellation during sampling, a ready signal, failure tracking, and completion acknowledgment after worker cleanup and CUDA synchronization. It also removes the upstream launcher's global certificate-verification override. Original files and the pre-change dependency freeze are in `/var/backups/hearth-fooocus`; subsequent worker backups are in `/opt/Fooocus-main/hearth-backups`.

The [adapter](../../runtimes/image/fooocus_bridge.py) retains a fixed checkpoint and single-image jobs. Its verified profile now advertises five aspect ratios, original/2K/4K output, 20/30/40/60 passes, installed styles, guidance and sharpness. See [exact dimensions and behavior](../implementation/IMAGE_OPTIONS.md). Unspecified styles and sampling values use Fooocus's defaults; the existing offset LoRA is retained. Refiner, diffusion enhancement and image-input modes remain disabled for API jobs. Larger output uses the existing Fooocus learned upscaler inside the same worker, before its CUDA release acknowledgment. Wildcard and LoRA directives in remote prompts remain rejected. The local source/config/model inventory is checked at startup. This inventory detects changes to operator-supplied files; it does not attest an upstream signed model release. Model downloads and the automatic updater are not used in the request path. Required files must already exist; Hugging Face operates offline.

The existing durable image-job store provides bounded admission, duplicate-ID handling, status, digest-bound PNG retrieval and restart interruption. A cancellation does not release capacity until the worker acknowledges completion. Uncertain execution holds capacity until restart. The checkpoint stays loaded rather than being evicted after each request; Fooocus can still move components within its pipeline as VRAM requires. Temporary Fooocus outputs are removed after collection or cancellation, and the adapter retains its authenticated job artifacts. Existing retention limits are described in [the image provider guide](../runtimes/IMAGE_PROVIDER.md).

## Maintain and reproduce

```sh
ssh operator@10.20.30.20
sudo systemctl status fooocus
sudo journalctl -u fooocus -n 80 --no-pager
sudo systemctl restart fooocus
```

Source files deployed in `/opt/hearth-fooocus` are `hearth_image.py`, `fooocus_bridge.py` and `prepare_fooocus.py` from `runtimes/image`, plus `hearth/contracts.py`, `hearth/image_settings.py` and `hearth/__init__.py` from `services/api/src`. The [service template](../../runtimes/image/fooocus.service) captures this machine's paths. This is a prepared external-install adapter, not a general GPU/bootstrap installer or signed enrolled worker.

For larger output, provision the upscaler once during setup while Fooocus is stopped, before generating the inventory. media-worker already has this file. This is the [upstream Fooocus upscaler](https://huggingface.co/lllyasviel/misc/tree/71f7a66a7affe631c64af469fe647217d422cac0), pinned to the recorded repository revision and SHA-256. It is 33,636,613 bytes. Downloading is explicit setup work, never triggered by a user's image request:

```sh
cd /opt/Fooocus-main
mkdir -p models/upscale_models
curl --fail --location --proto '=https' --proto-redir '=https' \
  --output models/upscale_models/fooocus_upscaler_s409985e5.bin.download \
  https://huggingface.co/lllyasviel/misc/resolve/71f7a66a7affe631c64af469fe647217d422cac0/fooocus_upscaler_s409985e5.bin
printf '%s\n' 'b2a66d21d2e44d2b59c53414419279763a423a61f05bc43d7c24e0489aeca5a3  models/upscale_models/fooocus_upscaler_s409985e5.bin.download' | sha256sum --check --status && \
  mv models/upscale_models/fooocus_upscaler_s409985e5.bin.download models/upscale_models/fooocus_upscaler_s409985e5.bin
```

For a deliberate, reviewed update, stop the service first, preserve the private state, apply the dependency overlay in Fooocus's environment and run:

```sh
/opt/Fooocus-main/fooocus_env/bin/python /opt/hearth-fooocus/prepare_fooocus.py \
  --fooocus /opt/Fooocus-main --manifest /var/lib/hearth-fooocus/manifest.json
sudo systemctl start fooocus
```

Do not regenerate the inventory merely to suppress an unexplained integrity error. Review changes first. If moving the head, update the exact controller IP allowlist in the private `config.json` and restart this service.

## Evidence and remaining work

[Live evidence](../../evidence/images/2026-09-17-fooocus/live.json) records a request through the real head API container's image transport without registering a farm provider: authenticated LAN connectivity, missing-key/Origin/body-limit rejection, busy admission, cancellation after sampling began, confirmed release, then a successful 1024×768 render in 7.4 seconds. The transport validated the PNG digest and dimensions. A separate 1024×1024 render took 12.05 seconds. These are single-run observations, not benchmarks. The actual image was visually inspected.

The initial eleven focused runtime/adapter/transport tests passed in a disposable process on the existing head VM, with no database or extra farm. The graphical UI returned HTTP 200, service restart retained receipts, and the unit is enabled for boot; a physical reboot has not been tested. The user subsequently registered and assigned the provider.

The [advanced-options evidence](../../evidence/images/2026-09-17-options/live.json) adds real 3840 × 2160 output in 13.22 seconds, 4096 × 4096 output in 23.01 seconds and cancellation during finishing with confirmed capacity release. The square PNG was 21.6 MB, exceeding the old artifact cap; the current head/runtime allow 64 MiB. The reviewed inventory digest is `ea873178e294a4b350cbe2f6e215f34bcb1b238ab41124bb1ae6b4304e6d4397`. Fifty-five VM tests and two deployed-bundle browser fixtures pass. See [qualification boundaries](../implementation/IMAGE_OPTIONS.md#observed-validation). No 3D stack was installed or qualified, and none of the 61 full release gates changes status.
