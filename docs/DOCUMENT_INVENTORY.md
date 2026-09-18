# Documentation inventory

Updated 18 September 2026. This index separates active guides, dated feature evidence and preserved historical records. Start with [the documentation index](README.md), [current farm state](implementation/CURRENT_STATE.md), [coverage](implementation/DESIGN_COVERAGE.md) and [build status](implementation/BUILD_STATUS.md).

There are 56 Markdown documents outside the baseline/archive directories. The immutable `docs/plan/` package has 119 files, including 30 Markdown documents, twelve numbered engineering designs, ten phase plans and fourteen rendered diagrams. Original snapshot hashes remain the preservation authority. Counts describe inventory, not acceptance coverage.

Feature reports retain their dated evidence and fixture boundaries. Their current-status notes and the farm snapshot resolve superseded topology, URL, adapter and availability claims. A historical model/provider test does not prove it is registered today. The website presents the finished-product vision by design.

## Guides

| Document | Location |
|---|---|
| [hearth implementation guidance](AGENT_GUIDANCE.md) | `AGENT_GUIDANCE.md` |
| [Developing hearth](DEVELOPMENT.md) | `DEVELOPMENT.md` |
| [Documentation inventory](DOCUMENT_INVENTORY.md) | `DOCUMENT_INVENTORY.md` |
| [hearth documentation](README.md) | `README.md` |
| [Testing the active hearth farm](TESTING.md) | `TESTING.md` |
| [hearth project website](WEBSITE.md) | `WEBSITE.md` |

## Architecture decisions

| Document | Location |
|---|---|
| [ADR 0001: control stack and upstream boundaries](adr/0001-foundation-and-upstream-adapters.md) | `adr/0001-foundation-and-upstream-adapters.md` |
| [ADR 0002: appliance, trust and native execution boundaries](adr/0002-installation-trust-and-native-boundaries.md) | `adr/0002-installation-trust-and-native-boundaries.md` |
| [ADR 0003: local geometry pipeline](adr/0003-local-geometry-pipeline.md) | `adr/0003-local-geometry-pipeline.md` |
| [ADR 0004: First testable identity and private workspace slice](adr/0004-first-testable-identity-slice.md) | `adr/0004-first-testable-identity-slice.md` |
| [ADR 0005: Reference WHPX guest CPU compatibility](adr/0005-whpx-shadow-stack-compatibility.md) | `adr/0005-whpx-shadow-stack-compatibility.md` |
| [ADR 0006: managed runtimes and existing inference services](adr/0006-managed-and-external-providers.md) | `adr/0006-managed-and-external-providers.md` |

## Implementation and evidence ledgers

| Document | Location |
|---|---|
| [Signup, approval and capability access](implementation/ACCOUNT_APPROVAL.md) | `implementation/ACCOUNT_APPROVAL.md` |
| [Visual identity 1.1: the lowercase hearth](implementation/BRAND_REVISION_1_1.md) | `implementation/BRAND_REVISION_1_1.md` |
| [visual identity 1.2: one integrated hearth wordmark](implementation/BRAND_REVISION_1_2.md) | `implementation/BRAND_REVISION_1_2.md` |
| [hearth build preparation](implementation/BUILD_PREPARATION.md) | `implementation/BUILD_PREPARATION.md` |
| [hearth implementation ledger](implementation/BUILD_STATUS.md) | `implementation/BUILD_STATUS.md` |
| [Capability routing and external LAN providers](implementation/CAPABILITY_ROUTING.md) | `implementation/CAPABILITY_ROUTING.md` |
| [contextual image planning](implementation/CONTEXTUAL_IMAGE_PLANNING.md) | `implementation/CONTEXTUAL_IMAGE_PLANNING.md` |
| [images inside conversations](implementation/CONVERSATION_IMAGES.md) | `implementation/CONVERSATION_IMAGES.md` |
| [Current farm snapshot](implementation/CURRENT_STATE.md) | `implementation/CURRENT_STATE.md` |
| [hearth design coverage](implementation/DESIGN_COVERAGE.md) | `implementation/DESIGN_COVERAGE.md` |
| [existing local providers and private chat](implementation/EXISTING_PROVIDER_CHAT.md) | `implementation/EXISTING_PROVIDER_CHAT.md` |
| [Direct HTTP for existing LAN providers](implementation/EXTERNAL_HTTP_PROVIDERS.md) | `implementation/EXTERNAL_HTTP_PROVIDERS.md` |
| [Head address and certificate settings](implementation/HEAD_ADDRESS_SETTINGS.md) | `implementation/HEAD_ADDRESS_SETTINGS.md` |
| [image batches and capability navigation](implementation/IMAGE_BATCHES_AND_CAPABILITY_NAVIGATION.md) | `implementation/IMAGE_BATCHES_AND_CAPABILITY_NAVIGATION.md` |
| [Delete generated images](implementation/IMAGE_DELETION.md) | `implementation/IMAGE_DELETION.md` |
| [Image settings and 4K output](implementation/IMAGE_OPTIONS.md) | `implementation/IMAGE_OPTIONS.md` |
| [hearth provider network test](implementation/LAN_PROVIDER_TESTING.md) | `implementation/LAN_PROVIDER_TESTING.md` |
| [Local image-to-3D generation](implementation/LOCAL_GEOMETRY.md) | `implementation/LOCAL_GEOMETRY.md` |
| [Managed Linux services and GPU queues](implementation/MANAGED_WORKERS.md) | `implementation/MANAGED_WORKERS.md` |
| [Multiple provider instances and resident specialists](implementation/MULTI_PROVIDER_RESIDENCY.md) | `implementation/MULTI_PROVIDER_RESIDENCY.md` |
| [notes, shared channels and local images](implementation/NOTES_CHANNELS_IMAGES.md) | `implementation/NOTES_CHANNELS_IMAGES.md` |
| [Private memory and Obsidian vaults](implementation/PRIVATE_MEMORY.md) | `implementation/PRIVATE_MEMORY.md` |
| [Lasting provider qualification](implementation/PROVIDER_LIFECYCLE.md) | `implementation/PROVIDER_LIFECYCLE.md` |
| [hearth Read aloud](implementation/READ_ALOUD.md) | `implementation/READ_ALOUD.md` |
| [Release gates](implementation/RELEASE_GATES.md) | `implementation/RELEASE_GATES.md` |
| [hearth reply streaming and model identity](implementation/REPLY_STREAMING_AND_IDENTITY.md) | `implementation/REPLY_STREAMING_AND_IDENTITY.md` |
| [Local Shapecast orchestration inspection](implementation/SHAPECAST_INSPECTION.md) | `implementation/SHAPECAST_INSPECTION.md` |
| [Shared tools and client connections](implementation/SHARED_TOOLS_AND_CLIENT_API.md) | `implementation/SHARED_TOOLS_AND_CLIENT_API.md` |
| [One sign-in across hearth](implementation/SINGLE_SIGN_ON.md) | `implementation/SINGLE_SIGN_ON.md` |
| [hearth local speech feasibility](implementation/SPEECH_FEASIBILITY.md) | `implementation/SPEECH_FEASIBILITY.md` |
| [Thinking previews in private chat](implementation/THINKING_PREVIEW.md) | `implementation/THINKING_PREVIEW.md` |
| [hearth microphone and transcription](implementation/TRANSCRIPTION.md) | `implementation/TRANSCRIPTION.md` |
| [hearth vision and concurrent resident models](implementation/VISION_AND_CONCURRENT_FARM.md) | `implementation/VISION_AND_CONCURRENT_FARM.md` |

