# Private memory and Obsidian vaults

Implemented 13 September 2026. Migration `0018` adds an owner-scoped knowledge store, editable notes, original-preserving message corrections, source-linked recall, and a durable Markdown/JSONL projection. This is a first P7 slice. No full release gate is closed.

## Try it

1. Open **Memory** in your personal workspace. Save a note such as “My telescope is named Juniper.” Choose **Preference** when a fact or writing preference should be considered for every private text reply.
2. Start a new chat and ask what your telescope is named. The reply's **Memory used** section links to the exact source ID and revision used. The source viewer shows its current revision and retained edit history.
3. Correct the note, start another chat, and ask again. Remove a note or exclude a conversation to stop cross-session recall. You can also pause all cross-session memory.
4. Search the archive, or choose **View messages** on a conversation. Archived conversations remain accessible. Select a message to correct it. Corrections retain the original text, original authorship/model identity, and subsequent revisions; the chat marks edited messages.
5. Choose **Download Obsidian vault**, extract it into a new private folder, and open that folder as a vault in Obsidian. Edit an individual file in `notes/` or `messages/`. Back in hearth, choose **Import edited Markdown**, review the content, then apply it. New plain Markdown files become new notes.

Desktop Obsidian files do not continuously synchronize in this build. Imports require the current source revision and authenticated scope. A stale file is rejected with no overwrite. Editing generated whole transcripts is not supported; edit the corresponding individual message instead. Preserve IDs, scope, farm, type, and revision properties. The exported JSON-quoted YAML scalars and ordinary scalar properties written by Obsidian are accepted; tagged/aliased or nested metadata is rejected.

## Storage and recall

PostgreSQL is authoritative for identity, ordering, ACLs, revisions, and complete visible message text. The new tables use forced owner/farm row security under the restricted application role. The administration API cannot open personal memory. Shared channels, private drafts, image planning, and the administration agent do not receive private-chat recall in this slice.

Notes have note/preference/decision kinds, an enabled flag, and immutable revision rows. Messages retain their originals on first correction. Completed audio derived from corrected text is invalidated; a running conversation or speech job must finish before that message is edited. Removing a note creates a tombstone and removes it from recall, while retaining private revision history. Exclusion is not physical deletion.

English PostgreSQL full-text indexes provide word matching, with SQL scope filtering before ranking. Preferences receive priority; up to eight source excerpts fit a maximum 4,000-byte recall allowance, within a 16,000-byte text-context envelope, excluding fixed system instructions. Image payloads are counted only against the attachment limits, not as text. The normal recent window is at most 30 visible messages and 12,000 UTF-8 bytes. An oversized latest user message remains intact; the tail of a large preceding assistant answer can be retained for continuation. Complete source text remains stored and exportable. This is context windowing, not model-generated summary compaction or context-length negotiation.

Short explicit memory follow-ups also search the preceding user question. For example, “it's not in your attached memory system?” after “what is my name” retains the name topic. Note titles convey the meaning of short values, so an ordinary enabled note titled “Users Name” with a name as its body can answer that question, including in a conversation containing images.

Every private text or vision turn supplies the model with the actual recall state. Specialist and memory instructions share one leading system message for compatible model templates. Replies show source links when recall succeeds, or explain that recall was paused, found no matches, or had insufficient context space. Older receipts without the status field remain readable.

Retrieved excerpts are quoted JSON data, explicitly not instructions or authority. The request's current provider and locality policy still govern dispatch. Sources, revisions, and recall settings are rechecked before generation and publication. Corrections/exclusion/removal also invalidate dependent historical answers through bounded source-lineage checks. An old assistant answer cannot reintroduce a removed note through the supported recall path. Previously visible text remains in the transcript. A stale execution drains and stops publishing, without falsely marking its provider unhealthy.

`memory.index` and `memory.retrieve` are now provided by the private knowledge store on the head. Their capability cards open Memory. They are not model-server routes: pre-existing intended model assignments remain stored but cannot grant memory execution to a chat provider. External knowledge-worker placement remains open. Resident inference models continue to run on their configured machines without loading or swapping for recall.

