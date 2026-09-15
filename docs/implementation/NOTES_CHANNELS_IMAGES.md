# notes, shared channels and local images

Current update: [provider qualification](PROVIDER_LIFECYCLE.md) no longer expires after one hour. The hourly behavior described in this historical milestone has been superseded.

> Milestone record. [Capability routing](CAPABILITY_ROUTING.md) subsequently implemented route preferences, connection editing and the optional native TLS connector. Their earlier pending status below is historical. See [design coverage](DESIGN_COVERAGE.md) for current limits.

> Milestone record. [Capability routing](CAPABILITY_ROUTING.md) subsequently implemented route preferences, connection editing and the optional native TLS connector. Their earlier pending status below is historical. See [design coverage](DESIGN_COVERAGE.md) for current limits.

13 September 2026. This slice adds the user's requested keyboard workflow, side notes, steering and joined channels, plus the first local image generation path. It closes no phase or release gate. All 61 gates, required local geometry and A12's P8 media cases remain in scope.

## Try it

Refresh the [workspace](https://localhost:8444). **Private chat** now sends on Enter and inserts a new line with Shift+Enter. Composition/IME events do not send. **For later** stores private notes independently of chat turns; save while the model works, use a note in the composer, send it, steer with it, or dismiss it. Accepted note sends consume the note atomically. Failed admission preserves it.

Typing a new direction while a reply runs changes the send action to **Steer response**. hearth saves the direction and stops accepting old answer text. With the current OpenAI-compatible adapter, the upstream request must finish before the replacement starts. This is a visible interruption and durable steering queue, not a claim that LM Studio's GPU computation stops instantly. **Return to composer** withdraws a queued message. A changed/revoked session or unknown prior execution blocks dispatch instead of replaying work.

You can continue a stopped conversation. Its partial answer remains visible, while the next model context contains human messages and completed assistant replies. Private chat still rejects an oversized context rather than silently dropping history. Notes stay outside model context until explicitly sent. The side panel moves beneath the transcript on narrower screens.

Open **Channels**, create a named room or join an existing one. Other farm members can discover names, but joining is required to read messages or participate. Joining reveals earlier channel history. Anyone in the farm may join these first shared rooms; private/invite-only channels and moderation are not implemented. Leaving removes subsequent read access and cancels publication of a reply you requested, while its upstream work drains.

A newly posted human message containing the separate mention `@hearth` requests one assistant response. Ordinary messages, email-like strings, old mentions and assistant messages never trigger another run. The model receives up to 20 recent completed channel messages within a 16,000-byte context window, with human display names represented as data. It receives no private chat, note, draft, credentials or tool authority. The UI displays the latest 100 channel messages; this first version has no older-history pagination. An occupied model leaves the human message saved and visibly reports that no assistant reply started. There is no automatic channel inference queue.

Open **Images** for local SDXL text-to-image generation. The prepared `hearth image provider` is connected to port 1235 and shares the LM Studio resource group. Prompts, seeds, dimensions, step counts, model revision, manifest hash and validated PNGs persist privately. **Stop image** uses actual job-scoped cancellation. **Use settings** restores a saved request; **Save PNG** downloads through the authenticated user API. Ordinary provider evidence expires after one hour, so an administrator may need to use **Verify chat** or **Verify images** again.

Image creation now also works directly in conversations, with inline PNGs and image-aware steering. See [contextual planning](CONTEXTUAL_IMAGE_PLANNING.md) and [conversation images](CONVERSATION_IMAGES.md) for the current dispatcher, membership boundaries and validation.

## Implementation boundaries

Migrations 0004â€“0008 add forced-RLS side notes, durable steering requests, explicitly joined channels and private image jobs. Shared channel tables do not weaken private conversation ownership. Channel memberships are principal-scoped, and message access requires that principal's membership; no security-definer RLS bypass is used. Image generation and chat use the same admission receipts and pool fencing. Account/session/target checks apply at dispatch, during persistence and before publication. A lost transport cannot silently release capacity or replay a prompt.

The image transport is a typed job protocol, independent of any upstream UI. It checks request/receipt identity and settings, advertised model closure, bounded downloads, SHA-256, PNG decoding and dimensions. Its experimental Python runtime loads only a pinned local SDXL safetensors closure with offline loading and CPU offload. It retains one job slot until CUDA synchronization completes. This is not the signed native worker/runtime distribution or an enforced OS network sandbox. See the [runtime recipe and limits](../runtimes/IMAGE_PROVIDER.md).

[Historical deployment inventory removed for repository privacy.]

Image input/editing, refiner/upscaling workflows, style/LoRA catalogs, voice, 3D generation, exports/import qualification, native remote connectors, richer routing preferences and the administration agent remain unimplemented. The original geometry decisions and [Shapecast observations](SHAPECAST_INSPECTION.md) still guide separate image, geometry, material and export stages.

## Evidence

- PostgreSQL/API: `test_chat.py`, `test_channels.py`, `test_images.py` cover private records, explicit joining, two-member context, keyboard-adjacent backend semantics, idempotency, target/profile checks, cancellation, revocation and shared GPU admission. OIDC is an explicit fixture in disposable farms. Real Owner/MFA and personal data were preserved.
- Runtime/transport: `test_image_runtime.py` and `test_image_transport.py` cover controller authentication, request bounds, scoped cancellation, restart receipts, receipt mismatches, corrupt artifacts and uncertain execution. These use synthetic engines/transports.
- Real GPU: [SDXL first render](../../evidence/images/2026-09-13/sdxl-local-proof.json), [HTTP cancellation and next render](../../evidence/images/2026-09-13/image-provider-live.json), and [BFF/database/fresh-session image persistence](../../evidence/images/2026-09-13/bff-live-image.json).
- Browser: 15 Playwright cases pass, including new note/steer, joined-channel and image-gallery interactions, desktop/mobile layout and real appliance readiness. Session and feature data in the UI cases are fixtures. The image screenshot uses an actual previously generated local PNG.

The first SDXL proof was 1024 Ã— 1024 at 20 steps in 13.48 seconds including pipeline load, with 5,593,327,104 bytes of peak GPU allocation. This measurement is specific to the current laptop and warm local dependency cache. No paid inference was used. The model closure added approximately 6.94 GB of verified weights/configuration/tokenizer files; the Python/CUDA environments require additional disk space.
