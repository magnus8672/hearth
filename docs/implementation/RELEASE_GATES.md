# Release gates

The [shared tools milestone](SHARED_TOOLS_AND_CLIENT_API.md) adds partial E10/S11 evidence. See its [validation record](../../evidence/tools/2026-09-14/validation.json). The current totals are 20 partial, 41 not run and zero fully passed.

The 61 binding gates retain their original meaning in [the validation plan](../plan/09-VALIDATION-AND-RELEASE.md). None is fully passed. Foundation, local identity, chat and image checks provide only the partial evidence described below. Current browser and restart records are in [identity evidence](../../evidence/identity/2026-09-12).

| Gate | Scenario | Status | Evidence or remaining work |
|---|---|---|---|
| E01 | First boot and LAN signup | Partial evidence | Local native Owner provisioning and real HTTPS Member signup/MFA pass. A standalone Linux LAN profile also passes real Owner/MFA sign-in, public origins and verified IP TLS on a disposable farm. Selected-LAN signup policy, physical ESX/other-system trust and signed installer remain pending. |
| E02 | Start a new worker | Not run | Requires later product implementation and end-to-end validation. |
| E03 | Pair and assign coding | Not run | Requires later product implementation and end-to-end validation. |
| E04 | Restart/change DHCP address | Not run | Requires later product implementation and end-to-end validation. |
| E05 | NAS model transfer interruption | Not run | Requires later product implementation and end-to-end validation. |
| E06 | One local chat | Partial evidence | Real LM Studio streaming, private owner isolation, target identity and saved follow-ups pass. Complete source-deployment and usage accounting, broader hardware and provider-format reliability remain pending. |
| E07 | Unassigned job type | Not run | Requires later product implementation and end-to-end validation. |
| E08 | OpenAI fallback | Not run | Requires later product implementation and end-to-end validation. |
| E09 | Local-only workflow | Not run | Requires later product implementation and end-to-end validation. |
| E10 | Shared toolbox | Partial evidence | Actual Streamable HTTP tools use two fixture users' separate credentials; private receipts and real resident Qwen tool use pass. Real multi-user identity and managed remote toolbox acceptance remain open. See shared tools validation. |
| E11 | Specialist consultation | Not run | Requires later product implementation and end-to-end validation. |
| E12 | Cross-session recall | Partial evidence | Real resident LAN Qwen recalls a private note in a fresh chat. SQL scope/revision checks, source links and bounded context pass. Semantic graph retrieval, broader knowledge quality and complete P7 acceptance remain pending. |
| E13 | Superseded preference | Partial evidence | A corrected preference is recalled by real resident Qwen in another fresh chat. Original revisions, stale-import rejection, source-lineage invalidation and in-flight publication fencing pass. Topic assertion workflows and full semantic graph supersession remain pending. |
| E14 | Delete conversation | Not run | Requires later product implementation and end-to-end validation. |
| E15 | Concurrent users | Not run | Requires later product implementation and end-to-end validation. |
| E16 | Worker loss mid-task | Not run | Requires later product implementation and end-to-end validation. |
| E17 | Controller restart | Partial evidence | One normal guest poweroff/start preserved accounts, draft content/revisions and certificates. In-flight task recovery and abrupt controller-loss behavior remain pending. |
| E18 | NAS/internet unavailable | Not run | Requires later product implementation and end-to-end validation. |
| E19 | Media workflow | Partial evidence | Real local SDXL images, private/chat/channel artifacts, contextual prompt planning, bounded image batches, description-based variations, provenance, digest/PNG validation and scoped cancellation pass. Required local 3D, transcription and speech in the same authorized session remain pending. |
| E20 | Backup restoration | Not run | Requires later product implementation and end-to-end validation. |
| E21 | Install/update/uninstall | Not run | Requires later product implementation and end-to-end validation. |
| E22 | Budget race | Not run | Requires later product implementation and end-to-end validation. |
| S01 | Spoofed discovery hostname/key | Not run | Requires later product implementation and end-to-end validation. |
| S02 | Replay/steal encrypted enrollment grant | Partial evidence | JWE tamper and binding checks only; durable one-use grants/CSR/revocation pending. |
| S03 | Revoked node on existing stream | Not run | Requires later product implementation and end-to-end validation. |
| S04 | User A requests User B IDs or SSE cursor | Partial evidence | Real PostgreSQL forced RLS and two real Members reject guessed Owner draft IDs. SSE cursors and shared-workspace paths remain pending. |
| S05 | Graph search reveals another user's node/count | Not run | Requires later product implementation and end-to-end validation. |
| S06 | Prompt says to use admin tool/cloud | Partial evidence | Locality and grant policy primitives pass; end-to-end prompt/tool paths pending. |
| S07 | NAS path traversal/symlink/corrupt weights | Not run | Requires later product implementation and end-to-end validation. |
| S08 | Uploaded HTML/SVG/script/tool output | Not run | Requires later product implementation and end-to-end validation. |
| S09 | Forged mTLS identity headers | Partial evidence | Spoofed identity headers cannot authenticate; worker mTLS listener pending. |
| S10 | Malicious tool URL / DNS rebinding | Not run | Requires later product implementation and end-to-end validation. |
| S11 | Tool adds schema/requests wider credentials | Partial evidence | Actual MCP schema drift disables the approved tool before execution; connection changes invalidate per-user credential bindings, and revoked keys cannot dispatch or receive results. Broader hostile-server and managed-package acceptance remain open. See shared tools validation. |
| S12 | Database pool reuses prior identity | Partial evidence | Real pooled PostgreSQL transactions reset personal identity and fail closed without it. Broader shared/index/stream paths remain pending. |
| S13 | Concurrent deletion and index write | Not run | Requires later product implementation and end-to-end validation. |
| S14 | Copied node certificate | Not run | Requires later product implementation and end-to-end validation. |
| S15 | Unknown paid-call outcome/retry | Not run | Requires later product implementation and end-to-end validation. |
| S16 | User promotes self via role API | Partial evidence | Public login provisioning grants only Member; real Members cannot inspect the admin farm. Role-editing APIs and promotion attack acceptance remain pending. |
| S17 | Cloud access through Graphify ambient env | Not run | Requires later product implementation and end-to-end validation. |
| S18 | IPv6 or alternate admin route bypass | Not run | Requires later product implementation and end-to-end validation. |
| C01 | First node creates hearth | Partial evidence | Local accelerated stack, console-bound Owner setup, MFA and private drafts work; the user completed Windows trust and reached Administration in Zen. Signed installer, other-system trust and sustained VM reliability remain pending. |
| C02 | Member needs only head address/port | Not run | Requires later product implementation and end-to-end validation. |
| C03 | All normal settings managed centrally | Not run | Requires later product implementation and end-to-end validation. |
| C04 | Correct service for assigned job | Not run | Requires later product implementation and end-to-end validation. |
| C05 | Pairing proof/envelope integrity | Partial evidence | Go/Python JWE interoperability and narrow tamper cases pass; full enrollment lifecycle pending. |
| C06 | Rogue head or anonymous endpoint | Not run | Requires later product implementation and end-to-end validation. |
| C07 | Untrusted provisioning input | Partial evidence | Python signature/digest checks and revision policy pass; native installer and provisioning still pending. |
| C08 | Setup and browser-origin isolation | Partial evidence | Exact-origin BFFs, one-use callback state, PKCE, audience-bound cookies, CSRF, setup proof/Host/Origin checks and logout rejection pass. Browser setup now verifies all three HTTPS origins independently of OS trust. Production helper, LAN/IPv6/alternate routes and complete lifecycle matrix remain pending. |
| C09 | Recovery and single control head | Not run | Requires later product implementation and end-to-end validation. |
| A01 | First provider on hearth itself | Not run | Requires later product implementation and end-to-end validation. |
| A02 | First provider on a member | Not run | Requires later product implementation and end-to-end validation. |
| A03 | OpenAI-first setup | Not run | Requires later product implementation and end-to-end validation. |
| A04 | Missing/broken provider | Not run | Requires later product implementation and end-to-end validation. |
| A05 | Real agentic management | Not run | Requires later product implementation and end-to-end validation. |
| A06 | Role and history isolation | Not run | Requires later product implementation and end-to-end validation. |
| A07 | Secret and cloud boundary | Not run | Requires later product implementation and end-to-end validation. |
| A08 | Prompt injection and fake approval | Partial evidence | Server-normalized plan digests and typed grant checks pass; real agent injection fixtures pending. |
| A09 | Plans and bounded routine grants | Partial evidence | Grant scope, expiry, revocation, hash and current revision checks pass; durable Apply and execution pending. |
| A10 | Idempotent durable operations | Not run | Requires later product implementation and end-to-end validation. |
| A11 | Agent changes its own provider | Not run | Requires later product implementation and end-to-end validation. |
| A12 | Useful setup and growth before optional services | Not run | Manual local chat/image provider assignment works without NAS/MCP setup. Agent-driven service addition, member installation/pairing/assignment and supported media/3D expansion are not implemented; the full P4 and P8 gate remains open. |

A12 is split across text/tool orchestration in P4 and required media, including local 3D, in P8. Neither part substitutes for the other. The full gate remains open.
