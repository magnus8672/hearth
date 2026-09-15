# images inside conversations

> Milestone record. Text turns now also use the configured [specialist routes](CAPABILITY_ROUTING.md); the original general-chat-only statement below describes this earlier image-dispatch slice. See [design coverage](DESIGN_COVERAGE.md) for the current scope.

13 September 2026. Direct requests such as “Make an image of a fox beside a fireplace” now select the verified `image.generate` provider and return a saved PNG inside the same conversation. `@hearth draw a fox` does the same in a joined channel. No text model is needed for this image action. Ordinary text turns continue using `chat.general`.

The browser shows preparation and detail-pass progress, a preview, an authenticated full-size link, **Save PNG**, and the actual prompt/model/seed/settings. Private chat images also appear in the personal Images gallery. Channel images belong to channel history and are excluded from private galleries, including the requester's. A currently joined member can open a channel image; leaving removes access to its endpoint. Owners have no implicit access to personal images.

Private **Stop response**, typed steering, and **Steer with this** from a side note work across image and text turns. The next accepted direction waits for a confirmed cancellation/completion receipt before claiming the shared GPU. Channel responses now have a Stop control for the member who requested them. Leaving also cancels that member's unfinished publication. Losing a receipt keeps the resource group unknown and blocks automatic continuation.

## Routing boundary

This initial action dispatcher recognizes explicit English image creation requests with make/create/generate/render/draw/paint/illustrate and common polite forms. It retains requested media/style and recognizes square/landscape/portrait before the image noun. Default settings are square, 20 steps and a newly saved seed. It does not execute instructions inside model output, a historical message, quoted text or a code block. Asking how image generation works, or explicitly saying not to generate, does not invoke the image provider. Unsupported or ambiguous phrasing can remain a text turn; this is not a general semantic planner.

The direct path uses a concrete description. [Contextual image planning](CONTEXTUAL_IMAGE_PLANNING.md) now resolves requests such as “draw what we just discussed” and makes new variations from previous descriptions. Multilingual intent classification, edits of existing pixels, image understanding, arbitrary model tool calls and required 3D remain unfinished. The next text turn receives the generation description with an explicit note that image pixels are absent; this does not qualify a vision model. The image tokenizer still rejects an oversized prompt instead of silently truncating it.

## Persistence and authorization

Migration 0007 adds `conversation_images`, a publication record linked by composite foreign keys to the original private or channel message and the private executor ledger. The private `image_jobs` table keeps the sending session and execution controls. No new permission grants are inferred from a target, model output, request identifier or URL. PNG URLs are constructed by hearth and always require the user BFF audience and current conversation scope. Responses use `no-store` and `nosniff`.

The common image executor checks the original session, target revision, active pool receipt and conversation state at dispatch and while observing generation. It commits terminal run/message state, the validated artifact and pool release in one transaction. In the control database, only channel publication stores channel PNG bytes; the private executor ledger does not retain another downloadable copy. Interrupted work is never replayed. A private control-database backup preceded migration 0007; existing Owner/MFA and personal data were preserved.

`ConversationImage` is a closed, versioned shared contract. The generated Python/Go/TypeScript schema bundle has 37 models, 38 definitions and 148 common validation fixtures.

## Observed validation

- Windows and Linux each pass 121 Python tests, with three opt-in live GPU cases skipped by the ordinary suite. New PostgreSQL tests cover direct dispatch without a chat model, private and cross-farm isolation, member join/leave, duplicate sends, fresh-session restore, side-note steering, revoked sessions, unknown execution and late channel publication.
- The opt-in [live dispatch proof](../../evidence/images/2026-09-13/chat-routing/live-dispatch.json) passes real SDXL requests through private chat and a channel mention, verifies both PNG digests and restores the private artifact in a fresh session. These use explicit OIDC fixtures in disposable farms; they do not replace the separate real-Keycloak acceptance suite or modify a real user's conversations.
- All 14 Playwright tests pass. Two focused image-conversation cases pass again after preview sizing, with desktop and mobile screenshots visually inspected. Browser identity/message data are fixtures; the displayed fox is the actual locally generated PNG from the live proof.
- Go checks, TypeScript validation, all 148 shared fixtures and both production bundles pass. No paid inference or additional model download was needed.

All 61 release gates remain open. E19's partial media evidence now includes conversation dispatch; local geometry, other media, native runtime distribution and the full A12 P4/P8 setup-and-growth scenarios remain required.
