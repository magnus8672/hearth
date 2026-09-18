# Managed Linux services and GPU queues

Implemented 18 September 2026. The first native Go worker can adopt approved, already installed systemd services. media-worker (`10.20.30.20`) is connected to the existing head (`10.20.30.10`) and manages Fooocus. TRELLIS and a 3D artifact adapter are not installed yet.

## Try it

Open **Administration → Workers**. media-worker shows its last observation, selected service, resource group, active work and waiting image count.

- **Pause queue** holds new work and lets the current job finish. **Resume queue** allows dispatch again.
- **Keep the selected service resident** is the default. Model services remain resident between jobs; separate machines can work concurrently.
- **Share this GPU between services** explicitly permits switching among locally approved services. The scheduler selects the service required by the next gallery job, confirms the previous service has stopped, waits for health readiness, and rechecks the previously qualified provider manifest before inference.
- **Unload and pause** releases the selected service when the group is idle. A running or uncertain job prevents service changes. Select Fooocus to start it again, then resume the queue.
- **Retry service** requires a new configuration revision after a lifecycle failure. Changed service files require reviewed approval, not repeated retries.

In **Images**, submit another picture while one is running. The button changes to **Add to queue**. Cancel a waiting picture without interrupting the current render. Private prompts and artifacts remain in the owner's existing RLS partition; administrators see queue counts, not another user's prompts.

## Scheduling and failure behavior

PostgreSQL migration `0023` adds content-free queue metadata and operator-adopted worker records. Admission is exclusive per resource group, with at most eight pending/active gallery jobs per owner and 64 per group. After serving an owner, the scheduler prefers the oldest waiting request from a different owner. Independently resourced pools are admitted separately. Requests expire after 30 minutes and their sending session must still be authorized at dispatch and during inference.

Queued requests survive head restarts. A claimed or dispatched request is never automatically replayed. Lost execution holds the existing pool reservation; expiration diagnoses interruption, not proof that GPU work stopped. The provider's confirmed cancellation/release receipt or the existing explicit recovery workflow releases execution capacity. Queued cancellation is immediate; running cancellation waits for the provider. Idempotent requests retain their original IDs and deletion tombstones.

The first durable queue covers **private gallery generation**. Chat/channel image batches, text, speech, transcription and client API requests still use their existing busy/admission behavior. All existing callers respect an adopted worker's pause, freshness and service readiness before taking its pool. Moving a managed provider to an unrelated group is rejected. This is not yet a universal task scheduler.

Each worker controls one resource group with up to sixteen approved service definitions. A service may back multiple model targets on its registered provider connection. The worker does not assume Fooocus internals: its local recipe names an exact unit, approved file hashes, an authenticated loopback health endpoint, and an expected response field. Future model drivers can use the same lifecycle boundary with their own typed job/artifact protocols.

## Control and trust

The worker opens an **outbound HTTPS** connection to the head's admin origin. It validates the pinned head CA and hostname, does not follow redirects or use HTTP proxy environment variables, and has no inbound management listener. A random 256-bit operator credential is scoped only to the worker poll endpoint; the head stores its digest. It cannot act as a browser, user, admin agent or MCP client. Browser Origins are rejected.

This is **console adoption**, not the complete member enrollment protocol. Automatic pairing, CSRs, mTLS client certificates, rotation, issuing policy and installer enrollment remain open. Existing Fooocus inference continues over its separately approved LAN HTTP connection. Adoption does not silently turn that legacy connection into a TLS-managed inference transport.

The operator signs the local recipe with Ed25519. The worker verifies the signature, signer, worker ID and closed schema before accepting it, then checks approved files before activation and health observation. Unit drop-ins must be included in approval and systemd must have reloaded the approved unit. Head commands contain only a revision and an approved service ID, never shell commands, paths or package URLs. The root supervisor can ask systemd to manage only those approved units; the inference service retains its existing unprivileged account.

Reports have a boot ID and strictly increasing sequence. Competing boots must wait for a 30-second absence. The control lease lasts at most 15 seconds and reports arrive approximately every three seconds. A stale lease prevents new lifecycle changes; existing inference is not killed just because the network dropped. A local process lock prevents two workers using the same state directory. A status journal contains observations, never credentials or prompts.

Before a replacement starts, systemd must confirm the old unit is inactive/failed, both main/control PIDs are zero and its cgroup is empty. Stop failures block the replacement. Readiness requires the service's authenticated health response, not simply a running PID. Model qualification and residency remain separate concepts. Fooocus may load some components lazily on its first image; API readiness is not an assertion that every model tensor is in VRAM.

