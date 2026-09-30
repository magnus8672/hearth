# Image settings and 4K output

> Addresses, host labels and accounts shown here are illustrative placeholders. Use your own private deployment configuration.

Deployed 17 September 2026 to the existing head at `10.20.30.10` and Fooocus on media-worker at `10.20.30.20`. Refresh the workspace, open Images and select the existing Fooocus provider. No replacement provider registration is needed.

## Controls

The gallery reads the verified provider profile and offers its supported shapes, detail passes and advanced options. Fooocus currently offers:

- Original render, 2K AI upscale or 4K AI upscale, with exact dimensions beside each choice.
- Square, landscape, portrait, widescreen and tall shapes.
- 20, 30, 40 or 60 sampling passes for the original render.
- Its installed style list, using the provider defaults or up to eight chosen styles. An empty custom selection disables styles; Fooocus V2 enables its prompt expansion.
- Guidance scale from 1 to 30 and sharpness from 0 to 30. Blank values retain the provider defaults.
- The existing negative prompt and repeatable seed.

| Shape | Original | 2K output | 4K output |
|---|---|---|---|
| Square | 1024 × 1024 | 2048 × 2048 | 4096 × 4096 |
| Landscape | 1024 × 768 | 2048 × 1536 | 4096 × 3072 |
| Portrait | 768 × 1024 | 1536 × 2048 | 3072 × 4096 |
| Widescreen | 1024 × 576 | 1920 × 1080 | 3840 × 2160 |
| Tall | 576 × 1024 | 1080 × 1920 | 2160 × 3840 |

Larger images use Fooocus's installed learned super-resolution model after diffusion. The worker runs the model at 4× and downsamples when necessary to match the requested size. This is AI-upscaled output, not native 4K diffusion or an additional diffusion refinement pass. The UI labels that distinction, shows Upscaling while finishing, and displays the actual saved dimensions. Download PNG keeps the full resolution. Use settings restores all submitted options; switching providers resets the advanced selection.

## Implementation and boundaries

`ImageOptions` and `ImageOptionsProfile` extend the shared closed contracts. The controller validates requested settings against the target's verified profile before reserving its resource group; the runtime validates again. Original providers still advertise only their original shapes and steps, and the transport omits default options for compatibility with their existing strict request schemas. Older saved requests normalize through the new defaults for idempotent replay.

Fooocus advertises larger outputs only when its upscaler file is installed. The pinned file is included in the startup inventory. Its worker applies upscaling inside the same execution slot before acknowledging CUDA completion. Cancellation during this stage can take until the current GPU operation finishes; hearth retains the slot until the worker acknowledges release. An uncertain worker keeps capacity fenced. There are no request-time model downloads or model swaps.

Migration `0022` raises the head's gallery and conversation PNG bounds from 16 MiB to 64 MiB and permits 60-step conversation progress. The transport enforces exact requested dimensions, digest and PNG decoding, plus the same byte cap and a 60-second transfer bound. The existing generation deadline remains 15 minutes. Account and stored-image byte totals were unchanged by migration.

Checkpoint paths, LoRAs, samplers, schedulers, refiner selection, image editing and arbitrary dimensions are not exposed in this profile. Existing wildcard/path directives remain rejected. This change adds gallery controls; it does not add natural-language resolution/style planning to chat. Local image-to-3D is covered by [TRELLIS](LOCAL_GEOMETRY.md); all full release gates remain open.

## Observed validation

[Real GPU evidence](../../evidence/images/2026-09-17-options/live.json) uses the existing registered Fooocus target through the production head's authenticated image transport and resource-group admission. Its assignments, credentials and user data were preserved. A harmless red pickup prompt, 20 passes, seed 8672, SAI Photographic style, guidance 5.5 and sharpness 2 produced:

| Run | Result | Elapsed | PNG bytes |
|---|---|---|---|
| Cancel after sampling, during 4K finishing | Cancelled, execution released | 4.81 s | 0 |
| Widescreen 4K | 3840 × 2160, validated PNG | 13.22 s | 11,267,017 |
| Square 4K | 4096 × 4096, validated PNG | 23.01 s | 21,632,401 |

These are individual observations on the CUDA test configuration, not throughput guarantees. The widescreen image was visually inspected. No test pictures were added to the user's gallery.

[Validation record](../../evidence/images/2026-09-17-options/validation.json): 55 Python tests pass on the head VM with restricted roles in a temporary database; three opt-in tests skip and real GPU transport is qualified separately above. Coverage includes settings admission, adapter forwarding, legacy compatibility, incorrect receipt rejection, large artifact storage, restoration and deletion. All 188 shared contract fixtures pass in Python and native Go on the VM. Two browser tests pass against the deployed HTTPS bundle with synthetic API responses, covering advanced settings, restoration, provider switching, deletion and 390-pixel layout. Browser fixtures do not prove real authenticated user generation. TypeScript checking, both production builds, Python lint and documentation checks pass. User acceptance of the new controls remains pending; no full release gate changes status.
