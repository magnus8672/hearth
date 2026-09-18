# Current farm snapshot

Observed 18 September 2026 through read-only SSH, operational database metadata, HTTPS readiness and LM Studio's native model inventory. The initial review used `main` at `d9ce334`; later same-day changes include the conversation queue, geometry catalog, channel heading and Hunyuan backend below. This remains a dated observation, not continuous monitoring. See [initial review evidence](../../evidence/documentation/2026-09-18/live-review.json) and [Hunyuan qualification](../../evidence/geometry/2026-09-18/hunyuan-validation.json).

## Machines and endpoints

| Machine | Responsibility | Observed configuration |
|---|---|---|
| Head, `10.20.30.10` | Existing ESXi VM; SSH `operator`; `/opt/hearth`; Compose `hearth-head` | Six running containers: admin API, user API, PostgreSQL, Keycloak, Caddy edge and reference MCP tools. Database at `0026`; both public API readiness checks pass with TLS validation. |
[Historical deployment inventory removed for repository privacy.]
| model-host, `10.20.30.30` | User-operated LM Studio on the source/client workstation | `qwen/qwen3.8-27b`, Q4_K_M, loaded context [redacted capacity] tokens; one loaded LLM instance. The downloaded Nomic embedding model is not loaded. |

| Surface | Address |
|---|---|
| Welcome and public certificate downloads | `http://hearth.example.invalid` |
| Workspace | `https://hearth.example.invalid` |
| Administration | `https://hearth.example.invalid:8443` |
| Identity | `https://hearth.example.invalid:8445` |
| Client API / MCP | `https://hearth.example.invalid/v1` / `https://hearth.example.invalid/mcp` |

Use the hostname for application TLS and SSH IPs for maintenance. The head certificate was migrated to `hearth.example.invalid`; old IP-based application URLs in historical evidence are not current client instructions. Models remain on their provider machines. The old laptop head/QEMU appliance stays retired; independent LM Studio remains under the user's control.

## Saved providers and capability availability

| Provider | Address and model | Saved verification / resource group |
|---|---|---|
| model-host | `http://10.20.30.30:1234/v1`; `qwen/qwen3.8-27b` | Previously qualified for chat, streaming and tools, but currently marked failed after a generation error; `lmstudio_loaded` preflight; `text-pool` |
| media-worker Fooocus | `http://10.20.30.20:1235/v1`; `fooocus/juggernaut-xl-v8` | Ready; text-to-image and image jobs; `media-worker GPU` |
| media-worker TRELLIS | `https://10.20.30.20:1236/v1`; `trellis2/q8` | Ready; image-to-3D and geometry jobs; verified `trellis-v1` tuning controls; `media-worker GPU` |
| media-worker Hunyuan3D 2.0 | `https://10.20.30.20:1238/v1`; `hunyuan3d/2.0` | Ready; image-to-3D with 128–512 octree extraction (default 512); verified `hunyuan-v1` tuning controls; `media-worker GPU` |

Saved qualification and a selected running service are separate. media-worker uses policy `shared`; the next job chosen by owner fairness determines which of its three signed services runs. Gallery and conversation images select Fooocus; geometry jobs retain their chosen TRELLIS or Hunyuan target. The worker confirms all other service cgroups stopped before starting the selected service. Saved provider qualification alone does not mean it is currently resident.

| Capability | Current farm status |
|---|---|
| `chat.general`, `code.implement` | Assigned to model-host with historical saved text features. Its later generation-error state currently makes the target ineligible; this Hunyuan change does not reconfigure LM Studio. |
| `vision.describe` | Assigned to model-host, but its saved features lack `vision`. LM Studio advertises vision; hearth still requires its actual pixel-reading verification before this route is eligible. The review did not run that probe. |
| `image.generate` | Assigned to media-worker Fooocus. Gallery, private-chat and channel image jobs use the shared GPU queue and service selection. |
| `geometry.generate` | Assigned to media-worker TRELLIS and Hunyuan3D 2.0. The geometry page lets members choose either provider. Private image-to-3D, required names/reference thumbnails, validated GLB preview/export/delete and cancellation are implemented. |
| `memory.retrieve`, `memory.index` | Built-in private PostgreSQL knowledge functions on the head; they do not require an inference-target binding. Access still depends on user grants. |
| `reason.plan`, `code.explain`, `write.compose`, `text.summarize`, `data.extract` | Implemented text profiles without dedicated saved bindings in this farm. Automatic intent selection can use the existing general-chat fallback when a specialist is unassigned; an explicit specialist request requires its own eligible assignment. |
| `audio.speak`, `audio.transcribe` | Implemented adapters, with historical real CPU-provider evidence. No audio providers or bindings are registered in this farm. |

All fourteen profiles have bounded executable implementations. This does not mean all fourteen are enabled here, or that a successful transport probe establishes task quality. There is no automatic model loading/swapping on the external LM Studio request path.

## Application layout and boundaries

Workspace navigation includes Private chat, Channels, Images, 3D models, Memory, Private drafts, Tools, Client connections and Capabilities, filtered by account grants. Administration includes Overview, Providers, Workers, Capabilities, Shared tools, People and Settings.

New signups are pending with zero permissions. People administration grants access explicitly; changes fence old sessions, API keys and execution authority. Owner accounts and the acting account are protected. Keycloak MFA SSO is shared across the two applications, while BFF sessions and authorization remain separate.

The head owns private storage, authorization, routing and durable gallery queues. Independent resource groups can run concurrently. Private image/geometry galleries and private-chat/channel image jobs share the durable fair queue. Text, audio and client API requests retain their existing admission behavior. The live router uses deterministic intent selection and ordered qualified targets. Switchyard has adapter/probe evidence but is not called by live dispatch.

## Verification limits and remaining work

The initial review checked operational metadata, not personal messages, credentials or generated artifacts. The later Hunyuan work generated an original qualification cube, validated and previewed its textured GLB, tested cancellation and three-way switching, and refreshed head/provider metadata; it did not inspect members' private content. Six sampled VM source files matched this checkout after newline normalization. It did not verify every deployed file or browser bundle, rerun sign-in, generate media, test provider failure, or complete a Hermes session. The older 8,192-token Hermes context observation is superseded by the current [redacted capacity]-token loaded context; this alone does not qualify the full client workflow.

The local tree was clean at the review. Its cached `origin/main` matched `d9ce334`; the read-only GitHub SSH check failed with `Permission denied (publickey)`, so remote branch freshness and current CI results were not verified. The docs cleanup does not change SSH credentials.

Automatic enrollment/mTLS, full NodePlan provisioning, signed distribution, protected administrative agent workflows, live Switchyard routing, cloud gateway/budgets, universal scheduling, semantic Graphify extraction, complete deletion/restore and broad hardware/quality qualification remain open. The [release ledger](RELEASE_GATES.md) retains **20 partial, 41 not run, zero fully passed**. Required local 3D and P8/A12 remain in scope; the bounded TRELLIS implementation supplies evidence without closing those gates.
