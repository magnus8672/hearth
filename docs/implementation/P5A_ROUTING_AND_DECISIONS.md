# P5A: routing and decision services

Implementation update, 4 October: the service, selection, classification controls and direct Decisions UI/API below now have bounded implementations. Migration 0029 adds the fifteenth profile. See [setup and operator testing](../operations/DECISIONS_SETUP_AND_TESTING.md) and [evidence](../../evidence/decisions/2026-10-04/validation.json). Legacy/Ordered remain defaults. The pinned English checkpoint's 216-case held-out benchmark reached 0.736 raw macro F1, 3.24% accepted coverage at 0.85 confidence and 1.66 seconds p95, so semantic promotion and full phase acceptance remain open. The following design and proposed targets are retained as the acceptance baseline.


Phase design, 4 October 2026. The operator has selected built-in Laya on the head for the initial internal decision service, with configurable use of a dedicated decision capability. Implementation and qualification remain pending; the exact Laya checkpoint/runtime still requires review. This phase extracts local routing work from [P5](../plan/phases/P5-ROUTING-AND-CLOUD.md), with a narrow connection to [P8](../plan/phases/P8-COLLABORATION-AND-MEDIA.md). The preserved baseline and all 61 release-gate statuses remain unchanged.

## Outcome and recommendation

Use a decision model to determine what kind of help an ambiguous request needs, Switchyard to select among eligible model targets, and hearth to authorize, schedule and execute the work. Add direct access to typed decisions as a separate capability. These functions can share infrastructure without becoming one model call or one authority boundary.

The proposed flow is:

1. Authenticate and scope the request. Explicit UI actions and explicit capability aliases establish intent without a classifier.
2. For automatic routing, apply narrow, tested direct-action recognition first. Send unresolved intent to a bounded local decision service, with an explicit uncertain outcome.
3. Validate the proposed capability against hearth's catalog and the caller's permissions. Build a compatible candidate set from operator assignments and current evidence.
4. Use the configured Switchyard selection policy where supported; return a target identity, not a generated answer or executable command.
5. Recheck route revisions and capacity, then let hearth admit or queue the job. Its scheduler owns fairness, reservations, approved backend changes and cancellation.
6. Dispatch through the existing typed transport and record both the intent decision and actual provider selection.

This is the recommended logical order. Switchyard could call a decision adapter internally in a later integration, but semantic classification still precedes choosing the execution target. Selecting a provider first and then discovering the required modality would invert that dependency. Do not classify the same request twice just because both integrations support a classifier.

## What the code does today

| Responsibility | Current implementation | Gap this phase addresses |
|---|---|---|
| Capability intent | [`routing.text_capability`](../../services/api/src/hearth/routing.py) uses English patterns and explicit overrides; [`conversation_media.intent`](../../services/api/src/hearth/conversation_media.py) handles image actions separately | Semantic handling of paraphrases, uncertainty and supported languages |
| Provider selection | `routing.select` checks capability permission, compatible verified features, priority and available capacity under locks | A live, observable Switchyard policy with preserved admission checks |
| Switchyard | [`adapters.SwitchyardRouter`](../../services/api/src/hearth/adapters.py), pinned `nemo-switchyard==0.2.0`, and a real-package selection test | Not called by live dispatch; currently returns selection-only receipts and randomly resolves equivalent finalists |
| Scheduling | [`image_queue`](../../services/api/src/hearth/image_queue.py) selects owners fairly within a pool and prepares the chosen approved media backend | Decision-service admission and isolation; no replacement of existing media fairness |
| Direct decisions | Fourteen catalog profiles; no typed decision capability | Provider verification, contracts, API access and a member-facing Decisions page |

Live selection is shared by private chat, channels and the client API, with explicit paths for audio and media. The current route editor requires distinct priorities. The adapter's quality and queue fields are a foundation abstraction, not evidence that live quality-ranked scheduling already exists. Simply calling a random selector with one finalist would not complete this phase.

## Roles and boundaries

**Decision service:** interprets scoped content and proposes a catalog capability, or abstains. It cannot select a hostname, change permissions, authorize cloud use or enable a tool. It sees only the current user request and the bounded context needed to resolve references. Historical text remains evidence, not a new instruction. Classification confidence is a model result, not a permission check.

**Switchyard:** chooses within hearth's allowed candidate set. Start with selection-only clients, retaining the [ADR 0001](../adr/0001-foundation-and-upstream-adapters.md) boundary. Library failure falls back to a declared deterministic policy over the same eligible set; an out-of-set answer is rejected. No automatic retry after partial generation or an unknown execution outcome.

