# contextual image planning

> Current status, 18 September: contextual image planning remains bounded prompt preparation. Shared tools and separate TRELLIS image-to-3D now exist; image editing and general specialist orchestration remain open. Historical SDXL/GPT-OSS measurements below are not today's provider inventory. See [the dated farm snapshot](CURRENT_STATE.md) and [current coverage](DESIGN_COVERAGE.md).

13 September 2026. hearth can now resolve an image request from the current conversation and make a variation from an earlier image description. The existing direct image path still works without a text model. This milestone does not qualify a general agent, arbitrary tools, image editing or local 3D.

## Try it

In Private chat, describe a scene, for example “Remember a red Jeep beside a pine forest at sunset.” Then ask “Please draw what we just discussed.” After the picture arrives, try “Make it blue instead.” A simple “Thank you” between the picture and variation preserves image focus. Substantive intervening text changes the focus so an instruction such as “make it shorter” continues to apply to the text conversation.

In a channel, discuss a scene with other members and ask “@hearth draw what we just discussed.” The planning model receives recent channel context only. It does not receive private chats or unsent notes. The existing explicit mention requirement remains in force.

The chat shows **Working out your image from the conversation…** while the local text model prepares a short description. SDXL progress follows. Image details record the final prompt, planning model, image model, seed and settings. Variations are labeled **New image from the earlier description**: composition and style can change because this is a new text-to-image render, not an edit of the original pixels.

Visual checks also found a color-adherence failure: one blue-Jeep prompt with strong orange sunset lighting produced an orange Jeep. The [failed render](../../evidence/images/2026-09-13/contextual-planning/color-mismatch.png) and [exact settings](../../evidence/images/2026-09-13/contextual-planning/color-mismatch-run.json) are retained. The planner now puts requested attributes beside their subject early in the prompt and avoids inventing competing colors or elaborate lighting. The repeated full test produced a visually confirmed blue Jeep. This reduces ambiguity but cannot guarantee that SDXL obeys every attribute. API completion proves a valid saved image, not visual fidelity.

If the subject is unclear, the planner can ask a question without starting an image. A short description in the next reply continues that image request. A cancellation, acknowledgement or new question can return to ordinary chat. Stop, side-note steering and channel leave remain effective during planning. The text request must finish before its resource group is released; stopping planning never dispatches its discarded proposal to the image provider.

## Execution boundary

The control plane recognizes a new human image action before invoking the planner. It selects the image target, source description, conversation scope and sending session. The local text model receives a fixed system instruction and a bounded JSON envelope of conversation data. It can propose only a closed `ImagePromptPlan`: a short prompt, optional negative prompt, supported shape, or a clarification question. It cannot select a URL, identity, provider, file path, command or permission. Unknown fields, duplicate keys, inconsistent actions, oversized descriptions and malformed output are rejected without image dispatch. No raw planning JSON is streamed into the conversation.

This is semantic **prompt preparation within an image action**. The outer action recognizer still uses explicit English request forms and focused variation phrases. It is not a universal multilingual classifier, vision model or tool-calling agent. Model output and historical mentions cannot create new execution authority. The source image description, rather than image pixels, supplies a variation's context.

Migration 0008 adds a private `image_plans` ledger, visible message phases and limited published planning provenance. A private database backup preceded the migration. The ledger stores the original scoped context, selected target revisions, source image request, proposal, execution start and terminal state. A second executor cannot replay a started plan.

After a confirmed text completion, hearth persists a handoff phase and releases the planning slot. A separate transaction rechecks the sending session, conversation state, selected image revision, capability binding, readiness and resource availability before admitting the image job. No two GPU locks need to remain held across this transition. If the image provider becomes busy or changes, the image is not started and the conversation records why. A handoff lost to a process interruption expires after 60 seconds, without replay or falsely marking another execution idle. A lost text completion receipt keeps its pool unknown and prevents image dispatch.

The existing image executor handles actual rendering, cancellation, artifact validation, private or joined-channel publication, and final pool release. The private image job metadata retains planning target/revision provenance. Published image details expose only the planning model, source image request and variation flag; the planner's private ledger is not shared with other channel members.

## Verification

- Windows and Linux each pass **152 Python tests**; four opt-in live GPU cases are skipped by the ordinary suite. **152 shared contract fixtures**, Go checks, TypeScript and both production bundles pass. The contract bundle has 38 models and 39 definitions.
- New tests cover contextual requests, variations after an acknowledgement, clarification replies, private planning records, rejected model authority fields, malformed/duplicate JSON, changed image targets, stop/steer/revocation during planning, normal/expired/stopped handoffs, channel-only context and cancellation when the requesting member leaves.
- **15 Playwright tests** pass, including planning-to-rendering transitions, variation labeling and provenance, desktop/mobile layout, and the existing chat/channel/image interactions. Browser session and message data are explicit fixtures.
- [Real local-model proof](../../evidence/images/2026-09-13/contextual-planning/live-planning.json) records LM Studio GPT-OSS prompt preparation and SDXL rendering through the BFF and restricted PostgreSQL. The red/blue Jeep images and channel result come from real local GPU calls. Identity responses use explicit fixtures in a disposable farm; actual Owner/MFA and personal data are preserved.
- [Deployed validation](../../evidence/images/2026-09-13/contextual-planning/validation.json) records matching HTTPS bundles/API source, migration 0008, ready/idle local providers, the immutable 119 original inputs and 61 still-open release gates.

A live diagnostic caught LM Studio leaking the leading `<|channel|>final <|constrain|>JSON` header into its content field. The exact GPT-OSS compatibility profile now accepts final JSON/json format labels. Chunk-boundary tests retain rejection of analysis, tool recipients and unknown formats; the independent image-plan schema still validates the answer. The [upstream format guide](https://github.com/openai/harmony/blob/main/docs/format.md) defines final answers and format metadata. The subsequent full private/channel run passed. See [the bounded diagnostic record](../../evidence/images/2026-09-13/contextual-planning/header-compatibility.json). No automatic inference retry or broad channel interpreter was added.

This successful planning run does not establish universal provider-format reliability. Broader action recognition, image inputs/editing, managed native runtimes, worker enrollment, geometry/material/export validation and the full A12 P4/P8 scenarios remain required.
