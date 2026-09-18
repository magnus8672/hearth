# Fooocus on media-worker

Prepared 17 September 2026 at the user's request. media-worker is the external image machine at `10.20.30.20`; the hearth head remains `10.20.30.10`. The provider is ready for manual registration through Administration. No provider record, capability assignment or account was created by this setup. The user will test that workflow.

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

The [adapter](../../runtimes/image/fooocus_bridge.py) fixes checkpoint, single-image count, dimensions, seed and 20/30/40 steps; refiner, enhancement and image-input modes are disabled for API jobs. Fooocus's default styles, expansion and existing offset LoRA are retained. Wildcard and LoRA directives in remote prompts are rejected. The local source/config/model inventory is checked at startup. This inventory detects changes to operator-supplied files; it does not attest an upstream signed model release. Model downloads and the automatic updater are not used in the request path. Required files must already exist; Hugging Face operates offline.

The existing durable image-job store provides bounded admission, duplicate-ID handling, status, digest-bound PNG retrieval and restart interruption. A cancellation does not release capacity until the worker acknowledges completion. Uncertain execution holds capacity until restart. The checkpoint stays loaded rather than being evicted after each request; Fooocus can still move components within its pipeline as VRAM requires. Temporary Fooocus outputs are removed after collection or cancellation, and the adapter retains its authenticated job artifacts. Existing retention limits are described in [the image provider guide](../runtimes/IMAGE_PROVIDER.md).

## Maintain and reproduce

```sh
ssh operator@10.20.30.20
sudo systemctl status fooocus
sudo journalctl -u fooocus -n 80 --no-pager
sudo systemctl restart fooocus
```

Source files deployed in `/opt/hearth-fooocus` are `hearth_image.py`, `fooocus_bridge.py` and `prepare_fooocus.py` from `runtimes/image`, plus `hearth/contracts.py` and `hearth/__init__.py` from `services/api/src`. The [service template](../../runtimes/image/fooocus.service) captures this machine's paths. This is a prepared external-install adapter, not a general GPU/bootstrap installer or signed enrolled worker.

For a deliberate, reviewed update, stop the service first, preserve the private state, apply the dependency overlay in Fooocus's environment and run:

```sh
/opt/Fooocus-main/fooocus_env/bin/python /opt/hearth-fooocus/prepare_fooocus.py \
  --fooocus /opt/Fooocus-main --manifest /var/lib/hearth-fooocus/manifest.json
sudo systemctl start fooocus
```

Do not regenerate the inventory merely to suppress an unexplained integrity error. Review changes first. If moving the head, update the exact controller IP allowlist in the private `config.json` and restart this service.

## Evidence and remaining work

[Live evidence](../../evidence/images/2026-09-17-fooocus/live.json) records a request through the real head API container's image transport without registering a farm provider: authenticated LAN connectivity, missing-key/Origin/body-limit rejection, busy admission, cancellation after sampling began, confirmed release, then a successful 1024×768 render in 7.4 seconds. The transport validated the PNG digest and dimensions. A separate 1024×1024 render took 12.05 seconds. These are single-run observations, not benchmarks. The actual image was visually inspected.

Eleven focused runtime/adapter/transport tests passed in a disposable process on the existing head VM, with no database or extra farm. The graphical UI returned HTTP 200, service restart retained receipts, and the unit is enabled for boot; a physical reboot has not been tested. User registration, capability assignment and chat use through Administration are deliberately pending. No 3D stack was installed or qualified, and none of the 61 full release gates changes status.
