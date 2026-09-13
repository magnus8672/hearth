# ADR 0003: local geometry pipeline

Status: selected qualification candidate, not an advertised deployment, 12 September 2026.

Local 3D and validated GLB output remain required scope. Select TripoSR as the first image-to-mesh qualification candidate at source revision `107cefdc244c39106fa830359024f6a2f1c78871`. Its upstream describes source and pretrained weights as MIT licensed and reports roughly 6 GB VRAM for default single-image inference. Those are upstream statements, not Hearth performance results. [TripoSR repository](https://github.com/VAST-AI-Research/TripoSR).

[Historical deployment inventory removed for repository privacy.]

The initial recipe pipeline will accept an authorized image artifact, perform controlled preprocessing, run the model locally, convert its mesh to GLB, validate it and attach provenance. A text request requires a separately approved local image-generation deployment before this image-to-mesh stage. If that dependency is absent, text-to-3D is unavailable with a reason. A shape-only route must not advertise textured output. Upstream exposes texture baking as a separate option and its CLI is the starting point for a bounded adapter. [TripoSR CLI](https://github.com/VAST-AI-Research/TripoSR/blob/main/run.py).

Before a recipe is advertised, pin model and extension revisions and hashes, preserve licenses/notices, build native dependencies in isolation, and measure installation time, peak RAM/VRAM, generation latency and cancellation. Keep these dependencies outside the control API environment. No model weights have been downloaded or executed in P0.

Every result must be an actual generated mesh with a validated GLB container, finite positions, nonempty indexed triangles, consistent bounds, meter units and Y-up orientation. Enforce triangle, texture and output-byte limits, and reject path traversal or external resource references. Persist input and model digests, recipe revision, seed where supported, conversion settings, validation output and locality. Locality inherits from all inputs.

The P8 acceptance suite must include a real local generation, preview, download, cancellation, exhausted-resource handling, cross-user artifact denial and import in an independent GLB consumer. A canned mesh can test a validator but cannot satisfy the generation gate. If TripoSR fails qualification, record the failure and select another local backend without dropping 3D from the product.
