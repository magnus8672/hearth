# Deployment roles and capability status

Updated 29 September 2026. This public overview describes implementation roles and qualification requirements. Actual hostnames, addresses, accounts, hardware inventories and saved provider state belong in private deployment configuration. For a live inventory, open **Administration → Farm map**, **Providers** and **Workers** on your own deployment. Dated validation is in the [implementation ledger](BUILD_STATUS.md).

## Roles

| Role | Responsibility |
|---|---|
| Head | Identity, authorization, routing, private storage, queues, memory, and separate workspace/admin interfaces. A GPU is not required. |
| Model host | An existing compatible server such as LM Studio, with explicitly configured targets and verified capability bindings. |
| Media worker | Approved Fooocus, TRELLIS or Hunyuan services. Independent hosts run concurrently; explicitly shared GPUs use the managed media queue. |
| Optional providers | Compatible speech, transcription and tool services registered by an administrator. |

## Capability requirements

| Capability | Implemented behavior and requirements |
|---|---|
| Text profiles | Compatible chat transports with verified targets. Automatic intent selection may fall back to general chat for an unassigned specialist; explicit selection requires an eligible assignment. |
| `vision.describe` | Private image understanding requires saved pixel-reading verification, not just advertised Vision support. |
| `image.generate` | Fooocus jobs from the gallery, private chat and channels join the durable media queue. |
| `geometry.generate` | TRELLIS.2 and Hunyuan3D 2.0 support private image-to-3D, names, reference thumbnails, tuning, previews, GLB/OBJ exports and cancellation. |
| `memory.retrieve`, `memory.index` | Built-in, scoped PostgreSQL functions; no inference-target binding is required. Account grants still apply. |
| `audio.speak`, `audio.transcribe` | Compatible providers must be installed, registered and verified. Adapter implementation does not imply deployment availability. |

All fourteen profiles have bounded implementations; this does not mean all are enabled in a particular installation. Configuration, observed residency, saved verification and model quality are separate facts. There is no automatic model loading/swapping on the external LM Studio request path.

## Scheduling and access

Explicit shared-media mode schedules by owner fairness, then selects the backend stored on the chosen job. The worker confirms other approved service cgroups have stopped before starting that service. Text, audio and client API requests retain their existing admission behavior; the universal inference queue is not implemented.

Private chats, memory and generated models remain account-scoped. Channels share messages and images with members. Channel image sharing does not automatically invoke Vision; **Generate model** prepares a private geometry request. New signups start pending with zero permissions, and administrators grant access explicitly.

The [Admin farm map](FARM_MAP.md) reports placement, observed residency and stale or unknown state. It makes read-only observations, not lifecycle or generation calls. See [design coverage](DESIGN_COVERAGE.md) for remaining release work.
