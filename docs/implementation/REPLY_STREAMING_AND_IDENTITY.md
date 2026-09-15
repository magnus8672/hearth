# hearth reply streaming and model identity

Updated 13 September 2026.

The user successfully routed a greeting to local GPT-OSS and a coding task to Qwen on another machine. The coding reply stopped after 53 visible characters. Its saved execution receipt reported `finish_reason=length`, with no API error. The transport requested only 768 completion tokens, leaving too little room for a reasoning model's answer.

## Reply limits and recovery

Normal private-chat and channel replies now request up to 16,384 completion tokens. This is a ceiling, not a requirement to generate that many tokens. `HEARTH_CHAT_MAX_OUTPUT_TOKENS` allows an operator to set 256 through 65,536. It covers the provider's completion budget, including reasoning where the provider counts it. It does not override the provider's own context or output limits.

Interactive streams may remain active for 900 seconds, configurable through `HEARTH_CHAT_TIMEOUT_SECONDS` from 30 to 3,600. A 30-second read-idle timeout, a 16 MB total stream bound and a 256 KiB pending-event bound remain. Explicit verification and image-planning token budgets retain their existing limits and 180-second duration. Stop/steer, receipt fencing, session checks and capacity leases remain enforced; cancellation drains the provider instead of freeing capacity while it might still be generating.

A `length` finish is preserved and visibly marked on the individual private reply. **Continue reply** starts a new, explicit turn using the same capability assignment and saved context. It does not silently replay or retry the interrupted generation. The button waits while an unsent draft is present. A changed capability assignment can select a different provider for that next turn. Channels save their own incomplete-reply warning and invite an explicit `@hearth` continuation.

The existing 16,000-byte private conversation context limit remains. Very long replies can fill that context and require a new conversation; context-window negotiation and longer-history management remain open. This fix does not promise unlimited output or conversations.

## Identity on every reply

Private chat now returns each run's `assistant_message_id`; the UI associates replies by this durable ID, not by array position or the latest header. Model identity comes from the existing saved execution receipt. Earlier legacy receipts retain the historical migration's documented provenance limitation. A missing association or model receipt is shown as **Model not recorded**, without borrowing the provider's current model name.

Migration 0014 adds a model-name snapshot to shared channel messages and backfills it from existing run receipts. Other joined members can see that public attribution without reading the author's private execution record, session hash or credentials. Retargeting a server does not relabel old replies.

Image replies use the model recorded in each image request, including after a text planner hands off to image generation. Planning-model details remain in Image details. Private and channel replies share one heading component, with wrapping model names on small screens.

## Verification

- Windows full checks: 208 Python tests passed, 9 optional tests skipped, all Go packages, 156 shared TypeScript cases, type checking and both production builds passed.
- The final missing-receipt refinement passed all 10 routing/identity regressions and type checking. Linux qualification built successfully; the final full suite is also run against the current mounted sources in that qualification image, with results in the validation record.
- Browser regressions: 22 passed and 1 optional readiness case skipped. New cases cover two different models in one transcript, reload, unknown historical identity, continuation capability, draft preservation, shared-channel attribution and image attribution. Desktop and mobile screenshots were inspected.
- Real remote Qwen: the same Fibonacci request finished normally in 22.204 seconds, with 1,526 answer characters and 519 visible text chunks. Both complete Python blocks parsed successfully; no model-authored code was executed. A fresh BFF session restored identical messages and model identity. The loaded model remained unchanged.
- Database regressions cover private turn association, preserved identity after retargeting, explicit continuation, shared model identity without access to another author's run, and channel output-limit reporting.
- Transport regressions cover the increased default, configurable budget, unchanged probe budget, streams beyond the former three-minute bound, eventual timeout and `length` receipts.

See [live Qwen evidence](../../evidence/replies/2026-09-13/live-qwen.json), [the generated test answer](../../evidence/replies/2026-09-13/live-code.txt), and [deployment validation](../../evidence/replies/2026-09-13/validation.json). The real model test uses real PostgreSQL and both BFF APIs with explicit OIDC fixtures in a disposable farm; it does not modify the user's conversations or provider assignments.

Sequential routing across the user's two machines is now user-confirmed. Concurrent physical-host acceptance, full residency control and the remaining modality adapters are still open. No release gate is closed by this patch.
