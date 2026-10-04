# Decisions and routing: setup and operator testing

P5A adds an isolated CPU decision service, private typed Decisions UI/API, independently configurable internal classification, and selection-only NVIDIA NeMo Switchyard balancing. See the [design](../implementation/P5A_ROUTING_AND_DECISIONS.md), [implementation evidence](../../evidence/decisions/2026-10-04/validation.json) and [checkpoint benchmark](../../evidence/decisions/2026-10-04/benchmark.json).

## Current limits and defaults

The default remains **Legacy** intent routing and **Ordered** targets. Built-in member Decisions are enabled for accounts with `capability.decision.evaluate`. Existing member grants do not gain that permission automatically; Owners and FarmAdmins retain their role permissions. A decision proposes an answer and never executes a branch or grants access.

The pinned English Laya checkpoint is experimental. At answer-confidence threshold 0.85, 216 held-out synthetic examples had raw macro F1 0.736, accepted coverage 3.24%, and p95 wall time 1.66 seconds. All seven accepted examples were correct media requests; that tiny sample does not qualify media precision. The proposed 0.90 F1 and 250 ms p95 targets were not met. Use background comparison first. Do not lower the threshold merely to hide abstentions. Larger or better-calibrated dedicated providers can use the same contract; none is qualified by these results.

These cases use grouped English templates, not independent real-user traffic. Builds and fixtures shared the VM during the benchmark. There is no multilingual quality claim. Confidence for 11 or more choices has an upstream calibration warning; provider confidence and answer confidence remain separately labeled estimates.

## Install the built-in service on a Linux head

Run from the existing head checkout during a maintenance window, preserving its private state and volumes:

```bash
sudo python3 scripts/setup_decisions.py
sudo python3 scripts/head.py up
```

Preparation builds `hearth-decision:0.1.0` and downloads the exact reviewed checkpoint. Startup verifies its file digests and fails closed on a mismatch. No request downloads, loads or swaps a model. Existing checkpoints with a different revision require explicit migration. Setup does not replace farm configuration, accounts, keys or certificates.

The head helper adds `deploy/compose/decision.yaml` only when preparation has created the checkpoint manifest. The container is a non-root, read-only, network-disabled process with four CPU cores, a 6 GiB memory limit and a private Unix socket shared with the APIs. Observed resident memory was about 1.9 GiB. Without preparation, ordinary hearth features remain available and Decisions reports the built-in service unavailable.

Pinned components:

- Laya source: `8a6e1328cce2460a0e5aa348ad465bb1b5821cd2`.
- Checkpoint: `convaiinnovations/laya-typed-decisions`, revision `1a793eb568e6718f15941d08f85432581df534e3`.
- Decision protocol: `hearth.decision.v1`; maximum state 8,000 characters, four questions and sixteen options/rubric levels. Token limits are checked separately, with no silent truncation.
- Switchyard uses the existing pinned Linux CPU dependency. Its random policy selects among the supplied eligible IDs only; the selection clients cannot run inference or send prompts.

Dependency and model licenses remain separate from hearth's MIT license. This installation recipe is not a completed redistribution/SBOM qualification.

## Dedicated providers and separate assignments

Register a provider using **hearth decision provider**, its `/v1` base URL and the exact model identity returned by `GET /v1/info`. Supply its token through the normal credential field. Verify all three typed answers, then bind the target to **Decisions** in Capabilities. Multiple targets and independent machines are supported. Existing external HTTP services use the usual explicit LAN-risk approval; HTTPS certificates are validated.

The same image can serve authenticated TCP on port 8098 by setting `HEARTH_DECISION_TCP=1`, `HEARTH_DECISION_TOKEN_FILE` to a privately mounted token file, and `HEARTH_DECISION_MANIFEST` to its checkpoint manifest. The checkpoint must be explicitly prepared first; the process remains resident. Put verified TLS in front of this listener. The image itself does not issue worker certificates or expose an unauthenticated endpoint. A compatible third-party adapter must implement the checked info and evaluate schemas in the [shared contract](../../packages/contracts/schema/hearth.json).

**Administration → Settings → Routing and decisions** selects the internal source independently of member bindings. Dedicated mode refers to a verified target ID, never a model name inferred from text. The default fallback policy reserves part of the five-second routing budget for built-in Laya. With fallback disabled, unavailable classification returns an actionable error; explicit capability choices still work. Explicit member comparisons never silently substitute a different provider.

**Capabilities → Configure route** selects Ordered or Balanced for text, Vision and Decisions. Ordered keeps saved priorities. Balanced treats every supplied target as interchangeable and uses scoped affinity for a conversation; busy, stale, unqualified, revoked or unloaded targets cannot be forced by affinity. Priorities provide deterministic fallback, not random weights. Media retains its existing queue and worker behavior.

