# hearth image provider

This experimental headless provider runs Stable Diffusion XL directly through Diffusers. It is the first local text-to-image implementation, separate from chat servers and graphical model tools. It does not implement the signed native worker installer, enrollment, remote supervision, image editing or 3D generation.

[Historical deployment inventory removed for repository privacy.]

## Installation on this development checkout

The reference machine has been prepared. Run these commands from the repository root, not from `docs/runtimes/`. For a fresh Windows environment:

```powershell
uv venv --python 3.12 .hearth/toolchains/image-runtime
uv pip install --python .hearth/toolchains/image-runtime/Scripts/python.exe torch==2.7.1 torchvision==0.22.1 --index-url https://download.pytorch.org/whl/cu128
uv pip install --python .hearth/toolchains/image-runtime/Scripts/python.exe -r runtimes/image/requirements-windows.txt
uv run python scripts/prepare_image_model.py --download
uv run python scripts/image_runtime.py start
uv run python scripts/image_runtime.py status
```

The explicit download fetches 6.94 GB from the [official SDXL base repository](https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0), pinned to revision `462165984030d82259a11f4367a4eed129e94a7b`. Every configuration, tokenizer and safetensors file has an exact byte count and SHA-256 in [the model manifest](../../runtimes/image/model-manifest.json). Its model card and license are included. No remote Python or pickle model file is loaded. The [Diffusers pipeline](https://huggingface.co/docs/diffusers/v0.35.0/en/using-diffusers/loading) uses the local FP16 files and CPU offload.

Startup verifies the model closure and binds only `127.0.0.1:1235`. It generates a controller key in ignored `.hearth/image-provider/controller.key`; it never prints that key or passes it on a process command line. Administration's provider type is **hearth image provider**, with model `stabilityai/stable-diffusion-xl-base-1.0`. Supply that controller key through the password field. Use the same resource group as LM Studio when both use the same GPU.

The development appliance has an explicit host-gateway alias for port 1235, just as it has for LM Studio on 1234. This does not expose the service to the LAN or qualify remote provider TLS. The launcher restarts this provider only if its local configuration already exists; it never implicitly installs weights.

## Job protocol and lifecycle

The versioned `ImageProviderInfo`, `ImageGeneration` and `ImageReceipt` contracts live in `services/api/src/hearth/contracts.py`, generating matching JSON Schema, Go and TypeScript. The reference launcher puts that source package on the isolated runtime's Python path. This shared source dependency must become a packaged contract dependency for standalone worker distribution.

Authenticated endpoints are `GET /v1/image-provider`, `POST /v1/image-jobs`, and `GET /v1/image-jobs/{id}`, with `/cancel` and `/image` operations. A request selects the fixed model profile, a bounded shape, 20/30/40 steps and an explicit seed. It cannot choose a script, arbitrary model path, output filename, URL or shell command.

SQLite records accepted jobs before execution. One process lock and one generation slot prevent overlapping jobs. Reusing an ID with identical input reads its receipt; changed input conflicts. A restart marks unfinished work interrupted and never replays it. Cancellation is scoped to the job and checked after each denoising step. A terminal receipt is published only after offloading and CUDA synchronization confirm release. A failed release holds admission until restart.

No model downloads occur during generation: loading requires local files, safetensors and offline Hugging Face/Transformers mode. This is an application-level restriction, not a claim of an OS egress firewall. The control plane verifies receipt identity, model profile, seed, settings, image digest, PNG decoding and dimensions before storing a private artifact. Direct browser access to the provider is rejected; the workspace reads images through its authenticated BFF.

## Storage and limits

Model files live in `.hearth/models`; the runtime environment, controller key, logs and SQLite/PNG jobs stay in `.hearth/`. The launcher restricts the provider state directory to the current OS user. Keep it private. The provider retains prompts and images for the trusted controller, while the BFF stores user-scoped records under forced PostgreSQL RLS. Farm administrators cannot read another user's images through the application; the host/runtime operator remains part of the trust boundary.

Limits are 2,000 runtime jobs, 100 image jobs per workspace, 16 MiB per returned PNG and a 15-minute controller deadline. The current SDXL tokenizer accepts up to its fixed token window; longer prompts fail with a request to shorten them rather than being silently truncated. The profile fixes CFG at 7 and has no refiner, LoRAs, upscaler or automatic prompt expansion. Saved seeds help repeat a configuration, but exact pixels across hardware/library changes are not guaranteed.

Fooocus was extracted to `C:\src\Fooocus-main` with its own environment for inspection. Its UI is not a dependency of this service. No Fooocus updater, public sharing link or certificate-verification override was used. Other engines can implement the job protocol or receive a dedicated adapter; image/3D stage boundaries remain described in ADR 0006.

Evidence: [GPU render](../../evidence/images/2026-09-13/sdxl-local-proof.json), [real HTTP cancellation and subsequent render](../../evidence/images/2026-09-13/image-provider-live.json), and [private BFF/database artifact persistence](../../evidence/images/2026-09-13/bff-live-image.json). Automated runtime unit tests use an explicit fake engine and do not require a GPU. Signed package activation, cross-machine operation, retention/deletion controls, crash injection and broad model quality suites remain open.