## Operations

| Document | Location |
|---|---|
| [CPU audio providers on a VM](operations/AUDIO_VM_SETUP.md) | `operations/AUDIO_VM_SETUP.md` |
| [Current ESX head](operations/ESX_HEAD.md) | `operations/ESX_HEAD.md` |
| [Fooocus on media-worker](operations/FOOOCUS_PROVIDER.md) | `operations/FOOOCUS_PROVIDER.md` |
| [Git repository](operations/GIT_REPOSITORY.md) | `operations/GIT_REPOSITORY.md` |
| [Run the hearth head on a LAN VM](operations/HEAD_VM_SETUP.md) | `operations/HEAD_VM_SETUP.md` |
| [hearth sign-in theme](operations/IDENTITY.md) | `operations/IDENTITY.md` |
| [Set up a fresh hearth VM from the ZIP](operations/VM_PACKAGE.md) | `operations/VM_PACKAGE.md` |

## Runtime and brand guides

| Document | Location |
|---|---|
| [hearth visual identity](brand/BRAND_GUIDE.md) | `brand/BRAND_GUIDE.md` |
| [hearth image provider](runtimes/IMAGE_PROVIDER.md) | `runtimes/IMAGE_PROVIDER.md` |
| [hearth development speech provider](runtimes/SPEECH_PROVIDER.md) | `runtimes/SPEECH_PROVIDER.md` |
| [hearth CPU transcription provider](runtimes/TRANSCRIPTION_PROVIDER.md) | `runtimes/TRANSCRIPTION_PROVIDER.md` |

## Preserved history

- [Original design package](plan/README.md): unchanged requirements, phase exits, original brand and source references. Its planned/no-code statements describe 12 September, not the current application.
- [Root-package archive](archive/root-package/README.md): relocated duplicates from the initial document reorganization; use canonical `plan/` links for baseline requirements.
- [Pre-refresh build ledger](archive/status-2026-09-18/BUILD_STATUS_PRE_REFRESH.md) and [coverage audit](archive/status-2026-09-18/DESIGN_COVERAGE_PRE_REFRESH.md): retain all earlier milestone prose, requirement mappings and test counts, including superseded status statements.
- [Pre-refresh development](archive/status-2026-09-18/DEVELOPMENT_PRE_REFRESH.md) and [testing](archive/status-2026-09-18/TESTING_PRE_REFRESH.md): retain retired laptop commands solely to interpret historical evidence. They are not operating instructions for the active farm.

Executable assets, generated contracts, runtime manifests and curated evidence remain beside code/assets. Model weights, binaries, certificates and generated connector ZIPs are ignored outputs, not source-document downloads. Build connectors using the [LAN guide](implementation/LAN_PROVIDER_TESTING.md).

Run `python scripts/check_docs.py` for local links, fences, placement and original snapshot hashes. It does not fetch external URLs, check heading anchors or qualify product behavior. See [18 September validation](../evidence/documentation/2026-09-18/validation.json).
