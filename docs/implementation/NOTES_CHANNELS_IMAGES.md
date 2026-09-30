# notes, shared channels and local images

> Addresses, host labels and accounts shown here are illustrative placeholders. Use your own private deployment configuration.

> Current status, 18 September: the active image provider is Fooocus on media-worker. Qwen runs independently on model-host; image and geometry services share media-worker's managed GPU. Hourly evidence expiry and the prepared laptop topology below are historical. See [the dated farm snapshot](CURRENT_STATE.md) and [current coverage](DESIGN_COVERAGE.md).

Current update: [provider qualification](PROVIDER_LIFECYCLE.md) no longer expires after one hour. The hourly behavior described in this historical milestone has been superseded.

> Milestone record. [Capability routing](CAPABILITY_ROUTING.md) subsequently implemented route preferences, connection editing and the optional native TLS connector. Their earlier pending status below is historical. See [design coverage](DESIGN_COVERAGE.md) for current limits.

> Milestone record. [Capability routing](CAPABILITY_ROUTING.md) subsequently implemented route preferences, connection editing and the optional native TLS connector. Their earlier pending status below is historical. See [design coverage](DESIGN_COVERAGE.md) for current limits.

13 September 2026. This slice adds the user's requested keyboard workflow, side notes, steering and joined channels, plus the first local image generation path. It closes no phase or release gate. All 61 gates, required local geometry and A12's P8 media cases remain in scope.

## Shared image attachments and composer focus — 18 September 2026

Channels accept pasted, attached or dropped still PNG/JPEG/WebP images, up to four per message and 8 MiB per input. Image-only posts are supported. The shared decoder applies orientation, strips metadata, flattens transparency and stores a JPEG at no more than 1600 pixels per edge. Draft uploads remain visible only to their uploader; sending publishes them atomically with the message to current channel members. Unsent attachments can be removed or recovered after reopening the channel; leaving deletes the sender's unused uploads. Saved message images remain in shared history, and membership is checked again on every no-store image download. Storage is bounded to 1000 images/128 MiB per uploader within currently joined channels; saved image deletion and general quota management remain future work.

Channel uploads are shared pictures only. They never trigger Vision, never attach historical pixels to later replies, and never override an explicit image-generation request. Mentioned text replies receive a short note that images exist but are not visible to the model. Private chat retains its separate Vision workflow.

Complete single-image descriptions go directly to the image queue, independently of LM Studio availability. Pronouns describing a subject already supplied in the prompt (for example, “a spaceship, give it an industrial look”) and spatial “above” do not require a chat planner. Actual references such as “an image of that” and image batches still use the existing planning workflow; an unavailable planner is identified as prompt-planning in the failure message.

Published attachments offer **Generate model** to members allowed to generate geometry. This opens the private geometry form with an authorized reference copy; naming, provider selection and explicit submission still precede the existing fair GPU queue. Navigation alone creates no job. Enter sends a channel message while keeping the composer focused; failed sends keep the draft, images and retry identity.

Migration `0027` adds forced-RLS channel attachments with separate draft/published read boundaries, owner-only draft mutations and a composite message/channel/farm/author foreign key. The private-chat attachment table is unchanged. See the [current build ledger](BUILD_STATUS.md) for validation and deployment results.

## Responsive workspace and shared image wording — 18 September 2026

The current workspace fills wide displays. Private chat, channels, image settings and model settings have persistent collapse controls and horizontal drag/keyboard dividers; private notes can dock on the right or below the conversation. Preferences are local to this browser and account. Below 800 pixels, panes stack and horizontal dividers disappear. This is pane docking, not arbitrary floating windows. Expanded 3D previews span the gallery and support vertical resizing, including the actual WebGL viewport.

Private and channel transcripts open at the newest message and follow replies and media growth while already at the bottom. Scrolling back pauses following; **Jump to latest** restores it. Sending a message also returns to the latest content.

