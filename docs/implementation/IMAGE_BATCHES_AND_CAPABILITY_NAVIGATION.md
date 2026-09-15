# image batches and capability navigation

> Milestone record. [Capability routing](CAPABILITY_ROUTING.md) subsequently added ordered assignments and text specialist dispatch for the capability cards. General semantic routing and missing modality adapters remain open. See [design coverage](DESIGN_COVERAGE.md).

13 September 2026. This build addresses two user-observed gaps: plural image requests falling through to text-only replies, and capability cards lacking a path to their provider controls.

## Image requests

The workspace accepts explicit plural requests such as “Generate four images of Jeep Gladiator pickups, one each in red, grey, black and army-green.” In an existing image conversation it also recognizes “make 4 different jeep gladiators in red grey black and army-green please.” A follow-up such as “ok generate the images of each please” uses the scoped conversation to plan separate pictures, even if an earlier text-model reply incorrectly said it could only supply descriptions.

The supported batch size is one through four. A model proposes a closed list of prompts, negative prompts and shapes. The control plane checks the human request's bound and any explicit count. It rejects malformed items, authority fields, excess images and missing requested items before rendering. This remains bounded English action recognition; arbitrary text requests without visual context are not a universal image classifier.

Each picture has a separate request ID, seed, progress, settings and saved PNG. A parent conversation run holds one shared resource slot while child renders execute sequentially. All child records are admitted in one transaction before any image RPC. A quota or admission failure rolls the entire batch back. Completed pictures appear while later ones wait. Stop, steering, session loss and channel leave prevent further child dispatch and preserve completed images. A missing execution receipt keeps the shared slot unknown. Expired queued/running batches reconcile without replay from either chat or the private gallery. A vague singular variation after several pictures asks which image instead of selecting one silently.

Migration 0009 adds batch parent IDs, positions, counts and queued states. Existing single-image artifacts remain readable. A private database backup was taken before migration. Private batches stay in their owner's gallery; channel batches remain in joined-channel history. The existing Owner, authenticator and personal data are preserved.

## Capability navigation

Administration's capability cards now provide **Configure**, **Configure provider**, or **Verify provider** links according to readiness. Conversation and Image generation open Providers with only matching models shown and the correct connection type preselected. Verification remains an explicit action on the matching model. Reload and browser Back preserve navigation. **Show all providers** restores the full list.

Capabilities whose adapters are unfinished offer **View requirements**. Their destination explains the missing support and does not present an unrelated chat form or imply that a chat probe enables them. Member workspace cards do not expose administration controls.

## Evidence and limits

- Windows and Linux: 170 Python tests, with five opt-in GPU cases skipped by ordinary runs. Contract generation produces 39 models, 40 definitions and 156 shared fixtures. Go, TypeScript and both browser builds pass.
- 18 browser tests cover capability navigation/filtering, reload/Back, mobile width, batch progress, completion, cancellation and persisted images. Identity and API data in browser interaction cases are explicit fixtures.
- [Live batch evidence](../../evidence/images/2026-09-13/batches/live-batch.json) records real local GPT-OSS planning and four real SDXL renders through restricted PostgreSQL and the BFF. OIDC is a fixture in a disposable farm. No personal chat was used for acceptance testing.
- Visual review confirms four separate pickups with cargo beds. Grey, black and green match their prompts. The red-prompt image came out blue; all four artifacts and exact prompts/seeds are retained. Batch completion proves routing, execution and persistence, not exact color or model fidelity. There are no silent retries to select a better-looking acceptance example.
- [Deployed validation](../../evidence/images/2026-09-13/batches/validation.json) checks HTTPS, deployed assets/API hashes, migration 0009, provider readiness, 119 unchanged original inputs and 61 open release gates.

Image editing, generalized capability routing, native remote worker enrollment, managed signed runtimes, local 3D and the remaining A12/P8 acceptance requirements remain unfinished.