## Client API

Create a client key with `decision.evaluate`. Send `POST /v1/decisions` using Bearer authentication. This typed endpoint is separate from Chat Completions and is not a fake chat model in `/v1/models`.

```json
{
  "id": "dca91a31-c88e-4e6c-bf74-b63ecfa39b01",
  "state": "The parcel arrived on Monday.",
  "questions": [{
    "id": "delivered",
    "kind": "choice",
    "instructions": "Was the parcel delivered?",
    "options": {"yes": "Delivered", "no": "Not delivered"}
  }]
}
```

Omit `target_id` and `use_route` for the built-in service; set `target_id` for an explicit dedicated comparison, or `use_route: true` for the assigned Decisions route. These two selectors are mutually exclusive. Reusing an ID with identical input retrieves the existing job without executing it twice; different input returns conflict. The response contains job state, typed result and model/route receipt. Repeated in-flight calls may return the existing running record. API failures return an error, not a fabricated answer.

Scores return the expected zero-based rubric index; booleans return `probability_true`. Probabilities, provider confidence and confidence in the chosen answer are different fields. The UI supports one question per experiment; the API supports up to four.

## Testing sweep

Start with Legacy/Ordered and your existing accounts and providers. Do not reset the farm to run this checklist.

1. Refresh both browser surfaces. Confirm sign-in, OTP/SSO, workspace/admin separation, People grants and Farm map. Decisions appears only with its permission. The built-in node shows readiness and independent internal/member assignment.
2. In Decisions, try Choice, Score and Boolean. Check model/revision, probability labels, saved inputs and JSON export. Reload, delete a result, cancel a running job, and confirm another member cannot see it. Oversized/token-heavy inputs should fail clearly without shortened state.
3. Register a dedicated compatible decision provider, verify it, bind it, and run the same input against built-in, explicit dedicated and assigned-route choices. Changing the internal source must leave those member bindings unchanged. Ordinary LM Studio Chat Completions alone is not this typed provider protocol.
4. In Settings choose **Compare decisions in background**. Send unresolved paraphrases in private chat, a joined channel using `@hearth`, and client API `auto`. Existing replies remain on legacy routes. Your Decisions page shows bounded comparison metadata without raw prompt text or a duplicate reply.
5. Try **Semantic** deliberately, retaining the conservative threshold. Uncertain requests should ask for an explicit capability. Check each reply's routing receipt. Test quoted instructions as source material, references to recent turns, image discussion versus generation, unsupported requests and long input. Low coverage is expected with this checkpoint.
6. Select a dedicated internal source with fallback on, then make that test provider unavailable. Check the actual fallback source in the receipt. Repeat with fallback off. Direct specialist choices and direct image actions must remain usable. Restore/verify the provider after a real failure. Never kill a shared GPU service during somebody else's job.
7. Bind two verified, interchangeable resident targets to a text capability and select Balanced. Separate new conversations can select either target; a continuing conversation prefers its still-eligible target. Inspect receipts, busy-target exclusion and route-change conflicts. One user request must cause one downstream generation. Return to Ordered to restore priority behavior.
8. Retest conversational chat and coding, Enter/Shift+Enter, thinking display, Stop/Steer/side notes, long streaming replies and Continue. Confirm per-message model identity, memory recall and private history. Account/key revocation must continue to block new work.
9. Retest channels with and without `@hearth`, image batches in chat, gallery generation and uploaded-image variations, deletion, Make a model, 3D generation/preview/export, shared GPU queue switching and cancellation. Retest Vision uploads, transcription and read-aloud on their configured providers.
10. Retest Continue/Hermes with both `auto` and explicit capability aliases, streaming and caller-owned tool round trips. Retest shared MCP list/describe/run and scoped keys. Confirm the original credentials and trust package still work.

Provider outages with unknown execution retain pool fencing. Cancellation discards late decision results; an active Laya forward pass drains before its capacity is reused. An abandoned private decision is marked failed when revisited after its deadline, never replayed. Member experiments have separate bounded head admission and runtime lanes; CPU decision work never joins the image/geometry rotation.

## Rollback and remaining qualification

For behavior rollback, choose **Legacy** in Settings and **Ordered** on changed capability routes. This retains saved Decisions and member assignments. Removing only the decision overlay after draining its work disables the optional runtime. Keep migration 0029 and the newer API while preserving these records; database downgrade requires a reviewed backup restore, not dropping private tables in place.

The implementation is available for operator testing. Semantic promotion, independent real-user evaluation, a larger dedicated challenger, multilingual support, sustained-load qualification and complete release gates remain open. General orchestration, cloud routing and managed text-model lifecycle are separate phases.
