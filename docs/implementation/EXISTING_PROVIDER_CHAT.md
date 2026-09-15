# existing local providers and private chat

Current update: [provider qualification](PROVIDER_LIFECYCLE.md) no longer expires after one hour. The hourly behavior described in this historical milestone has been superseded.

> Milestone record. [Capability routing](CAPABILITY_ROUTING.md) subsequently added connection editing, ordered per-capability assignments, explicit specialist selection and a native TLS connector. Pending statements about those items below describe the earlier slice. See [design coverage](DESIGN_COVERAGE.md) for current limits.

> Milestone record. [Capability routing](CAPABILITY_ROUTING.md) subsequently added connection editing, ordered per-capability assignments, explicit specialist selection and a native TLS connector. Pending statements about those items below describe the earlier slice. See [design coverage](DESIGN_COVERAGE.md) for current limits.

13 September 2026. This is a testable portion of P4 and ADR 0006, not completion of a phase or release gate.

The reference appliance connects to the user's existing LM Studio server at `http://127.0.0.1:1234/v1`, model `openai/gpt-oss-20b`. A development-only alias routes that address through QEMU's host gateway, `10.0.2.2`. LM Studio remains on Windows loopback. This bridge is not the production native connector and does not qualify another LAN host or plaintext network transport. Production configuration rejects development aliases.

## What works

- Administration has an authenticated **Providers** screen for connection, exact model selection, encrypted optional credentials, resource grouping, verification and disabling. A real model listing plus complete text/SSE probe assigns `chat.general`; verification expires after one hour. This proves a short chat exchange, not tool support, model quality, weight identity, maximum context or exclusive GPU capacity.
- Connections, model targets, capability bindings and resource pools are separate records. Existing services remain externally managed. Multiple models and URLs can share one pool with one generation slot. The first slice automatically binds verified text targets to general chat; a richer per-capability routing editor remains pending.
- **Private chat** saves conversations, ordered turns, partial answers and execution receipts in PostgreSQL. The backend consumes an upstream stream independently of browser lifetime. The browser polls committed text, checking its real audience-bound session on every read. A fresh session restores saved replies. Follow-ups include human turns and completed assistant replies within the explicit context limit.
- Requests are idempotent, with revision checks and no automatic inference retries. Forced personal RLS protects conversations, messages, runs and outbox records. Existing draft routes cannot read, overwrite or archive chats. The administration application cannot use personal chat endpoints.
- Stop response stops accepting answer text and drains the upstream stream to completion before releasing capacity. It does not claim to interrupt another application's model process. Session or target revocation also stops accepting output; local authorization is checked during persistence and identity tokens are introspected at dispatch, every five seconds of active stream events, and completion.
- A broken stream or lost process leaves an unknown execution receipt. Its partial text stays saved and its pool stays occupied until an administrator confirms the backend is idle. Receipt matching fences late writers and releases. The outbox is durable evidence of acceptance; it is not an automatic replay queue.

Only authorized administrators choose inference addresses. Addresses are normalized and DNS answers are pinned per request while preserving Host and TLS SNI. Redirects, metadata/link-local addresses, public addresses, URL credentials and network plaintext are rejected; certificate validation remains enabled. Loopback and private-network addresses still do not prove that an external operator avoids cloud forwarding, so the UI requires an explicit trust acknowledgement. No paid-provider path is enabled.

## Boundaries of this build

The UI displays answer text literally. It does not execute model output, render model HTML, enable tools or expose the administration agent. Reasoning fields are ignored. A live GPT-OSS follow-up exposed a leading Harmony header in LM Studio's content field. The adapter now recognizes a bounded set of observed final-answer headers for the exact GPT-OSS model identifiers, including headers split across chunks. Unsupported channels fail closed and require checking the server's chat template. This is a narrow compatibility profile, not a general Harmony/tool interpreter or model quality qualification. See the [upstream format](https://github.com/openai/harmony/blob/main/docs/format.md).

Limits are 32 configured targets per farm, 200 conversations per workspace, 4,000 input characters per turn, 16,000 UTF-8 bytes of full conversation context, 15 completed turns and, since the [reply streaming update](REPLY_STREAMING_AND_IDENTITY.md), 16,384 requested output tokens by default. Responses are bounded by bytes and time. Context is never silently truncated. After a stopped, failed or interrupted turn, you can continue the conversation; partial output remains saved but is excluded from the next model context. [Side notes, durable steering, shared channels and text-to-image](NOTES_CHANNELS_IMAGES.md) now extend this slice. Archive recovery, connection editing/key rotation, general admission queues, explicit target preferences, native connectors, signed model installation and admin tools remain pending.

## Evidence and reproduction

- [Live model evidence](../../evidence/inference/2026-09-13/live-chat.json): real LM Studio probe and two BFF chat turns with remembered context and fresh-session persistence. Identity is an explicit fixture in a disposable farm; the real user's Owner, authenticator and personal content were preserved.
- `tests/integration/test_chat.py`: restricted PostgreSQL access, CSRF/audience/role checks, idempotency, draft/chat separation, shared admission, cancellation, revocation, failure receipts and lost-execution reconciliation.
- `tests/security/test_inference.py`: bounded streaming, rejected URLs/redirects, DNS pinning, model mismatch, unsupported tools, incomplete events and the observed split-header regression.
- `tests/browser/chat.spec.ts`: UI fixtures for connect/verify, incremental rendering, reload, literal HTML and responsive layouts. Screenshots in the same evidence directory are explicitly labeled fixtures.
- [Brand HTTPS evidence](../../evidence/branding/2026-09-13-v1.2/brand-live.json): anonymous real HTTPS rendering with certificate validation enabled. No account provisioning or login was performed for these appearance checks.

The opt-in live test requires an already running local model and sends synthetic prompts only:

```powershell
$env:HEARTH_LIVE_CHAT_MODEL='openai/gpt-oss-20b'
uv run python -m pytest -q tests/integration/test_chat.py -k live_selected_model
Remove-Item Env:HEARTH_LIVE_CHAT_MODEL
```

The ordinary suite skips this test. The explicit development maintenance helper `scripts/connect_existing_provider.py` can configure and probe the chosen server through the restricted admin API container environment. It requires exactly one existing active Owner, preserves accounts and content, and never creates a browser session. Normal use goes through **Providers**.

Migration 0003 was applied after a private control-database backup in the appliance's ignored `.hearth/backups/` directory. This is not full backup/restore acceptance evidence. All 61 release gates remain open.
