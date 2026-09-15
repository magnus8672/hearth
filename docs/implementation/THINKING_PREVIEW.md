# Thinking previews in private chat

Implemented 13 September 2026 with migration `0019`. Private chat now exposes the reasoning text a provider explicitly streams in `delta.reasoning_content`, separately from its answer. The panel starts collapsed. Open **Thinking** while the reply runs to watch updates and decide whether to steer from the composer or a side note.

## Interaction

The disclosure remains open across polling updates. Its text follows new chunks while you are reading at the bottom; scrolling up pauses that following until you return to the bottom. A bounded inner viewport keeps the composer usable. Keyboard users can expand the disclosure and focus/scroll its text. Provider text renders as plain text, including any HTML or script-looking strings.

The **streaming** label reflects the most recently received reasoning event. It disappears when answer text starts, or changes to **stopped** after cancellation or failure. A provider that sends no reasoning gets no invented thinking panel. The waiting placeholder says **Waiting for the model…**, rather than asserting that the model is reasoning.

You can type and press Enter to steer, or choose **Steer with this** on a side note, while the panel is open. Existing cancellation semantics remain: publication stops, the old request drains while holding its resource group, and an accepted replacement starts afterward. The panel does not introduce provider-specific immediate cancellation.

## Storage and boundaries

Thinking is stored in separate `chat_runs.reasoning_text` columns under the existing forced owner/farm row security. It is returned only by the authenticated personal-chat API, with the same session, source-revision and provider checks as answer publication. Cancellation, session revocation, stale memory or provider changes stop further thinking publication too. Previously received text remains with its reply and can be reopened in that conversation.

Each preview retains a contiguous prefix of at most 65,536 UTF-8 bytes. The UI says when the preview was shortened. Reaching that limit does not stop the answer or stop draining the provider. Stream-wide size/time bounds remain active.

Reasoning never becomes message content, a future model prompt, memory-search input, a vault/Graphify export, a Read aloud source, or tool-execution authority. General PostgreSQL backups include the saved preview because it is durable private conversation data. It shares the conversation's existing retention limitations; removing a memory note is not physical deletion of prior thinking or answers.

Only private chat opts into reasoning from the transport. Provider verification, shared channels and image planners retain their answer-only behavior. This slice supports the separate field confirmed on the real LM Studio Qwen instance. It does not parse arbitrary `<think>` tags or reinterpret unsupported model channel headers.

## Validation

[Live Qwen evidence](../../evidence/thinking/2026-09-13/live-qwen.json) uses the resident LAN model, restricted-role PostgreSQL and actual BFF executor in a disposable farm with explicit OIDC fixtures. It verifies incremental thinking before the answer and restoration after reopening, with no model loading/swapping or cloud inference. The evidence retains sizes and the synthetic arithmetic answer, not the thinking text.

Regression coverage includes opt-in stream separation, malformed reasoning, tool-call rejection, UTF-8 preview limits with continued answers, owner isolation, session revocation, stopping and side-note steering during thinking, export/recall/prompt exclusion, keyboard disclosure, literal HTML display, scroll position, restored replies and mobile width. This adds implementation evidence; none of the 61 full release gates is closed.

[Validation record](../../evidence/thinking/2026-09-13/validation.json) includes complete Windows/Linux checks, browser counts and final captures, verified HTTPS, matching deployed backend/frontend hashes, and preserved provider bindings.