Direct creation requests now accept both “me” and “us,” including `@hearth make us an image of a ford F150 please`. Channel requests still require an explicit mention and use the shared capability router. Quotes, negation and requests for prompts remain text; contextual images and bounded plural requests retain local planning. Existing qualification, permissions, resource availability and joined-channel publication rules apply. A subsequent [conversation queue integration](MANAGED_WORKERS.md#conversation-queue-integration--18-september-2026) now queues images from private chat and channels and performs service switching under the worker’s approved shared policy.

See [workspace validation](../../evidence/workspace/2026-09-18/validation.json) for source checks, isolated VM backend tests and browser fixtures. Provider rendering and real member identity are distinct from these fixture results.

## Try it

Refresh the [workspace](https://hearth.example.invalid). **Private chat** now sends on Enter and inserts a new line with Shift+Enter. Composition/IME events do not send. **For later** stores private notes independently of chat turns; save while the model works, use a note in the composer, send it, steer with it, or dismiss it. Accepted note sends consume the note atomically. Failed admission preserves it.

Typing a new direction while a reply runs changes the send action to **Steer response**. hearth saves the direction and stops accepting old answer text. With the current OpenAI-compatible adapter, the upstream request must finish before the replacement starts. This is a visible interruption and durable steering queue, not a claim that LM Studio's GPU computation stops instantly. **Return to composer** withdraws a queued message. A changed/revoked session or unknown prior execution blocks dispatch instead of replaying work.

You can continue a stopped conversation. Its partial answer remains visible, while the next model context contains human messages and completed assistant replies. Private chat still rejects an oversized context rather than silently dropping history. Notes stay outside model context until explicitly sent. The side panel moves beneath the transcript on narrower screens.

Open **Channels**, create a named room or join an existing one. Other farm members can discover names, but joining is required to read messages or participate. Joining reveals earlier channel history. Anyone in the farm may join these first shared rooms; private/invite-only channels and moderation are not implemented. Leaving removes subsequent read access and cancels publication of a reply you requested, while its upstream work drains.

A newly posted human message containing the separate mention `@hearth` requests one assistant response. Ordinary messages, email-like strings, old mentions and assistant messages never trigger another run. The model receives up to 20 recent completed channel messages within a 16,000-byte context window, with human display names represented as data. It receives no private chat, note, draft, credentials or tool authority. The UI displays the latest 100 channel messages; this first version has no older-history pagination. An occupied model leaves the human message saved and visibly reports that no assistant reply started. There is no automatic channel inference queue.

Open **Images** for local SDXL text-to-image generation. The prepared `hearth image provider` is connected to port 1235 and shares the LM Studio resource group. Prompts, seeds, dimensions, step counts, model revision, manifest hash and validated PNGs persist privately. **Stop image** uses actual job-scoped cancellation. **Use settings** restores a saved request; **Save PNG** downloads through the authenticated user API. Ordinary provider evidence expires after one hour, so an administrator may need to use **Verify chat** or **Verify images** again.

Image creation now also works directly in conversations, with inline PNGs and image-aware steering. See [contextual planning](CONTEXTUAL_IMAGE_PLANNING.md) and [conversation images](CONVERSATION_IMAGES.md) for the current dispatcher, membership boundaries and validation.

## Implementation boundaries

Migrations 0004â€“0008 add forced-RLS side notes, durable steering requests, explicitly joined channels and private image jobs. Shared channel tables do not weaken private conversation ownership. Channel memberships are principal-scoped, and message access requires that principal's membership; no security-definer RLS bypass is used. Image generation and chat use the same admission receipts and pool fencing. Account/session/target checks apply at dispatch, during persistence and before publication. A lost transport cannot silently release capacity or replay a prompt.

The image transport is a typed job protocol, independent of any upstream UI. It checks request/receipt identity and settings, advertised model closure, bounded downloads, SHA-256, PNG decoding and dimensions. Its experimental Python runtime loads only a pinned local SDXL safetensors closure with offline loading and CPU offload. It retains one job slot until CUDA synchronization completes. This is not the signed native worker/runtime distribution or an enforced OS network sandbox. See the [runtime recipe and limits](../runtimes/IMAGE_PROVIDER.md).

The supplied Fooocus ZIP was extracted under `C:\src\Fooocus-main`. Its own Python environment was prepared with CUDA 12.8 support, and a real matrix operation passed on the test CUDA GPU. Source inspection found a large Gradio positional UI contract, automatic update/install behavior and a launcher TLS override. The hearth experiment used the direct Diffusers route without running the Fooocus updater or disabling TLS validation. Fooocus's graphical workflow remains an optional future adapter, not a requirement for this capability.

Image input/editing, refiner/upscaling workflows, style/LoRA catalogs, voice, 3D generation, exports/import qualification, native remote connectors, richer routing preferences and the administration agent remain unimplemented. The original geometry decisions and [Shapecast observations](SHAPECAST_INSPECTION.md) still guide separate image, geometry, material and export stages.

## Evidence

- PostgreSQL/API: `test_chat.py`, `test_channels.py`, `test_images.py` cover private records, explicit joining, two-member context, keyboard-adjacent backend semantics, idempotency, target/profile checks, cancellation, revocation and shared GPU admission. OIDC is an explicit fixture in disposable farms. Real Owner/MFA and personal data were preserved.
- Runtime/transport: `test_image_runtime.py` and `test_image_transport.py` cover controller authentication, request bounds, scoped cancellation, restart receipts, receipt mismatches, corrupt artifacts and uncertain execution. These use synthetic engines/transports.
- Real GPU: [SDXL first render](../../evidence/images/2026-09-13/sdxl-local-proof.json), [HTTP cancellation and next render](../../evidence/images/2026-09-13/image-provider-live.json), and [BFF/database/fresh-session image persistence](../../evidence/images/2026-09-13/bff-live-image.json).
- Browser: 15 Playwright cases pass, including new note/steer, joined-channel and image-gallery interactions, desktop/mobile layout and real appliance readiness. Session and feature data in the UI cases are fixtures. The image screenshot uses an actual previously generated local PNG.

The first SDXL proof was 1024 Ã— 1024 at 20 steps in 13.48 seconds including pipeline load, with 5,593,327,104 bytes of peak GPU allocation. This measurement is specific to the current laptop and warm local dependency cache. No paid inference was used. The model closure added approximately 6.94 GB of verified weights/configuration/tokenizer files; the Python/CUDA environments require additional disk space.
