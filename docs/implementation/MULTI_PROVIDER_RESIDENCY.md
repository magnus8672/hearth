# Multiple provider instances and resident specialists

> Addresses, host labels and accounts shown here are illustrative placeholders. Use your own private deployment configuration.

> Current status, 18 September: the active farm has one Qwen LLM target plus Fooocus/TRELLIS. Historical physical two-LLM concurrency has evidence in the vision report; complete UI/residency/failure/load qualification remains open. Provider qualification no longer expires hourly. See [the dated farm snapshot](CURRENT_STATE.md) and [current coverage](DESIGN_COVERAGE.md).

Implemented 13 September 2026. The local build now has explicit server onboarding and loaded-model checks for LM Studio. It is ready for the user's multi-machine test; physical LAN concurrency and automatic-loading configuration on those machines remain to be qualified.

Follow-up: [external HTTP approval](EXTERNAL_HTTP_PROVIDERS.md) now lets existing LAN services connect directly after admin risk acceptance. Its real Qwen test adds remote-model transport evidence; a later bounded physical-concurrency case passed, while the full UI/residency/failure workflow remains open. Use the direct HTTP instructions in the LAN guide when certificates or a connector are unnecessary for your chosen network policy.

## What changed

| Area | Current behavior |
|---|---|
| Add a server | A persistent **Add server** action starts a fresh form, including from edit mode. Connection, model, key, trust, group and confirmations reset. Every supported provider type accepts multiple independent servers. The farm limit remains 32 targets. |
| Add a model | **Add model to this server** reuses the server address, saved key and certificate trust. Those connection fields are locked, the model starts blank, and the resource group is inherited. This is optional for machines with capacity for several resident models. |
| Edit | Clearly marked edit mode retains the target identity and capability assignments, checks revision, and invalidates previous verification. Moving a model onto another existing server cannot silently rename that server. Shared credentials/trust cannot be overwritten through a sibling target. |
| Identity | The same model identifier on distinct connections stays independently addressable. A duplicate server/model pair returns a conflict. Provider lists expose connection IDs; new route receipts preserve connection ID, resource group and residency policy alongside target/model/revision. |
| Capacity | The UI requires a deliberate resource-group name, offers existing names and warns when sharing one. API callers omitting a group receive a conservative per-host default; different ports on one host share that default. Existing groups are preserved. Host aliases and multiple GPUs still need deliberate operator grouping. |
| Assignments | Several capabilities can use one model; a capability can keep up to eight ordered targets. Choices show the server address as well as name/model. Independent idle groups can accept work concurrently. Busy, stale, disabled or incompatible targets are skipped before admission. |
| LM Studio residency | Optional **LM Studio · require a loaded instance** checks the native model list before every text generation, including verification, private chat, channel replies and image planning. Missing, malformed or unreachable loaded-state reports stop inference. Select the exact loaded instance identifier. |
| Other services | Compatible services without this check retain explicitly unknown residency. Image pipelines retain their existing job/lifecycle behavior; this change does not make staged media pipelines permanently resident or enable pending modality adapters. |

Migration `0012` adds a constrained target policy, defaulting existing records to `unknown`. It does not rename providers, rewrite their groups, enable residency checks without configuration or change user content.

## Residency boundary

LM Studio's [native list endpoint](https://lmstudio.ai/docs/developer/rest/list) distinguishes downloaded models from loaded instances. hearth reads `GET /api/v1/models` and accepts only the exact instance ID under an LLM's `loaded_instances`; an available model key alone is insufficient. The connector now permits that read-only endpoint while still rejecting load, unload and download operations.

In LM Studio, disable Just-in-Time loading and automatic unloading, and keep the intended model loaded. The form requires confirmation that automatic loading has been disabled when selecting this check. [LM Studio documents JIT loading, idle TTL and auto-eviction](https://lmstudio.ai/docs/developer/core/ttl-and-auto-evict). hearth does not change these server settings. They are an operator declaration, not remote attestation.

The preflight is an observation, not an atomic memory reservation. Another client can change the server between observation and inference. The server must enforce its configured no-auto-load behavior to close that race. A failure after admission is reported on that turn; hearth does not silently issue the same generation on another model. Live loaded-state filtering of every routing candidate, event-driven inventory and managed lifecycle/reservations remain future work. The existing deterministic selector still chooses among configured, qualified targets before the per-request loaded-state check.

## Validation and scope

- The [four-server integration test](../../tests/integration/test_multi_provider.py) uses actual loopback HTTP/SSE servers and PostgreSQL behind the BFF APIs. Four separate targets, including identical model IDs on different servers, survive a fresh admin session. All four requests reach their respective servers before any is released. Shared capacity rejects extra work. An unloaded target receives no generation POST. This is a simulated multi-host topology on one computer, not physical LAN qualification.
- The [browser regression](../../tests/browser/multi-provider.spec.ts) adds four same-type text servers, adds another model on an existing server, escapes edit mode safely, adds two image servers, reloads all seven targets and checks desktop/mobile layout. Its identity and API data are explicit fixtures. Existing route-editing regressions remain separate checks.
- Transport regressions reject unavailable, malformed, redirected and wrong-modality loaded-state reports before inference. Connector tests on Windows and Linux permit native model-list reads and reject lifecycle writes, unauthorized credentials, wrong TLS trust and invalid hostnames.
- The [real LM Studio check](../../evidence/multi-provider/2026-09-13/live-residency.json) uses the user's selected `openai/gpt-oss-20b`, a disposable farm and explicit OIDC fixtures. A feature probe and routed reply complete through the real model API; loaded instance IDs remain unchanged before/after. It records admission and first-output timing. Automatic-loading settings were neither changed nor verified by that test.

See the [validation record](../../evidence/multi-provider/2026-09-13/validation.json) for suite counts, deployment identity and artifact hashes. Desktop and mobile screenshots are in the same evidence directory. At that milestone the ledger had 16 partial and 45 not run; the current ledger has 20 partial and 41 not run, with no full pass. The full multi-server acceptance closes only after exercising the actual admin UI, connector trust, residency configuration and concurrent dispatch together on separate physical hosts.

## Try it

Reload [Administration](https://hearth.example.invalid:8443), open **Providers**, and use **Add server** for each machine. Use a distinct resource group for each independent GPU. For LM Studio, select the loaded-model check after configuring its server settings. Assign planning, writing and coding to different targets under **Give each capability a home**, then send requests from separate conversations. Follow [LAN provider testing](LAN_PROVIDER_TESTING.md) for connector setup and shared-capacity cases. Replace older connector binaries with the rebuilt packages to use the native model-list check; keep their existing private identity files.
