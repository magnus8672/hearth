# P7: shared conversation history and topic memory

Dependency: P6. Outcome: the farm recalls authorized earlier conversations through source-cited retrieval and inspectable vaults.

## Build

Provision the knowledge service and approved extraction/index dependencies through central service recipes in [11](../../../plan/11-INSTALLATION-AND-CENTRAL-MANAGEMENT.md). Vault scopes and storage/engine settings originate in Hearth, not member-side files. Service installation may not broaden access to private memory partitions.

1. Implement message/artifact outbox projections into scoped Markdown/JSONL vaults, revision tracking, NAS outage spool, authenticated export and authored-note import.
2. Add topic assertions, decisions, preferences, temporal supersession, evidence labels and complete source lineage.
3. Implement PostgreSQL full-text retrieval and explicit topic traversal with scope filtering before ranking. Add context budgeting and authenticated source citations.
4. Package the knowledge role and pinned Graphify adapter. Run isolated partition exports with explicit local backend, validated output and incremental updates.
5. Build Memory UI, corrections, exclusions, deletion tombstones, dependent-record rebuild, cache invalidation, backup deletion ledger and restore checks.

## Prove

E12-E15 and S04-S05, S12-S13, S17. Retrieve a prior decision using a different model, identify its later correction, and verify exact original-message citations. Delete that conversation during an active indexing job and prove it cannot reappear in graph, summaries, caches or restored state.

Use two users with intentionally similar topic names to expose leakage. Run with all internet egress blocked; Graphify must use only the configured local model endpoint. Its failure must leave baseline permitted search functional. Open the exported vault in an Obsidian-compatible viewer and inspect links and records.

## Exit gate

Real conversational recall, actual Graphify integration, vault export/import and complete deletion behavior are evidenced. A static graph picture or summary-only mock does not satisfy memory integration.

Next: [P8](../../../plan/phases/P8-COLLABORATION-AND-MEDIA.md).
