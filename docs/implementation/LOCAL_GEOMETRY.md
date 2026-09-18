# Local image-to-3D generation

Implemented on the existing head and media-worker, 17 September 2026. The original runtime is [trellis.cpp v0.6.0](https://github.com/pwilkin/trellis.cpp/releases/tag/v0.6.0), executing TRELLIS.2 with the pinned Q8 GGUF profile. This replaces the earlier TripoSR candidate for this deployment, without tying the geometry protocol to one engine.

## Try it

Open **3D models** in the workspace. Enter a model name, upload a still PNG, JPEG or WebP of one clearly visible object, choose a 3D provider and its supported detail (TRELLIS: 512/1024; Hunyuan3D 2.0: 512), and select **Create 3D model**. Alternatively, choose **Make a model** beside a completed image in the gallery, private chat or a joined channel. The 3D form opens with that image selected and previewed. Enter a name, choose the detail and select **Create 3D model** to start work; opening the form alone never generates a model.

### Hunyuan3D 2.0 profile

The alternative is the original [Tencent Hunyuan3D 2.0](https://github.com/Tencent-Hunyuan/Hunyuan3D-2) shape-and-paint pipeline, model ID `hunyuan3d/2.0`, at 512 geometry detail. It does not select 2.1 or a turbo checkpoint. The checked-in [inventory](../../runtimes/hunyuan/inventory.json) pins upstream source `f8db63096c8282cb27354314d896feba5ba6ff8a`, model revision `9cd649ba6913f7a852e3286bad86bfa9a2d83dcf`, every required weight including background removal, and CUDA build tools. Python dependencies are hash-locked. Preserve upstream licenses and notices; downloaded weights and binaries stay outside Git.

On media-worker, the two geometry providers and Fooocus share `media-worker GPU`. Owner fairness selects the next job before its stored target selects the backend. The worker stops every other approved service and confirms its cgroup has exited before starting Hunyuan, TRELLIS or Fooocus. A selected Hunyuan job is never silently converted into a TRELLIS job. Failed readiness or generation remains a visible failure; unknown execution continues to hold capacity. Independent future hosts should use separate provider connections and resource groups so they can run concurrently.

[Historical deployment inventory removed for repository privacy.]

The installer leaves the new service stopped for reviewed adoption:

```sh
sudo python3 scripts/install_geometry_provider.py --backend hunyuan --user YOUR_RUNTIME_USER --host GPU_LAN_IP --controller HEAD_LAN_IP
```

Defaults are `/opt/hearth-hunyuan`, `/var/lib/hearth-hunyuan`, HTTPS port `1238` and authenticated loopback health port `1239`. Use Python 3.12 and a C++ build toolchain on the Linux CUDA host. Installation downloads about 13.6 GiB of pinned models, prepares a private virtual environment and builds the reviewed rasterizer/mesh extensions; it never starts inference. Register `https://GPU_LAN_IP:1238/v1`, model `hunyuan3d/2.0`, with its private controller key and public CA. Include the runner, adapter, contract/validation modules, unit, configuration, dependency lock and model/engine inventories in the signed recipe. The health assertion is `protocol=hearth.geometry.v1`. Follow the pause/drain/adoption procedure below, then run the real geometry probe and add the target to the geometry capability. A fresh second-host installation and wider hardware/quality matrix remain unqualified.

### References and saved models

Saved-image handoff uses the existing authorized image endpoint and prepares a JPEG reference copy with a maximum 1600-pixel edge. This includes 4K PNGs larger than the manual upload limit; the saved original is unchanged. Only a source kind and image UUID appear in the link, never arbitrary URLs or image data. Unavailable images leave generation disabled. A channel image produces a model in the requesting member's private workspace, not a shared channel artifact. Browser qualification is recorded in [handoff evidence](../../evidence/geometry/2026-09-18/image-handoff.json).

Reference files may be up to 8 MiB. Both Caddy templates and the BFF permit a 12,100,000-byte JSON envelope for `POST /api/v1/geometry`, including base64 overhead; ordinary requests retain their 1 MiB limit. An upload regression originally left the edge at 1 MiB, producing an empty HTTP 413 that the UI misreported as a JSON parse error. The corrected client preserves structured API errors and supplies readable messages for empty or non-JSON failures. [Upload correction evidence](../../evidence/geometry/2026-09-18/upload-fix.json) includes real edge boundary checks, a large valid PNG through the BFF, and browser error fixtures.

New jobs require a model name (1–120 characters after trimming whitespace), enforced in both the form and API. Cards show this name at the top, with the provider model, seed, detail, triangle count and size beneath it. **Rename** works on existing and new jobs without rerunning generation. Model names remain private catalog metadata and are not sent to the GPU provider.

New cards retain a static **Reference image** thumbnail, up to 320 pixels on either edge and 512 KiB, generated from the normalized upload with metadata removed. It identifies the source image, not a rendered view of the resulting mesh. The thumbnail remains after generation; the full generation input is still discarded. Migration `0026` adds nullable catalog fields without changing existing artifacts or RLS. Older jobs show an ID-based title until renamed, and an explicit missing-preview placeholder because their completed source images were already discarded. No old source images or names are guessed.

Thumbnail reads and rename writes require the geometry capability and owner/farm scope; rename also requires CSRF protection. Deletion clears the catalog name and thumbnail along with the artifact. The thumbnail response is private and `no-store`. Catalog validation is recorded in [the 18 September evidence](../../evidence/geometry/2026-09-18/catalog-validation.json).

**Preview 3D** supports orbit, zoom and pan. **Save GLB** exports the mesh and embedded PNG textures. Cancel works both in the queue and during generation. **Delete model** removes the head's saved artifact and reference. Provider caches and backups are separate retention domains, as with image deletion.

media-worker's worker is configured in explicit **shared GPU** mode. Geometry jobs and image requests from the gallery, private chat, and shared channels share one durable queue and one exclusive GPU reservation. A service change waits for the previous process/cgroup to finish. The head checks the new service's qualified manifest before dispatch. The last used service remains selected until another queued job needs a different approved service. Distributed, concurrently resident specialists on independent machines remain the farm default.

## Boundaries

- `hearth.geometry.v1` is a separate typed protocol: provider information, idempotent submit, poll, cancel and GLB collection. It is not an OpenAI image endpoint.
- The native worker controls the signed service recipe. A small unprivileged Python adapter owns a fixed native CLI invocation with typed seed/detail arguments. No request supplies a shell command, executable, output path or download URL.
- media-worker listens on HTTPS `10.20.30.20:1236`, with a private CA registered on its head connection and a controller-scoped key. Only the head address and loopback are accepted. An authenticated loopback-only health listener serves the worker; it cannot execute jobs.
- Engine archive and model digests are pinned in [the inventory](../../runtimes/geometry/inventory.json). The signed recipe binds the adapter, configuration and engine/model inventories. The adapter verifies the engine and weights before becoming healthy. Runtime inference does not download models.
- Cancellation kills the CLI process group and reaps the native process before reporting execution released. systemd `KillMode=control-group` and `ExitType=cgroup` fence restart and service switching. Interrupted requests are never replayed automatically.
- PostgreSQL migration `0024` preserves existing image queue rows while extending `capability_queue` with generated, foreign-key-checked image/geometry references. Queue metadata contains no image bytes. Geometry content has forced owner-and-farm RLS, including against farm administrators.
- Queue admission retains eight waiting/active jobs per owner, 64 per GPU, owner fairness and a 30-minute waiting deadline. The geometry CLI has a 20-minute execution limit. The gallery retains at most 50 nondeleted models per owner; the provider stops accepting work at 1,000 retained job records until operator maintenance.
- GLBs are bounded to 64 MiB, one million triangles and eight embedded PNG textures up to 4096 pixels. Validation checks container sizes, accessor/index bounds, finite vertex values and scene cycles. External resources, animations, skins and extensions are rejected. The preview uses bundled Three.js, with no remote texture fetches; same-origin blob access is permitted for embedded textures.

## Observed qualification

[Historical deployment inventory removed for repository privacy.]

A real BFF test on isolated VM PostgreSQL storage completed two textured GLBs, cancelled one waiting request and one active generation, reused the GPU after cancellation, downloaded and validated the result, and deleted it. The existing live farm's accounts and artifacts were not test fixtures. Actual signed-worker selection of TRELLIS and restoration of Fooocus also passed. Mixed image/geometry scheduling and service readiness have a separate database fixture; multi-user live mixed-load acceptance is still open.

The deployed browser bundle rendered the actual generated mesh with embedded color textures. Additional fixtures cover upload, cancellation, deletion, mobile width, and worker controls. See [the evidence](../../evidence/geometry/2026-09-17/validation.json).

## Remaining scope

Text/chat-to-3D chaining, channel/shared model artifacts, rigging, animation, mesh editing, texture/material controls, measured physical scale, independent Blender import, automatic model fit decisions, sustained multi-user stress and additional hardware are not qualified. The generated object has inferred hidden surfaces and normalized scale; set its real-world dimensions in your editor. The full P8/E19/A12 release requirements remain open.

This remains console-approved worker adoption. Automatic enrollment/mTLS, certificate renewal, signed package distribution and GUI recipe installation are separate work. The setup CA lasts ten years and the service certificate one year; renewal requires an operator update before expiry.

## Operator installation and updates

The current installation is `/opt/hearth-trellis`, with private configuration under `/var/lib/hearth-trellis`. The service is `hearth-trellis.service`, managed by `hearth-worker.service`; do not enable it independently alongside Fooocus. Unmanaged Fooocus/ComfyUI jobs remain outside this queue.

For another reviewed Ubuntu 24.04 CUDA machine with Python 3.12, its NVIDIA driver, OpenSSL, curl and Python venv support already installed, copy this source tree and run:

```sh
sudo python3 scripts/install_geometry_provider.py --user YOUR_RUNTIME_USER --host GPU_LAN_IP --controller HEAD_LAN_IP
```

The script downloads the digest-pinned archive and approximately 9.3 GiB of Q8 weights, installs hash-locked Python dependencies, creates private TLS and leaves the service stopped. It refuses to overwrite an existing private configuration. This reusable installer follows the steps used on media-worker; a second fresh-machine install has not been qualified.

Register `https://GPU_LAN_IP:1236/v1`, model `trellis2/q8`, protocol **hearth geometry provider**, using the public CA and controller key from that machine. Place it in the same resource group as any engine sharing its GPU. Do not run a generation probe until the GPU is free and the approved service is selected.

For an existing worker recipe update, pause admission, wait for active work to release, unload its selected service, and stop the worker supervisor. After its last report is at least 30 seconds old, use the head's console tool:

```sh
sudo python3 scripts/adopt_worker.py --inventory /private/reviewed-inventory.json --output /private/new-worker-bundle --existing-bundle /private/previous-worker-bundle
```

Include all services sharing the GPU in the reviewed inventory. Include each unit, adapter module, configuration, requirements, model inventory and engine inventory in the approved file map. Copy the resulting private bundle to `/etc/hearth-worker` over trusted SSH, preserve root-only permissions, start the supervisor, select the service and verify it in Providers. This keeps the worker ID and credential, checks that the old worker is paused/stopped and the pool idle, and audits the new signed recipe. media-worker's private bundles and farm signing key remain on the head, outside Git.

Model provenance: [TRELLIS.2](https://github.com/microsoft/TRELLIS.2), [Q8 conversion inventory](https://huggingface.co/ilintar/trellis2-gguf/tree/a57397bd3d351599d9729fc144b3f87c3f87d65b/q8). Preserve upstream engine and model notices when distributing a runtime bundle; weights and downloaded binaries are not committed to this repository.
