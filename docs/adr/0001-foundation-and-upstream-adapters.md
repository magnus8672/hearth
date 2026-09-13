# ADR 0001: control stack and upstream boundaries

Status: accepted for the development foundation, 12 September 2026.

Use the specified Python/FastAPI, PostgreSQL, Go and React/TypeScript boundaries. Resolve Python through `uv.lock`, JavaScript through `pnpm-lock.yaml`, Go through `go.sum`, and appliance containers through digest-pinned Compose references. Migration 0001 reads a frozen seed file, so future catalog changes cannot rewrite the meaning of an existing migration.

The application database role cannot own tables, become a superuser or bypass RLS. Personal workspaces, conversations, messages and outbox records enforce both farm and owner at the database boundary. Transaction-local scope expires before a pooled connection is reused. Shared workspace membership needs a subsequent migration and its own tests.

## Switchyard

Pin `nemo-switchyard==0.2.0`. Its actual library exposes `switchyard.libsy.LlmTarget` and `algorithms.random(...).run(...)`, with Python clients called by a Rust-owned algorithm. Earlier example APIs in the design documents are not assumed to exist. The maintained installation notes also distinguish the library from the CLI. [Upstream installation](https://github.com/NVIDIA-NeMo/Switchyard/blob/main/INSTALLATION.md).

Hearth filters authorization, capability, health expiry, context capacity, residency, quality and queue position first. It gives Switchyard only tied eligible candidates. Selection clients return a route receipt without dispatching inference or making a network call. An upstream error selects the first candidate from that same filtered set; an ineligible result fails closed. The real-package regression records each client invocation, so an accidental fallback cannot masquerade as successful integration.

The Windows probe qualifies bounded selection behavior. The official Linux wheel requires AVX2 and faults in the current WHPX guest. The same locked release, built with Rust 1.96.1 and maturin 1.15.0 for x86-64-v2, passes the Linux suite. The source and Cargo lock hashes are recorded in `deploy/bootstrap/switchyard-build.lock.json`. No upstream source edits were needed. It does not qualify provider generation, context planning, cancellation, billing or model quality.

## Graphify

Pin the actual distribution `graphifyy==0.1.14`, which imports as `graphify`. The probe calls `graphify.extract.extract_python` and `graphify.build.build_from_json` on a single explicitly approved source file. It filters nodes and edges to that file. A network-denial test and an ambient credential canary verify the structural path does not require a provider. [Upstream repository](https://github.com/Graphify-Labs/graphify).

This qualifies AST extraction only. Semantic extraction, partition isolation, source generations, deletion, query authorization and filesystem projections remain P7 work. PostgreSQL remains authoritative; Graphify is a rebuildable derived index.

## Contract scope

The 29 Pydantic wire models generate 30 shared definitions, Go and TypeScript types, JSON Schema and an initial OpenAPI document. The 116 common cases cover valid records, unknown authority fields, unsupported versions and boolean version confusion. Python additionally checks dependency cycles and plan sequencing; schema agreement alone does not prove every semantic constraint in Go. Worker execution must validate those semantics before accepting plans.

The OpenAPI document also includes internal record schemas for development inspection. Their presence does not expose a route, grant a permission or make `AdminExecutionGrant` a model-tool argument. Public admin tools will receive their own narrow allowlist in P4. No router, model, extractor or client-supplied header can create a principal.