**hearth:** owns capability definitions, authorization, locality, verified features, residency requirements, pool identity, fair scheduling, approved lifecycle changes and final dispatch. Busy, offline and unsupported must remain distinguishable. Selection is revalidated immediately before admission; never hold database locks while waiting for a decision model or asynchronous selector.

A shared-media service that is intentionally nonresident may be eligible to queue, but cannot execute before the worker confirms readiness. The existing adapter's resident-only filter must not be applied blindly to those jobs. LLM routing algorithms are not assumed to understand GLB, PNG or audio job protocols. Initial Switchyard integration covers compatible text/decision targets; media keeps its typed provider selection and scheduler until a selection-only multi-provider media policy is explicitly qualified.

Explicit image generation, uploaded-image editing, Generate model, Read aloud and transcription bypass semantic classification. Complete channel image requests retain their independent dispatch path. A shared channel attachment does not silently enable Vision or send pixels to a decision model. Uncertain automatic media intent asks for clarification rather than starting an unwanted generation. An unavailable assigned capability produces an honest unavailable/queued result, not a misleading chat answer.

## Candidate models and serving approach

The following are upstream descriptions checked on 4 October, not measurements on this farm:

| Candidate | Relevant properties | Proposed role |
|---|---|---|
| Laya | Public project lists 421M English/typed-decision checkpoints and a 322M multilingual checkpoint, with CPU serving paths. Context and calibration differ by checkpoint. | Selected initial built-in head service; qualify the checkpoint, CPU budget, latency and quality before enabling semantic routing |
| Clef-Flash | 9B multimodal model with Apache-2.0 weights and a separate joint decision head | Local challenger if its measured quality improvement justifies memory and latency |
| Clef | 27B multimodal model, also with a joint decision head | Larger quality comparator; do not make a large resident classifier a prerequisite for every request |
| Jev | TypeSafe documents typed Choice, Score and Noul results through its System One API | Optional hosted adapter later, subject to the cloud boundary; not a dependency of local routing |

