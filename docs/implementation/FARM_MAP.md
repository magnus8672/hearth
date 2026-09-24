# Live Admin farm map

The **Farm map** page in Administration (`#farm-map`) renders saved capability bindings as separate tree nodes inside dotted host groups. Several capabilities can point to the same model; several models can serve the same capability. Built-in memory appears inside the head. Unassigned capabilities and connected targets without bindings are listed separately.

The page polls the admin-only `GET /api/v1/farm-map` endpoint every ten seconds while visible. It requires `farm.inspect`, uses the normal authenticated session and farm-scoped database role, and returns an explicit projection without credentials, certificates, worker tokens, user content or job-owner identifiers. Failed refreshes leave the last map visible with an explicit stale warning. Selection, zoom, pan and collapsed groups survive ordinary refreshes; removing a selected binding returns inspection to the head.

## What the states mean

- **Loaded / Not loaded:** read-only LM Studio `/api/v1/models` inventory for targets configured with the `lmstudio_loaded` policy. Matches loaded instance IDs, not merely downloaded model names. Observations are cached for up to fifteen seconds per connection; transport failures show unknown residency.
- **Service ready:** fresh managed-worker heartbeat, matching desired/observed service and revision, not paused or revoked. This reports service health, not a new inference qualification.
- **On demand:** another service is selected on a fresh, shared worker. The existing queue prepares the required backend when work is admitted.
- **Starting, Paused, Service failed, Worker offline:** distinct worker observations. Stale heartbeat data never claims current service readiness.
- **Residency unknown:** unsupported or unavailable external residency observation. Generic OpenAI model catalogs do not establish residency.
- **Built-in:** scoped memory indexing/retrieval on the head.

Saved capability qualification, observed residency and pool occupancy remain separate. The map does not change target qualification, reserve capacity, generate content, load/unload models, switch worker services or reset queues. It respects existing provider TLS trust, approved LAN HTTP policy, private-address checks and redirect restrictions.

## Host boundaries

External endpoints are grouped by the hostname or IP in their saved connection URL, across ports. The head uses its configured Admin hostname. A matching managed worker supplies the group name; sharing a resource pool does not merge different endpoint hosts. Address aliases may therefore show the same physical machine twice. This is a routing view, not authenticated physical hardware discovery. Hardware inventory, alias reconciliation and arbitrary physical placement editing remain outside this page.

The layout supports additional machines, multiple rows of capability nodes, independent collapse controls, model-label toggling, an inspector and zoom/pan/fit controls. It uses the application's Daylight and Firelight tokens. The original static design artifacts remain separate from the application.

## Validation

Focused verification uses isolated PostgreSQL storage on the existing VM, distinct application/migration roles, fixture provider metadata and browser API fixtures. It covers Admin boundaries, safe projection, binding changes, loaded-instance matching, caching, stale/revoked/paused worker states, many-to-many binding identity, unknown residency, and distinct hosts sharing a pool. Browser cases exercise automatic refresh, removal, failure/recovery, collapse, inspection, empty/growing farms and narrow viewports. These checks are not fresh generation or model quality tests.
