# Context compaction and managed text runtime

20 October implementation note: the [Windows runner preview](../operations/WINDOWS_RUNNER.md) now supervises pinned llama.cpp or experimental NCM XSum through signed recipes and explicit backend selection. This bounded text-runner slice does not complete installers, automatic enrollment, universal text queues, context compaction or broad hardware qualification.

Integrated into the [active roadmap](ROADMAP.md) on 20 September 2026 and reconciled with current source and [P5A](P5A_ROUTING_AND_DECISIONS.md) on 4 October. This is implementation design, not delivered functionality or a release acceptance claim. The source inspection below did not change a running service or model configuration.

## Direction

The head owns conversation continuity across models and machines. Implement model-generated compaction against existing compatible providers before making a managed text runtime a prerequisite. Keep LM Studio and other existing providers supported alongside the eventual managed deployment. This extends [the memory contract](../plan/06-MEMORY-AND-KNOWLEDGE.md) and [provider ownership decision](../adr/0006-managed-and-external-providers.md).

The [roadmap crosswalk](ROADMAP.md#how-context-continuity-fits-the-existing-plan) places budgeting in P4/P5/P7, summaries and lineage in P7, durable execution in P4/P6/P8, client continuity in P5, and managed engine provisioning in P0/P2/P3/P4. Deliver compaction before making managed provisioning a prerequisite. P5A's typed routing decisions are a separate workstream: selecting an intent or target does not summarize conversation history, and its chosen decision model is not automatically a qualified compactor. Neither workstream blocks the other; preserve the outstanding full phase exits.

A managed text runtime means the native hearth worker supervising a pinned inference engine, initially a qualified llama.cpp backend. It does not require writing a new inference engine. Its contribution is installation, authenticated control, model residency, configuration, tokenization and resource observations. The head still owns permissions, context selection, compaction and routing.

## Observed foundation and gaps

| Area | Current source behavior | Needed addition |
|---|---|---|
| Private history | PostgreSQL stores complete visible messages; revisions and Markdown/JSONL vault projections exist | Durable compaction snapshots with exact source revisions and coverage |
| Working context | `memory.recent_window` retains up to 30 messages and normally 12,000 UTF-8 bytes; recall has a separate bounded allowance | Token-based budgeting, retained recent turns and source-backed summaries of older turns |
| Memory | Private notes, preferences, scoped search, original-preserving corrections and dependency checks | Summary invalidation/rebuild integrated with existing revision and permission checks |
| Text providers | Compatible streaming inference and the `text.summarize` capability profile exist | Qualified compaction generation and per-target effective context metadata |
| External clients | Text Chat Completions forwards caller history and tool exchanges; histories are not automatically imported | Explicit stateless compaction and optional authenticated session continuity contracts |
| Managed services | Signed Linux worker recipes adopt installed media services | Qualified text-engine recipe, managed provisioning, context/cache/concurrency settings and resource telemetry |

See [private memory](PRIVATE_MEMORY.md), [client API](SHARED_TOOLS_AND_CLIENT_API.md), [managed workers](MANAGED_WORKERS.md) and [coverage](DESIGN_COVERAGE.md). A summarization profile or a successful short inference probe does not establish compaction fidelity, context capacity or runtime qualification.

## Three representations of a conversation

1. **Original records:** messages, permitted tool results and artifact references remain authoritative. Compaction never replaces or deletes them. Large outputs use bounded artifact references. Hidden model reasoning is not required for continuity.
2. **Working context:** current instructions, a validated summary, recent complete turns, relevant memory and the current user request form the input to the selected specialist.
3. **Cross-session memory:** user-editable notes and eligible historical sources remain separately controlled. A generated task summary is not automatically promoted into a preference or a verified fact.

The user can inspect which earlier turns were summarized and open their originals. Export derived summaries as clearly marked, source-linked Markdown while preserving full message exports. Corrections go through authenticated revision handling; do not let an edited exported summary silently replace its source history. Encryption at rest is a separate storage responsibility, not a reason to make summaries unreadable in the authorized UI.

## Context budget and compaction flow

- Select an eligible resident target, then calculate its input allowance from the effective loaded context limit, output/reasoning reservation, instructions, tool schemas, modality overhead and safety margin. Use a configurable working-context ceiling when a smaller prompt improves latency. Recalculate on a route change or failover.
- Record the provenance of context limits and token counts: exact tokenizer/template measurement, native provider report, administrator declaration or conservative estimate. A model's advertised maximum is not proof of its loaded limit. Generic OpenAI-compatible discovery does not guarantee a tokenization API; label estimates and preserve a margin.
- Trigger compaction before reaching the target's limit. Keep the latest request and recent complete turns intact, including paired tool calls/results. Pin unresolved tool state, pending approvals and artifact identifiers independently of narrative summarization. If required content alone cannot fit, report the limit rather than silently discarding it.
- Summarize a bounded older prefix using a configured, permitted resident text target. The existing `text.summarize` route is a candidate; define its internal execution permission explicitly so an ordinary permitted chat can compact without acquiring unrelated public capabilities. Compaction cannot broaden the user's scope, locality or cloud policy.
- Preserve the objective, user constraints/corrections, decisions and their sources, completed work and observed results, unresolved questions, next steps, and relevant paths/artifact references. Distinguish a proposal from an executed action and an assistant assertion from an observed result. Do not copy logs or large code blocks wholesale into the summary.
- Validate the output size, schema, claimed source IDs and coverage before committing it. Treat the summary as derived conversation data, never as system instructions or an execution grant. Syntactic validation cannot prove factual fidelity, so preserve originals and evaluate retention separately.
- Persist a versioned snapshot with covered message IDs/revisions, lineage, generating target/model, prompt version, budget measurements and scope generation. Publish atomically only if those sources and permissions still match. Invalidation follows source correction, exclusion, deletion and revocation semantics, including dependencies inherited through earlier summaries.
- Use bounded durable jobs and idempotent snapshot publication. Release the compactor's inference reservation before acquiring the answering target, including when both use the same resource pool. Cancellation and uncertain execution retain existing drain/no-replay rules. Do not hold a database transaction open across inference.
- A failed compaction keeps the previous valid snapshot and full history. Continue only if the remaining required context fits; otherwise expose a retryable failure. Prevent repeated unsuccessful compaction loops and silent history loss.

Incremental summaries may include prior summaries, but retain full original-source lineage. Rebuild from original records after invalidation and periodically check fidelity against the source; repeated summarization is lossy. The UI should show a compacting state, covered turns and an inspectable summary without exposing another user's content.

## External agent clients

Keep existing `/v1/chat/completions` caller-owned and stateless by default. A client may already summarize or prune its own history. The head cannot reconstruct context the client never sent, and neither server changes nor a new runtime make a client automatically adopt a new compaction protocol.

Design an explicit compaction request that returns a portable context package, plus optional session IDs/revisions for clients choosing head-managed history. Specify retention consent, scope, idempotency, concurrency and errors before adding these routes. Do not claim OpenAI Responses compatibility or support for OpenAI's encrypted compaction items. Preserve caller-owned tool schemas, call IDs and pending results; hearth must never execute a local client tool merely because it appears in a summary.

Workspace chat compaction can ship independently of these client extensions. Shared-channel compaction follows later with channel audience checks and no private-memory merging.

## Managed runtime contribution

Extend the worker with approved text-service recipes and eventual provisioning that report the actual tokenizer/template, loaded context, cache format, Flash Attention, speculative decoding, concurrency, residency and GPU/host allocation. Expose reviewed settings through Administration, with an explicit drain/reload operation for changes that require it. Report unsupported settings per backend rather than pretending every engine has equivalent controls.

Preserve the distributed default: different resident specialists on independent machines. Compaction is normal inference dispatched to an already eligible target, not an implicit model download or swap. Existing services remain under their operator's control until explicitly adopted. Linux systemd and Windows Job Object supervision now have bounded implementations; cross-platform provisioning and recovery qualification remain open.

Prompt compaction reduces the text processed on future requests. It does not by itself shrink a runtime's preallocated KV cache; context allocation remains a separate managed or operator-controlled setting. These two changes solve related but distinct resource problems.

## Delivery and acceptance order

1. Add context metadata/budgeting and durable private-chat compaction, with visible progress/source links. Qualify against the current LM Studio provider, including a conversation longer than the active working window that retains an early corrected requirement.
2. Verify route changes to a smaller context, complete tool-pair preservation, cross-user isolation, source edits during compaction, cancellation/restart, malformed/hallucinated source references, compaction failure and unchanged full-history exports. Fixtures use isolated storage on the existing VM; live tests use authorized synthetic content and do not replace user history.
3. Add opt-in client continuity after defining and testing the client contract. Demonstrate an actual client adopting it; keep current Continue/Hermes integrations working without the extension.
4. Deliver the managed text runtime on a supported worker with authenticated control, measured settings, resident-model enforcement and explicit provisioning/reload. Qualify head/worker loss and concurrent load separately. Continue accepting existing LM Studio and other compatible servers.

## Compaction comparison

[Official OpenAI documentation](https://developers.openai.com/api/docs/guides/compaction) describes both automatic server-side compaction and an explicit compact endpoint, returning opaque encrypted compaction items that preserve prior state with fewer tokens. It does not establish the pasted explanation's specific AES construction, exact hidden prompt or a universally separate compactor model.

hearth's proposed structured, source-linked summary is a portable application-level approach. It does not reproduce OpenAI's internal representation or guarantee equivalent retention quality. Its acceptance tests must measure whether the selected local compactor preserves the information needed to continue a task.