Sources: [Laya project](https://github.com/NandhaKishorM/laya), [Clef-Flash model card](https://huggingface.co/Cloudflare/clef-flash), [Clef model card](https://huggingface.co/Cloudflare/clef), [TypeSafe introduction](https://docs.typesafe.ai/introduction).

Clef's supported decision path includes `joint_head.safetensors` and `joint_schema_model.py`. Loading its backbone as an ordinary chat model does not qualify that path. Review and pin the full runtime/model closure before installation; do not assume LM Studio's chat endpoint or a GGUF conversion preserves typed decisions and probabilities. Cloudflare's published runtime testing is on an H200, not evidence of fit on our deployment hardware. [Clef-Flash serving instructions](https://huggingface.co/Cloudflare/clef-flash#usage)

Prefer a small, persistently available decision service with independently reserved capacity. Evaluate CPU placement before allocating a scarce media GPU. Never unload an image or geometry backend merely to classify the next request. Direct decision jobs must not starve internal routing: give internal calls bounded reserved capacity and direct calls fair quotas, with visible overload. No model download or lazy checkpoint switch on the request path.

Laya's maintainers explicitly document checkpoint-dependent confidence and calibration problems. Use held-out hearth examples to set thresholds; do not treat a reported 0.9 as a universal 90% correctness guarantee. Preserve provider confidence separately from option probabilities and any hearth abstention policy. [Laya evaluation and calibration notes](https://github.com/NandhaKishorM/laya#calibration)

## Selected placement and configuration

Build Laya into the head deployment as a supervised CPU service behind hearth's typed decision adapter. Keep its model process isolated from the API processes, with bounded CPU threads, memory, input size, concurrency and deadlines. Share one resident model instance across head callers rather than loading a copy in each API worker. Stage pinned, reviewed weights during setup; report loading, ready, busy and failed separately. A Laya failure must not take down head authentication, administration or explicit capability dispatch. Packaging it with the head does not require giving it network access or database/admin credentials.

Expose two independent administrator settings:

| Setting | Default / choices | Behavior |
|---|---|---|
| Internal routing decision source | Built-in Laya; or a configured dedicated `decision.evaluate` capability binding | Chooses the service used for hearth's fixed intent questions. Dedicated mode requires an explicitly selected, verified, local binding with compatible decision features. |
| Member Decisions capability assignments | Independently configured eligible decision targets | Lets members experiment with the built-in service and dedicated providers without changing the internal classifier. Existing capability permissions still apply. |

Keep built-in Laya available when a dedicated target is assigned. Selecting an external decision capability for internal routing must not overwrite member assignments or uninstall Laya. Likewise, adding a 9B or 27B provider must not silently redirect internal calls. Both placements use the same versioned adapter contract; supported question kinds, context limits and confidence semantics remain provider-specific verified features. Show the built-in decision node inside the head's machine box on the farm map and dedicated targets under their actual hosting groups, separating configured assignment from observed residency and readiness.

The internal setting refers to a stable capability binding/target identity, not a hard-coded address or a model name parsed from UI text. Resolve that binding directly, applying current authorization, locality, readiness, capacity and revision checks; never send the classifier's own request through semantic `auto` routing. Selection among interchangeable dedicated targets may use the selection-only Switchyard policy without invoking another intent classifier. Configuration changes affect new requests; in-flight requests retain their source revision and must not be executed twice.

Dedicated mode also exposes an explicit **fall back to built-in Laya** policy, initially enabled, within a single bounded routing deadline. Record the attempted source, fallback reason and actual model used. If no qualified source can answer in time, use the safe direct paths or clarification behavior described below. A malformed or unauthorized provider result cannot widen the permitted candidate set. Direct member requests targeting a particular provider must return that provider's failure rather than silently substitute another model, preserving useful comparisons.

For simultaneous experiments, the Decisions page can explicitly select an authorized built-in or dedicated target and retain its identity with the result. An opt-in administrator shadow comparison may evaluate the same bounded intent on both local services, but only the primary decision can affect routing. Shadow work has separate bounded capacity and must never delay primary dispatch, trigger duplicate downstream jobs or retain raw private prompts in global logs. Start with manual comparison; automatic shadow sampling is a later rollout step in this phase.

Reserve a small, bounded share of decision capacity for internal routing and apply per-user limits to member experiments. The built-in CPU service uses its own resource budget; a dedicated provider uses its real resource pool. Do not place it in the media switching rotation merely to run classification. Future dedicated 9B/27B hardware can replace the internal source through configuration after qualification, without a new routing implementation.

## Switchyard integration choices

The current upstream documentation describes task, stage and escalation strategies. Its `capability` classifier estimates whether an efficient model can solve a task; that term is not automatically equivalent to hearth's `image.generate` versus `code.implement` catalog. Its judge expects a particular structured verdict. A System One response needs an explicit adapter and suitable evidence before it could supply that verdict. Intent confidence must not be relabeled as a model's probability of solving the task. [Switchyard classifier documentation](https://nvidia-nemo.github.io/Switchyard/routing_algorithms/llm_classifier_routing/)

Audit the actual pinned library entry points first. Website/main-branch documentation does not prove the pinned build exposes the same API. Retain the approved Linux CPU baseline and its verification; a dependency upgrade is a separate, recorded qualification. See [upstream changes](https://github.com/NVIDIA-NeMo/Switchyard/blob/main/CHANGELOG.md).

Preserve **ordered** routing as the compatibility policy. Add an explicit opt-in **balanced** policy over administrator-approved interchangeable targets, using a strategy verified against the pin. Do not silently turn distinct priorities into random weights. A later **measured quality** policy requires capability-specific evaluation data and a documented quality/latency tradeoff; connection success alone is insufficient. Affinity is scoped by farm, user, conversation and capability, and is invalidated by changes to authorization, bindings, readiness or residency. It must not force a busy target when the configured policy permits an equivalent idle target.

## Direct decision capability

Proposed public capability: `decision.evaluate`, with an independently verified provider profile and permission. It is distinct from `reason.plan` and free-form extraction. Start with text/structured state plus a bounded set of typed questions:

- **Choice:** select a supplied option; return its stable ID and available option probabilities.
- **Score:** evaluate a supplied ordered rubric; preserve the rubric and provider result semantics.
- **Boolean probability:** return the probability of yes/true; adapt the upstream `noul` field without confusing it with confidence in an answer.

Include request ID, model/provider revision, schema revision, timing, truncation/limit status and abstention in a versioned hearth receipt. Validate finite values, ranges, option membership and probability structure. Preserve unavailable fields as unavailable rather than manufacturing confidence. Examples include categorizing a document, choosing a workflow branch, or scoring a draft against a rubric. Results do not execute the selected branch.

Deliver a **Decisions** workspace page with state input, typed question controls, probability/rubric results and JSON export; corresponding authenticated browser and scoped client API endpoints; and discovery in Capabilities and the Admin farm map. Endpoint names and any System One compatibility facade are design work, not existing API promises. A future chat tool can call this capability, but its raw typed result must remain inspectable separately from a generated explanation.

The internal intent classifier uses an administrator-owned question template and a directly configured decision-service binding. It must never route recursively through `auto` to discover its own provider. Direct users cannot replace that internal template or gain access to private classification history.

## Delivery slices and acceptance

| Slice | Deliverable | Required evidence before proceeding |
|---|---|---|
| A: baseline and benchmark | Freeze routing cases; audit the Switchyard pin; qualify Laya on the head CPU, with optional dedicated challengers | Capability confusion matrix, false media actions, abstention coverage, calibration, warm/cold latency, memory and contention; initial selection is not a performance claim |
| B: decision service | Versioned contracts, isolated built-in Laya service, dedicated-provider adapter/binding, independent internal/member settings, private result storage, limits and provider probe | Real typed answers through both placements, live source changes and explicit fallback, malformed/oversized input rejection, user/farm isolation, cancellation/timeout and context-limit behavior; no silent truncation |
| C: live Switchyard selection | Ordered compatibility plus an opt-in balanced policy, scoped affinity, admission recheck and route receipts | Real upstream invocation selects among at least two eligible targets; one inference dispatch only; stale, denied, incompatible and busy targets excluded appropriately |
| D: semantic auto routing | Bounded decision call on unresolved intent, thresholded abstention, explicit-choice bypass and shadow comparison | Private/chat/client consistency, adversarial quoted instructions, contextual references and multilingual cases; classifier failure cannot block direct media actions |
| E: direct use and rollout | Decisions page with explicit target comparison, scoped client access, admin source/fallback controls and map status, optional shadow comparison, operator-visible selection reason and rollback switch | Real end-to-end decision requests through both placements and staged opt-in rollout; legacy routing remains available; privacy-reviewed evidence |

Proposed evaluation starts with at least 300 labeled cases separated into threshold-tuning and held-out sets. Include paraphrases and unsupported requests, explicit overrides, image discussion versus image generation, editing versus new generation, batches, channel mentions, quoted instructions and ambiguous follow-ups. Test only languages the candidate actually claims to support. Set the promotion thresholds before scoring the held-out set. Initial targets for discussion are macro F1 at least 0.90, at least 0.99 precision for automatic media actions, and p95 routing overhead at most 250 ms on the designated runtime under representative concurrency. Report coverage and sample counts beside those figures; do not hide low-confidence cases or promise those targets before measuring.

Hard regressions must all pass: no unauthorized capability/egress, no channel/private context crossover, no recursive routing, no duplicate execution, no image starvation behind an independent chat, no media unload caused by classification, and no loss of cancellation or uncertain-execution fencing. Internal classifier timeout falls back to the explicit/direct paths or an honest clarification; direct decision API requests receive a structured timeout/unavailable response, never a fabricated judgment.

Placement acceptance also covers head API responsiveness under saturated Laya load, recovery from a killed model process, dedicated-provider outage with fallback enabled and disabled, stale/deleted bindings, concurrent configuration changes, and member experiments while internal routing is active. Verify that switching the internal source leaves member assignments unchanged, that every response identifies the actual model, and that shadow failures cannot affect the primary request. Qualification of a dedicated adapter does not require purchasing or installing a large model; distinguish transport fixtures from real model evidence until that hardware is available.

Run semantic inference outside admission transactions, then acquire the needed locks and recheck state. On route changes while queued, preserve the existing revision-fence behavior; automatic cross-pool migration is separate work. Record classification model/template revision and selection policy/candidate-set revision without recording raw private prompts in global operational logs.

## Roadmap boundaries and discussion points

The [active roadmap](ROADMAP.md) tracks this phase under R10/R35 alongside the independent [context continuity design](CONTEXT_CONTINUITY_PLAN.md). Typed intent decisions do not replace context budgeting or compaction. Neither slice requires completion of the other, and the chosen routing decision model is not automatically a qualified summarizer.

P5A advances the local portions of P5 items 1–2 and extends its client-access work with decisions. It contributes evidence to E07/E09/E15/E16 and S06/S17; it does not close those entire scenarios. Central configuration contributes to C03/C04 but does not implement automatic provisioning. It prepares a typed specialist result for P8; general task trees, parent/child slot release and orchestration remain P8 work.

Defer cloud activation and paid tests, full text/audio queue unification, learned model-quality routing, multimodal decision uploads, training/fine-tuning and general specialist orchestration. Jev/hosted Clef can be future connectors using the same typed contract once consent, locality, budgets and unknown-outcome accounting are implemented. Local-only classification must remain local even if the final user task has a cloud option. Free, open-source hearth does not depend on a subscription to a decision provider.

Selected direction: start with text-only Laya on the head for internal use and allow an explicit switch to a qualified dedicated decision capability. Include independent direct Decisions UI/API access so both placements can be explored at the same time. Benchmark the selected Laya checkpoint before promotion and treat larger models as optional challengers. The architecture choice above is the acceptance baseline. The implementation update and linked evidence record which parts are delivered and which qualification remains open.