Direct jobs launched through Fooocus's graphical UI, ComfyUI or another unmanaged application are outside the scheduler. When assigning a GPU to hearth, avoid running those jobs concurrently. The worker does not kill unrelated processes or claim control of their memory.

## Installation and service updates

This operator workflow currently requires Linux, systemd, cgroups v2, Python 3 and OpenSSL on the head, and a compiled native worker. It adopts installed applications; it does not install CUDA, download models or accept arbitrary executable recipes from the UI.

1. Install and qualify the provider normally. Identify its connection ID and resource group ID. Gather the exact unit/entrypoint and dependency-inventory SHA-256 values from the worker over trusted SSH. Include `/etc/systemd/system/<unit>.service`, the adapter entrypoint, its relevant modules, and the runtime's verified dependency manifest.
2. Prepare a private JSON inventory with `name`, `pool_id`, and `services`. Each service entry contains `name`, `connection_id`, `unit`, `files` (absolute path to SHA-256), `health_url` (fixed `http://127.0.0.1:port/path`), `health_key_file`, `health_field` and `health_value`. No downloaded content or model output is an approval source.
3. On the head, run `sudo python3 /opt/hearth/scripts/adopt_worker.py --inventory /private/inventory.json --output /opt/hearth/.hearth/worker-setup`. It requires an idle, unmanaged pool and creates a paused registration plus a private bundle. The farm's recipe signing key stays on the head.
4. Copy the bundle over authenticated SSH into root-owned `/etc/hearth-worker` (directory 0700, files 0600). Install the Linux binary at `/usr/local/lib/hearth/hearth-worker` and the [service unit](../../worker/hearth-worker.service) at `/etc/systemd/system/hearth-worker.service`. Create root-owned `/var/lib/hearth-worker` with mode 0700. Disable independent boot startup of adopted inference services without stopping their current jobs. Select the intended service in Administration before starting the worker if it must remain running during adoption; a null desired service explicitly means unloaded.
5. Run `sudo systemctl daemon-reload` and `sudo systemctl enable --now hearth-worker`. Select the service and resume admission in Workers. The recipe is read at worker startup; changing installed files requires re-signing the reviewed inventory and updating its digest on the head while admission is paused and the worker is stopped. A guided update/re-signing wizard is still pending.

media-worker uses `/etc/hearth-worker`, `/var/lib/hearth-worker` and `hearth-worker.service`. Fooocus's own unit is now disabled for independent boot startup; the worker owns its desired state. Fooocus still runs as `operator` and retains all of its existing configuration, keys, models and saved jobs. Its provider URL and capability bindings are unchanged. To revert adoption, first pause and drain the group, stop the worker, remove its managed registration through a reviewed console operation, and re-enable Fooocus boot startup. Do not remove a registration to bypass uncertain GPU execution.

## Evidence and limits

- 69 isolated VM tests passed, including worker authentication/revision checks, queue persistence, cancellation, quotas, cross-owner privacy, owner fairness and independent-pool admission. Three opt-in tests skipped in that run.
- Four native Go tests passed on the head VM: service switching, failed-stop fencing, file tampering/readiness, invalid commands/leases and process locking.
- Four browser fixtures passed against the deployed TLS-served bundles: worker controls, multiple gallery requests/cancellation, existing advanced image options and deletion. These use fixture API responses and do not claim real browser sign-in acceptance.
- A separate real GPU integration test passed using isolated database storage: two queued 1024 × 1024 PNGs completed sequentially, a third was cancelled before dispatch, and no two jobs were observed running together. Existing user galleries were not used as test storage.
- [Real lifecycle evidence](../../evidence/workers/2026-09-18/lifecycle.json): authenticated outbound control unloaded Fooocus in 5.36 seconds, GPU use fell from 8,328 MiB to 651 MiB, and API readiness returned in 17.64 seconds. These are single observations, not benchmarks. The queue was resumed after qualification.

Multi-engine switching has native fixture coverage only. Actual Fooocus-to-TRELLIS switching, 3D outputs/previews, multiple managed physical workers, sustained load, process/host power-loss recovery, signed distribution, automatic installation, full enrollment/mTLS, certificate lifecycle, automatic GPU fit checks and unified queues for other capabilities remain unqualified or unfinished. No full release gate is closed.
