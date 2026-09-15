# P8: specialist collaboration and multimodal output

Dependency: P7. Outcome: one conversation coordinates several workers and returns text, images and audio.

## Build

All image/audio and approved geometry backends use central service recipes from [11](../../../plan/11-INSTALLATION-AND-CENTRAL-MANAGEMENT.md). Assigning a supported modality installs its correct runtime/dependencies/model and typed settings automatically. Apply C04 to real text-to-image or geometry reassignment. A member operator must not install Python packages, set model paths or edit container files. Geometry recipes use the GLB contract and quality gates in the [video review](../../../plan/VIDEO-REVIEW-IH8XmxiwliQ.md); advertise only actually validated backend capabilities.

1. Implement `ask_specialist` through the task broker, bounded task trees, source-cited results, authority/budget inheritance and cancellation propagation.
2. Persist and release parent inference slots while children/tools run. Add cycle/depth guards, shared-deployment scheduling and visible dependency states.
3. Add media contracts and local adapters: Diffusers image generation on a tested NVIDIA/Linux profile, whisper.cpp transcription, and Kokoro through a pinned ONNX runtime package for CPU speech. Approve actual models/licenses through the catalog; do not auto-download arbitrary pipelines.
4. Add media upload validation, artifact delivery, image/audio display, progress and modality-specific OpenAI adapters where the configured provider supports them.
5. Build an illustrated/narrated documentation workflow and compare specialist collaboration against a single-model baseline.
6. Implement the selected approved local 3D service recipe with typed text/image inputs supported by that backend and GLB output. Test any conversion/validation dependency separately. Supply central assignment/settings, scoped input/output artifacts, progress/cancellation, isolated preview and provenance. The first working profile may be NVIDIA/Linux; other combinations remain unavailable until verified.

## Prove

E11, E19 plus authority, locality, cycle and cancellation regressions. A writer asks a coder to inspect implementation and cites real source results. The same deployment can act as parent and child without deadlocking its one generation slot. Two models recursively requesting each other terminate under a bounded policy.

Generate a real image, transcribe a known audio clip and synthesize an intelligible script. Record model/runtime provenance and content authorization for each artifact. Test cloud-only media refusal under local-only policy. Cloud tool results cannot bypass egress checks through a specialist's summary.

Generate a real 3D artifact through an assigned geometry worker, validate GLB structure/contained resources, finite coordinates/bounds and requested geometry budget, and inspect its preview. Record supported materials/textures and do not claim rigging or game-ready topology without evidence. Complete one authorized image-to-3D chain where the selected backend supports image input.

## Exit gate

Register the now-implemented toolbox, knowledge and media/geometry configuration operations with the existing admin management facade. Demonstrate conversational assignment of a real supported media service under the same permissions and provisioning checks. This extends the P4 admin agent; it does not create its first usable implementation.

One complete user request exercises multiple workers, shared tools and memory with real outputs. Every claimed supported modality has a real adapter and quality evidence. AMD/Windows media support may remain explicitly deferred while those hosts retain their validated text roles.

Next: [P9](../../../plan/phases/P9-HARDENING-AND-RELEASE.md).