## Vault projection and migration

Committed note/message/conversation changes enqueue `memory.vault.changed` events transactionally. The admin service projects each principal through a separate RLS transaction into `HEARTH_MEMORY_VAULT_PATH/<farm UUID>/<owner UUID>/`. The development stack mounts the named `memory-vaults` volume at `/var/lib/hearth/vaults`, owned by UID 10001. This directory is not exposed through the web server or as a general network share.

The projector coalesces generations, uses atomic file replacement, records its completed generation, and retries filesystem failures. Committed database history remains safe if the vault is unavailable. Unexpected file edits are preserved in `conflicts/` before regeneration. Paths are generated from opaque IDs, never note titles or imported paths. Generated obsolete note files disappear after removal; the private revision log retains their history. Exports are built from the current committed database state, even while the server projection is behind.

Each export contains readable conversation Markdown, individual editable messages/notes, exact message JSONL, revision JSONL, an explicit-link graph, and a hash manifest. Attachments are represented by IDs and provenance; image/audio binaries are not included. This is a text/history export, not a full appliance backup. User-controlled downloaded copies are outside server deletion control.

When moving the head to a Linux VM, migrate PostgreSQL using the eventual reviewed head backup/restore workflow. The vault is a derived copy and can be rebuilt from that database. The Compose volume and path configuration are already included; Obsidian itself runs on the user's computer. A separately placed knowledge service, NAS spooling, full head installer/restore acceptance, quotas, encryption at rest, and backup deletion ledgers remain unfinished.

## Graphify

Obsidian can display the explicit `[[note ID]]` and transcript/message links without another service. `graph.json` contains only nodes and edges in the exported private scope, excluding disabled/tombstoned notes, excluded conversations, and invalid dependent recall sources.

The optional offline adapter invokes the actual pinned `graphifyy==0.1.14` build/export functions:

```powershell
uv run --group knowledge python scripts/graphify_vault.py C:\path\to\vault\graph.json C:\path\to\new-graph-folder
```

Choose a new output directory. IDs and paths are validated before passing generated metadata to Graphify; user titles are not passed into upstream filenames/frontmatter. The adapter does not invoke the extraction CLI, call a model, or use cloud credentials. This produces an explicit-link graph, not semantic extraction. Rebuild derived exports after corrections or exclusions. Local semantic entity/relation extraction, topic assertions, richer graph navigation, embeddings, and Graphify process/egress isolation remain future P7 work.

## Validation

[Validation](../../evidence/memory/2026-09-13/validation.json) records exact deployment and test counts. [Live recall](../../evidence/memory/2026-09-13/live-recall.json) used the real resident LAN Qwen model, a real restricted-role PostgreSQL database, and two fresh conversations in a disposable farm with explicit OIDC fixtures. It returned the original test name, then the corrected name, with current source revisions and unchanged loaded models.

Integration regressions cover RLS/CSRF/audience boundaries, revision conflicts, cross-scope imports, original-preserving corrections, long history export, Unicode windows/continuation, in-flight source edits, tombstone lineage, projection retry/conflict handling, and Graphify with network connections blocked. Browser fixtures cover note editing, reviewed import, recall toggle, source links, and responsive layout. Source identity and infrastructure checks do not substitute for full production signup, semantic retrieval quality, complete deletion, or ESX migration qualification.

### Vision recall correction

The initial recall budget mistakenly serialized multimodal image data as text. An earlier attachment could exhaust the allowance and silently omit an otherwise matching note. The corrected path budgets only text parts, preserves the image payload, and reports the actual recall state. [Live regression evidence](../../evidence/memory/2026-09-13-vision-fix/live-recall.json) covers an ordinary name note after a retained image, followed by the exact memory-system follow-up. Resident LAN Qwen answered both from the saved source and correctly described hearth memory. The fixture used a disposable farm and did not change real user notes, chats, or model residency.

[Correction validation](../../evidence/memory/2026-09-13-vision-fix/validation.json) includes the full Windows/Linux checks, browser status regressions, exact deployed backend/frontend hashes, verified HTTPS, unchanged provider bindings and private-vault permissions.
