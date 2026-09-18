# hearth vision and concurrent resident models

> Current status, 18 September: private and shared-channel vision are implemented, but the active Qwen target lacks saved vision verification. Run the explicit pixel probe before treating its Vision binding as eligible. Audio, memory and geometry implementations now also exist; their deployment status is separate. See [the dated farm snapshot](CURRENT_STATE.md) and [current coverage](DESIGN_COVERAGE.md).

Implemented 13 September 2026. Private chat can now send actual image pixels to a separately verified vision model. Automatic routing selects `vision.describe` when a turn or its retained history contains uploaded images. Normal text chats continue using their existing conversation/coding routes.

## Try it locally

Open [your workspace](https://hearth.example.invalid), refresh, and start a private chat. Use **Attach image**, paste a picture, or drop a PNG, JPEG or WebP onto the composer. Ask what is in the picture and press Enter. Pictures alone use a short description request. Follow-up questions in that conversation retain the pictures; the response names the model that actually ran.

Administration has **Verify vision** on compatible text servers. That probe reads six fresh random digits from an image; its text prompt never contains the answer. A plain chat probe or advertised vision feature does not qualify the route. Assign a successfully verified model under Capabilities > Vision > Configure. Re-verifying an already qualified vision server checks both chat and vision. Successful evidence no longer expires hourly; see [provider lifecycle](PROVIDER_LIFECYCLE.md).

The historical development farm used the existing remote `qwen/qwen3.8-27b` target for both coding and vision. Its saved HTTP consent, credentials and shared resource pool are preserved. All other capability bindings are preserved. GPT-OSS continues to handle local text conversation. The [activation receipt](../../evidence/vision/2026-09-13/activation.json) records whether this setup completed successfully.

## Privacy and bounded inputs

Migration `0015` adds forced farm/owner RLS storage for normalized chat images and attachment references on messages and queued requests. Each upload is also bound to one conversation. Reading or reusing another account's or another conversation's attachment returns 404. Upload and removal require the current user session and CSRF token. Image URLs are authenticated, never public or sent to a provider as fetchable URLs. The BFF sends normalized pixels inline to the selected provider.

Inputs are limited to four image references in retained vision context, 8 MiB per upload, and 20 megapixels. Only still PNG, JPEG and WebP files that decode successfully are accepted. EXIF orientation is applied, metadata is removed, transparency is flattened onto white, and the image is resized to at most 1600 pixels per edge and re-encoded as JPEG. Stored images are capped at 3 MiB each; each account has a 100-image/128-MiB attachment budget. This is deliberately bounded development storage, not the planned general artifact service. Saved message attachments remain preserved on archive; unsent images are removed when archiving. Full deletion/export and quota management remain unfinished.

Both the streaming request-body middleware and the edge enforce the larger upload budget only for the exact upload method/path. Ordinary requests retain their 1-MiB limit. The edge uses disjoint [Caddy request-body matchers](https://caddyserver.com/docs/caddyfile/directives/request_body), verified against the installed configuration before activation.

Staged images survive reloads and can be removed before sending. Steering stores the attachment IDs with the queued direction, waits for the previous model to drain, then routes the new turn. Cancelling that queued direction restores the images as unused attachments. Retrying a request ID with different images is rejected. Explicitly choosing a text specialist excludes image pixels and adds a short context marker; the UI/API reject attaching new pictures directly to a text-only turn.

## Recorded qualification

- [Physical concurrency](../../evidence/vision/2026-09-13/physical-concurrency.json): real local GPT-OSS and remote Qwen streams overlapped for 0.485 seconds. A second coding request was refused while Qwen's resource pool was occupied. Both requests completed and the loaded model instances were unchanged across dispatch. GPT-OSS was initially unloaded and was explicitly loaded during setup using the existing installed model. No automatic loading or swapping was added to the request path.
- [Real vision](../../evidence/vision/2026-09-13/live-vision.json): Qwen passed the fresh pixel challenge, identified a red rectangle on the left and blue circle on the right from an uploaded image, completed normally, and restored the saved reply and picture in a fresh session. This uses real provider calls and restricted PostgreSQL/BFF APIs with explicit OIDC fixtures in a disposable farm.
- Backend regressions cover image decoding, metadata removal, body-size limits, RLS, CSRF, cross-conversation IDs, failed vision qualification, idempotency, history, image-context bounds, steering and cancelled directions. Browser fixtures cover upload, reload, removal, send, saved previews, per-reply model labels and provider verification. Desktop/mobile screenshots were visually inspected.
- [Deployment and full test validation](../../evidence/vision/2026-09-13/validation.json) records exact counts, source hashes and TLS bundle checks. The original 119 documents and all 61 open release gates remain unchanged.

The first concurrency attempt used a more demanding coding prompt and failed; a simpler reproducible Fibonacci coding task passed the subsequent concurrent run. The first failure's cause was not established. The passing run proves simultaneous dispatch for that case, not broad model reliability or quality acceptance. Physical provider loss/recovery, automatic-loading configuration attestation and the full multi-host acceptance matrix remain open.

## Boundaries and next work

This milestone originally delivered nine executable profiles; all fourteen now have bounded implementations. Vision supports private and joined-channel image understanding; uploaded-image editing, inpainting, image-aware generation and document/PDF ingestion are not implemented. In an image conversation, Automatic keeps follow-ups on Vision; use a new conversation for image generation or explicit text-specialist selection for text-only work. The existing short text-history limit still applies, and provider-native context limits can reject larger requests.

Audio, private memory and geometry adapters were subsequently implemented; active-farm assignments and remaining quality qualification are tracked separately. Managed node enrollment and runtime placement remain separate unfinished work. No release gate was closed by this slice.

The next audio step now has a [measured offline CPU speech probe](SPEECH_FEASIBILITY.md) using existing Kokoro files. It produced a playable sample without downloading models or displacing GPT-OSS; provider registration, playback and transcription were subsequently implemented. No audio provider is registered on today's farm.

Channel upload privacy, recent image context and 3D handoff are described in [shared image attachments](NOTES_CHANNELS_IMAGES.md#shared-image-attachments-and-composer-focus--18-september-2026).
